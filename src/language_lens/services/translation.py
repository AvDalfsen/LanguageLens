from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
import math
import os
from threading import RLock
import unicodedata

from language_lens.domain import WordTranslation
from language_lens.services.model_download import DownloadProgress, download_model


EXPANDED_HYPOTHESES = 12
# Argos caches translation objects globally, including mutable hypothesis caches.
_TRANSLATION_LOCK = RLock()


class TranslationUnavailable(RuntimeError):
    pass


class ModelRouteUnavailable(TranslationUnavailable):
    pass


def selection_results(translator, text, words, source, target, report, cancelled=lambda: False):
    """Yield the sentence once, then one word delta per completed lookup.

    None means the sentence is unchanged; an empty string means it failed.
    Consumers merge word deltas, keeping IPC and GUI work linear in word count.
    """
    if cancelled():
        return
    try:
        sentence = translator.translate(text, source, target)
    except Exception:
        sentence = ""
        report("Whole-selection translation failed. Word lookups remain available; choose 'Retry translation' to try again.")
    yield sentence, {}
    for word in dict.fromkeys(words):
        if cancelled():
            return
        try:
            translation = translator.word_candidates(word, source, target)
        except Exception:
            translation = WordTranslation((), "Word translation unavailable. Choose 'Retry translation' to try again.")
        yield None, {word: translation}


class ArgosTranslator:
    """Local translator backed by installed Argos model packages."""

    def __init__(self) -> None:
        self._lock = _TRANSLATION_LOCK

    @staticmethod
    def _modules():
        # Ignore inherited Argos cloud-provider preferences. Lens is local-only.
        os.environ["ARGOS_MODEL_PROVIDER"] = "OPENNMT"
        os.environ["ARGOS_CHUNK_TYPE"] = "ARGOSTRANSLATE"
        os.environ["ARGOS_DEBUG"] = "0"
        try:
            import argostranslate.package as package
            import argostranslate.translate as translate
            from argostranslate import settings
            if settings.model_provider != settings.ModelProvider.OPENNMT:
                settings.model_provider = settings.ModelProvider.OPENNMT
                translate.get_installed_languages.cache_clear()
            settings.debug = False
            settings.chunk_type = settings.ChunkType.ARGOSTRANSLATE
            settings.device = "cpu"
            settings.intra_threads = 2
            settings.inter_threads = 1
        except ImportError as exc:  # pragma: no cover - exercised in installed app
            raise TranslationUnavailable(
                "Argos Translate is not installed. Run the setup command from README.md."
            ) from exc
        return package, translate

    def route(self, source: str, target: str) -> list:
        if source == target:
            return []
        _, backend = self._modules()
        languages = {language.code: language for language in backend.get_installed_languages()}
        try:
            translation = languages[source].get_translation(languages[target])
        except KeyError as exc:
            raise TranslationUnavailable(f"No installed local route for {source} → {target}.") from exc
        def packages(item):
            if hasattr(item, "underlying"):
                return packages(item.underlying)
            if hasattr(item, "t1"):
                return packages(item.t1) + packages(item.t2)
            return [item.pkg] if hasattr(item, "pkg") else []
        if translation is None:
            raise TranslationUnavailable(f"No installed local route for {source} → {target}.")
        return packages(translation)

    def is_pair_installed(self, source: str, target: str) -> bool:
        if source == target:
            return True
        _, translate = self._modules()
        # Missing languages are normal; enumeration/backend failures are not.
        # Propagate those failures so Settings reports an unknown status rather
        # than encouraging downloads for a model that may already be installed.
        installed = {language.code: language for language in translate.get_installed_languages()}
        if source not in installed or target not in installed:
            return False
        return installed[source].get_translation(installed[target]) is not None

    def install_pair(
        self,
        source: str,
        target: str,
        progress: Callable[[str], None] | None = None,
        download_progress: Callable[[DownloadProgress], None] | None = None,
        *, staged: bool = False, force: bool = False,
    ) -> None:
        """Install a direct model, or two models routed through English."""
        if source == target:
            return
        package, translate = self._modules()
        report = progress or (lambda _message: None)
        report("Fetching the Argos model index...")
        package.update_package_index()
        available = package.get_available_packages()

        def find(from_code: str, to_code: str):
            return next(
                (
                    candidate
                    for candidate in available
                    if candidate.from_code == from_code and candidate.to_code == to_code
                ),
                None,
            )

        route = []
        direct = find(source, target)
        if direct is not None:
            route = [direct]
        else:
            legs = [(source, "en"), ("en", target)]
            legs = [leg for leg in legs if leg[0] != leg[1]]
            route = [find(*leg) for leg in legs]
            if any(model is None for model in route):
                raise ModelRouteUnavailable(
                    f"No Argos model route is available for {source} -> {target}."
                )

        pending = [model for model in route
                   if force or not self.is_pair_installed(model.from_code, model.to_code)]
        for index, model in enumerate(pending, 1):
            label = f"{model.from_name} → {model.to_name}"
            if len(pending) > 1:
                label += f" · model {index} of {len(pending)}"
            model_path = download_model(model, package, label, report, download_progress)
            report(f"Installing {label}…")
            if staged:
                from language_lens.services.model_management import install_archive, InvalidModelArchive
                try:
                    install_archive(model_path, package, expected=(model.from_code, model.to_code))
                except InvalidModelArchive:
                    # A ZIP can pass CRC verification but contain unusable weights.
                    # Do not reuse that managed download on every subsequent retry.
                    from pathlib import Path
                    if (hasattr(package.settings, "language_lens_download_scratch")
                            and Path(model_path).resolve().parent == Path(package.settings.downloads_dir).resolve()):
                        Path(model_path).unlink(missing_ok=True)
                    raise
            else:
                package.install_from_path(model_path)
            cache_clear = getattr(translate.get_installed_languages, "cache_clear", None)
            if cache_clear is not None:
                cache_clear()
            cached = getattr(translate, "installed_translates", None)
            if cached is not None:
                cached.clear()
        self.translate.cache_clear()
        self.word_candidates.cache_clear()
        report("Local translation model ready.")

    @lru_cache(maxsize=4096)
    def word_candidates(self, text: str, source: str, target: str,
                        *, expanded: bool = False) -> WordTranslation:
        """Rank translations of a word in isolation, with a larger search on demand.

        Argos scores are used only for ordering. They are length-adjusted search
        scores, not probabilities that a particular meaning fits the sentence.
        The compact search requests five hypotheses and keeps four distinct results.
        The expanded search keeps every distinct result from twelve hypotheses.
        The installed translation also handles routes through an intermediate language.
        """
        if not text:
            return WordTranslation(())
        if source == target:
            return WordTranslation((text,), "Source and target languages are the same.")
        _, backend = self._modules()
        with self._lock:
            try:
                languages = {language.code: language for language in backend.get_installed_languages()}
                translation = languages[source].get_translation(languages[target])
                hypotheses = translation.hypotheses(
                    text, num_hypotheses=EXPANDED_HYPOTHESES if expanded else 5,
                )
                ranked = []
                for hypothesis in hypotheses:
                    value = " ".join(unicodedata.normalize("NFC", hypothesis.value).split())
                    score = float(hypothesis.score)
                    if value and math.isfinite(score):
                        ranked.append((value, score))
                ranked.sort(key=lambda item: item[1], reverse=True)
                candidates, seen = [], set()
                for value, _score in ranked:
                    # Capitalization can distinguish meanings (US/us, Polish/polish).
                    # Ignore terminal punctuation, but retain case for every language.
                    key = value.strip(" \t.,;:!?…。！？\"'“”‘’«»")
                    if key and key not in seen:
                        seen.add(key)
                        candidates.append(value)
                if candidates:
                    return WordTranslation(tuple(candidates if expanded else candidates[:4]))
            except Exception as exc:
                if expanded:
                    raise TranslationUnavailable("Could not load more candidates. Please retry.") from exc
                # Some packages/backends can translate but cannot return an n-best list.
                # Keep the usual translation available and explicitly label the fallback.
                pass
            if expanded:
                raise TranslationUnavailable("The expanded search returned no usable candidates. Please retry.")
            value = self.translate(text, source, target)
            return WordTranslation((value,), "Alternatives unavailable; showing a single translation.")

    @lru_cache(maxsize=4096)
    def translate(self, text: str, source: str, target: str) -> str:
        if not text or source == target:
            return text
        _, translate = self._modules()
        with self._lock:
            try:
                result = translate.translate(text, source, target)
            except Exception as exc:  # Argos raises several backend-specific errors
                raise TranslationUnavailable(
                    f"Local translation failed for {source} → {target}. Use 'Check required files' or 'Reinstall translation model' in 'Settings'."
                ) from exc
        return result.strip() or text

