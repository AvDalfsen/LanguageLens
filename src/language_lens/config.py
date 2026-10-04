from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path


LANGUAGES: tuple[tuple[str, str], ...] = (
    ("Arabic", "ar"),
    ("Chinese", "zh"),
    ("Czech", "cs"),
    ("Danish", "da"),
    ("Dutch", "nl"),
    ("English", "en"),
    ("Finnish", "fi"),
    ("French", "fr"),
    ("German", "de"),
    ("Greek", "el"),
    ("Hindi", "hi"),
    ("Hungarian", "hu"),
    ("Italian", "it"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Norwegian", "nb"),
    ("Polish", "pl"),
    ("Portuguese (Portugal)", "pt"),
    ("Portuguese (Brazil)", "pb"),
    ("Romanian", "ro"),
    ("Russian", "ru"),
    ("Spanish", "es"),
    ("Swedish", "sv"),
    ("Turkish", "tr"),
    ("Ukrainian", "uk"),
)


@dataclass(slots=True)
class Settings:
    source_language: str = "pt"
    target_language: str = "en"
    hotkey: str = "<ctrl>+<shift>+t"
    send_escape: bool = True
    min_ocr_confidence: float = 0.45
    speech_enabled: bool = True
    show_ipa: bool = False
    speech_voices: dict[str, str] = field(default_factory=dict)


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "LanguageLens" / "settings.json"


def legacy_settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "GameLanguageLens" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    if path is None:
        path = settings_path()
        if not path.exists() and legacy_settings_path().exists():
            path = legacy_settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "send_escape" not in raw and "pause_game" in raw:
            raw["send_escape"] = raw["pause_game"]
        if not isinstance(raw.get("speech_voices", {}), dict):
            raw["speech_voices"] = {}
        allowed = Settings.__dataclass_fields__.keys()
        return Settings(**{key: value for key, value in raw.items() if key in allowed})
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    temporary.replace(path)

