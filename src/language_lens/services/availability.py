"""One set of action rules for Settings, tray actions and capture dispatch."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Availability:
    verified: bool
    capture_busy: bool = False
    model_busy: bool = False
    voice_busy: bool = False
    shutting_down: bool = False
    hotkey_valid: bool = True

    @property
    def capture_enabled(self) -> bool:
        return self.verified and not self.reason

    @property
    def listening_enabled(self) -> bool:
        return self.capture_enabled and self.hotkey_valid

    @property
    def maintenance_enabled(self) -> bool:
        return not (self.capture_busy or self.model_busy or self.voice_busy or self.shutting_down)

    @property
    def reason(self) -> str:
        if self.shutting_down:
            return "Language Lens is closing."
        if self.capture_busy:
            return "Close the current screenshot before starting another capture or changing local files."
        if self.model_busy:
            return "Finish or cancel the local model task before capturing."
        if self.voice_busy:
            return "Finish or cancel the voice download/check before capturing."
        if not self.verified:
            return "Verify the local OCR and translation files in 'Settings' before capturing."
        return ""
