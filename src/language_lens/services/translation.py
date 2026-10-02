from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from threading import RLock


class TranslationUnavailable(RuntimeError):
    pass


class ArgosTranslator:
    """Local translator backed by installed Argos model packages."""

    def __init__(self) -> None:
        self._lock = RLock()

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

        for model in route:
            if self.is_pair_installed(model.from_code, model.to_code):
                continue
            report(f"Downloading {model.from_name} -> {model.to_name}...")
            model_path = model.download()
            report(f"Installing {model.from_name} -> {model.to_name}...")
            package.install_from_path(model_path)
            cache_clear = getattr(translate.get_installed_languages, "cache_clear", None)
            if cache_clear is not None:
                cache_clear()
        self.translate.cache_clear()
        report("Local translation model ready.")

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

