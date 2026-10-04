from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
import math
from threading import RLock
import unicodedata

from language_lens.domain import WordTranslation
from language_lens.services.model_download import DownloadProgress, download_model


EXPANDED_HYPOTHESES = 12
# Argos caches translation objects globally, including mutable hypothesis caches.
_TRANSLATION_LOCK = RLock()


class TranslationUnavailable(RuntimeError):
    pass


class ArgosTranslator:
    """Local translator backed by installed Argos model packages."""

    def __init__(self) -> None:
        self._lock = _TRANSLATION_LOCK

    @staticmethod
    def _modules():
        try:
            import argostranslate.package as package
            import argostranslate.translate as translate
        except ImportError as exc:  # pragma: no cover - exercised in installed app
            raise TranslationUnavailable(
                "Argos Translate is not installed. Run the setup command from README.md."
            ) from exc
        return package, translate

    def is_pair_installed(self, source: str, target: str) -> bool:
        if source == target:
            return True
        _, translate = self._modules()
        try:
            installed = {language.code: language for language in translate.get_installed_languages()}
            translation = installed[source].get_translation(installed[target])
            return translation is not None
        except (KeyError, AttributeError, StopIteration):
            return False

    def install_pair(
        self,
        source: str,
        target: str,
        progress: Callable[[str], None] | None = None,
        download_progress: Callable[[DownloadProgress], None] | None = None,
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
                raise TranslationUnavailable(
                    f"No Argos model route is available for {source} -> {target}."
                )

        pending = [model for model in route
                   if not self.is_pair_installed(model.from_code, model.to_code)]
        for index, model in enumerate(pending, 1):
            label = f"{model.from_name} → {model.to_name}"
            if len(pending) > 1:
                label += f" · model {index} of {len(pending)}"
            model_path = download_model(model, package, label, report, download_progress)
            report(f"Installing {label}…")
            package.install_from_path(model_path)
            cache_clear = getattr(translate.get_installed_languages, "cache_clear", None)
            if cache_clear is not None:
                cache_clear()
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
                    # Case/terminal punctuation variants do not add another meaning.
                    key = value.casefold().strip(" \t.,;:!?…。！？\"'“”‘’«»")
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
                    f"The local {source} -> {target} model is not installed."
                ) from exc
        return result.strip() or text

