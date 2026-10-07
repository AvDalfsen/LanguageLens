from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
from language_lens.services.hotkey import normalize_hotkey


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
    hotkey: str = "<f8>"
    capture_scope: str = "all"
    min_ocr_confidence: float = 0.45
    speech_enabled: bool = True
    show_ipa: bool = False
    speech_voices: dict[str, str] = field(default_factory=dict)
    settings_window_size: list[int] | None = None
    settings_window_maximized: bool = False
    speech_speed: float = 1.0
    tray_close_notice_shown: bool = False


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
        if path.stat().st_size > 128 * 1024:
            return Settings()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return validate_settings(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return Settings()


def validate_settings(raw: object) -> Settings:
    defaults = Settings()
    if not isinstance(raw, dict):
        return defaults
    values = {key: value for key, value in raw.items() if key in Settings.__dataclass_fields__}
    languages = {code for _name, code in LANGUAGES}
    for key in ("source_language", "target_language"):
        if not isinstance(values.get(key), str) or values[key] not in languages:
            values[key] = getattr(defaults, key)
    try:
        values["hotkey"] = normalize_hotkey(values.get("hotkey"))
    except ValueError:
        values["hotkey"] = defaults.hotkey
    if values.get("capture_scope") not in ("all", "current"):
        values["capture_scope"] = defaults.capture_scope
    for key in ("speech_enabled", "show_ipa", "settings_window_maximized", "tray_close_notice_shown"):
        if type(values.get(key)) is not bool:
            values[key] = getattr(defaults, key)
    for key, lower, upper in (("min_ocr_confidence", 0, 1), ("speech_speed", .5, 1.5)):
        value = values.get(key)
        if (type(value) not in (int, float) or not lower <= value <= upper
                or not math.isfinite(value)):
            values[key] = getattr(defaults, key)
    preferences = values.get("speech_voices")
    values["speech_voices"] = {
        code: voice for code, voice in preferences.items()
        if code in languages and isinstance(voice, str) and 0 < len(voice) <= 128
    } if isinstance(preferences, dict) else {}
    size = values.get("settings_window_size")
    if not (isinstance(size, list) and len(size) == 2
            and all(type(value) is int and 0 < value <= 16777215 for value in size)):
        values["settings_window_size"] = None
    return Settings(**values)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(asdict(settings), handle, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

