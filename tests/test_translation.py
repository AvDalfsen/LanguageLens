from types import SimpleNamespace

import pytest

from language_lens.domain import WordTranslation
from language_lens.services.translation import ArgosTranslator
import language_lens.services.translation as translation_module


class FakeLanguage:
    def __init__(self, code, translations=None):
        self.code = code
        self.translations = translations or {}

    def get_translation(self, target):
        return self.translations.get(target.code)


def test_pair_is_not_installed_when_argos_returns_none(monkeypatch):
    english = FakeLanguage("en")
    portuguese = FakeLanguage("pt")
    translate = SimpleNamespace(get_installed_languages=lambda: [english, portuguese])
    monkeypatch.setattr(
        ArgosTranslator,
        "_modules",
        staticmethod(lambda: (SimpleNamespace(), translate)),
    )

    assert not ArgosTranslator().is_pair_installed("en", "pt")


def test_pair_is_installed_when_argos_returns_a_translation(monkeypatch):
    portuguese = FakeLanguage("pt")
    english = FakeLanguage("en", {"pt": object()})
    translate = SimpleNamespace(get_installed_languages=lambda: [english, portuguese])
    monkeypatch.setattr(
        ArgosTranslator,
        "_modules",
        staticmethod(lambda: (SimpleNamespace(), translate)),
    )

    assert ArgosTranslator().is_pair_installed("en", "pt")


def test_install_refreshes_argos_installed_language_cache(monkeypatch):
    class InstalledLanguages:
        def __init__(self):
            self.clear_count = 0

        def __call__(self):
            return [FakeLanguage("en"), FakeLanguage("pt")]

        def cache_clear(self):
            self.clear_count += 1

    installed_languages = InstalledLanguages()
    translate = SimpleNamespace(get_installed_languages=installed_languages)
    model = SimpleNamespace(
        from_code="en",
        to_code="pt",
        from_name="English",
        to_name="Portuguese",
        download=lambda: "model.argosmodel",
    )
    installed_paths = []
    package = SimpleNamespace(
        update_package_index=lambda: None,
        get_available_packages=lambda: [model],
        install_from_path=installed_paths.append,
    )
    monkeypatch.setattr(
        ArgosTranslator,
        "_modules",
        staticmethod(lambda: (package, translate)),
    )
    monkeypatch.setattr(translation_module, "download_model", lambda *args: "model.argosmodel")

    ArgosTranslator().install_pair("en", "pt")

    assert installed_paths == ["model.argosmodel"]
    assert installed_languages.clear_count == 1


def candidate_backend(monkeypatch, hypotheses, single=lambda *_: "single translation"):
    english = FakeLanguage("en", {"pt": SimpleNamespace(hypotheses=hypotheses)})
    backend = SimpleNamespace(
        get_installed_languages=lambda: [english, FakeLanguage("pt")], translate=single,
    )
    monkeypatch.setattr(ArgosTranslator, "_modules", staticmethod(lambda: (None, backend)))
    return ArgosTranslator()


def test_word_candidates_rank_deduplicate_and_cache_without_changing_accents(monkeypatch):
    calls = []
    def hypotheses(text, num_hypotheses):
        calls.append((text, num_hypotheses))
        return [SimpleNamespace(value=value, score=score) for value, score in [
            ("cursos:", -3), (" pratos ", -.5), ("cursos", -1),
            ("avo\u0301", -1.5), ("avô", -2),
        ]]
    translator = candidate_backend(monkeypatch, hypotheses)
    result = translator.word_candidates("courses", "en", "pt")
    assert result == WordTranslation(("pratos", "cursos", "avó", "avô"))
    assert translator.word_candidates("courses", "en", "pt") == result
    assert calls == [("courses", 5)]


def test_word_candidates_preserve_meaningful_capitalization(monkeypatch):
    translator = candidate_backend(monkeypatch, lambda *_args, **_kwargs: [
        SimpleNamespace(value=value, score=-index) for index, value in enumerate(
            ("Polish", "polish", "US", "us", "US!")
        )
    ])
    assert translator.word_candidates("word", "en", "pt", expanded=True).candidates == (
        "Polish", "polish", "US", "us",
    )


def test_word_candidates_limit_to_four_unique_results_and_preserve_phrases(monkeypatch):
    translator = candidate_backend(monkeypatch, lambda *_args, **_kwargs: [
        SimpleNamespace(value=value, score=-index) for index, value in enumerate(
            ("curso de formação", "prato", "trajeto", "rumo", "percurso")
        )
    ])
    assert translator.word_candidates("course", "en", "pt").candidates == (
        "curso de formação", "prato", "trajeto", "rumo",
    )


@pytest.mark.parametrize("failure", ["exception", "empty", "invalid"])
def test_word_candidates_fall_back_explicitly_when_alternatives_unavailable(monkeypatch, failure):
    def hypotheses(*_args, **_kwargs):
        if failure == "exception":
            raise RuntimeError("This model cannot return multiple hypotheses")
        if failure == "invalid":
            return [SimpleNamespace(value=" ", score=0),
                    SimpleNamespace(value="invalid", score=float("nan"))]
        return []
    translator = candidate_backend(monkeypatch, hypotheses)
    result = translator.word_candidates("course", "en", "pt")
    assert result.candidates == ("single translation",)
    assert "Alternatives unavailable" in result.note


def test_missing_word_translation_is_an_error_not_a_fabricated_candidate(monkeypatch):
    def unavailable(*args):
        raise RuntimeError("No model")
    translator = candidate_backend(monkeypatch, lambda *a, **kw: [], unavailable)
    with pytest.raises(translation_module.TranslationUnavailable):
        translator.word_candidates("course", "en", "pt")


def test_same_language_candidates_do_not_load_models(monkeypatch):
    def no_models():
        raise AssertionError("Must not load a model")
    monkeypatch.setattr(ArgosTranslator, "_modules", staticmethod(no_models))
    result = ArgosTranslator().word_candidates("courses", "en", "en")
    assert result.candidates == ("courses",)
    assert "same" in result.note


@pytest.mark.parametrize("source,target,word,values", [
    ("en", "nl", "hovering", ("zwevend", "zwevende", "zweven", "zweeft", "zweefgedrag", "zweefde")),
    ("ja", "es", "見る", ("ver", "veo", "mirar", "mirando", "observar", "observando")),
    ("ru", "el", "видеть", ("βλέπω", "βλέπει", "κοιτάζω", "παρατηρώ", "βλέπουν", "βλέπεις")),
    ("it", "de", "vedere", ("sehen", "sieht", "schauen", "blicken", "betrachten", "ansehen")),
])
def test_expansion_keeps_all_distinct_guesses_and_separate_cache_entries(monkeypatch, source, target, word, values):
    # Synthetic hypotheses verify the shared workflow, not these models' linguistic quality.
    calls = []
    def hypotheses(text, num_hypotheses):
        calls.append(num_hypotheses)
        entries = [SimpleNamespace(value=value, score=-index) for index, value in enumerate(values)]
        return entries[:num_hypotheses]
    route = SimpleNamespace(hypotheses=hypotheses)
    backend = SimpleNamespace(get_installed_languages=lambda: [
        FakeLanguage(source, {target: route}), FakeLanguage(target),
    ])
    monkeypatch.setattr(ArgosTranslator, "_modules", staticmethod(lambda: (None, backend)))
    translator = ArgosTranslator()
    assert translator.word_candidates(word, source, target).candidates == values[:4]
    assert translator.word_candidates(word, source, target, expanded=True).candidates == values
    translator.word_candidates(word, source, target, expanded=True)
    assert translator.word_candidates(word, source, target).candidates == values[:4]
    assert calls == [5, 12]


def test_expanded_failure_preserves_compact_results_and_can_be_retried(monkeypatch):
    fail = [True]
    def hypotheses(text, num_hypotheses):
        if num_hypotheses == 12 and fail[0]:
            raise RuntimeError("Temporary backend failure")
        return [SimpleNamespace(value="vier", score=-1), SimpleNamespace(value="4", score=-2)]
    translator = candidate_backend(monkeypatch, hypotheses)
    compact = translator.word_candidates("four", "en", "pt")
    with pytest.raises(translation_module.TranslationUnavailable, match="retry"):
        translator.word_candidates("four", "en", "pt", expanded=True)
    assert translator.word_candidates("four", "en", "pt") == compact
    fail[0] = False
    assert translator.word_candidates("four", "en", "pt", expanded=True).candidates == ("vier", "4")
