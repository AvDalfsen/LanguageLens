from types import SimpleNamespace

from language_lens.services.translation import ArgosTranslator


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

    ArgosTranslator().install_pair("en", "pt")

    assert installed_paths == ["model.argosmodel"]
    assert installed_languages.clear_count == 1
