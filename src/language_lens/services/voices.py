"""Pinned, opt-in local voices. No networking or native speech imports on import."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from importlib.resources import files as resource_files
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import quote

from language_lens.config import settings_path

PIPER_VERSION = "1.8.0"
REVISION = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
REPOSITORY = "https://huggingface.co/rhasspy/piper-voices"
MAX_TEXT_LENGTH = 2000


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    locale: str
    language: str
    espeak: str
    directory: str
    sample: str
    # Filename, exact bytes, SHA-256 of the pinned upstream artifact.
    files: tuple[tuple[str, int, str], ...]
    phoneme_type: str = "espeak"
    license_note: str = "See upstream model card; redistribution review required."

    @property
    def total_bytes(self) -> int:
        return sum(size for _, size, _ in self.files)

    def url(self, filename: str, *, view: bool = False) -> str:
        action = "blob" if view else "resolve"
        return f"{REPOSITORY}/{action}/{REVISION}/{quote(self.directory + '/' + filename)}"


def _voice(id, name, locale, language, espeak, directory, sample, model_hash,
           config_size, config_hash, card_size, card_hash) -> Voice:
    return Voice(id, name, locale, language, espeak, directory, sample, (
        (id + ".onnx", 63201294, model_hash),
        (id + ".onnx.json", config_size, config_hash),
        ("MODEL_CARD", card_size, card_hash),
    ))


VOICES = (
    _voice("en_US-lessac-medium", "Lessac · English (US)", "en-US", "en", "en-us",
           "en/en_US/lessac/medium", "Hello! Select some text and I will read it aloud.",
           "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f",
           4885, "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0",
           351, "ce49eb457742208166d399a40cdec2c7fa9db77960930031564ab56f12882645"),
    _voice("en_GB-alan-medium", "Alan · English (UK)", "en-GB", "en", "en-gb-x-rp",
           "en/en_GB/alan/medium", "Hello! Select some text and I will read it aloud.",
           "0a309668932205e762801f1efc2736cd4b0120329622adf62be09e56339d3330",
           4888, "c0f0d124e5895c00e7c03b35dcc8287f319a6998a365b182deb5c8e752ee8c1e",
           320, "abcbc3e961124398911436acd9eaaa0ab167cdf221d5a24146aa08732c52630f"),
    _voice("pt_PT-tugão-medium", "Tugão · Portuguese (Portugal)", "pt-PT", "pt", "pt",
           "pt/pt_PT/tugão/medium", "Olá! Seleciona um texto e eu vou lê-lo em voz alta.",
           "223a7aaca69a155c61897e8ada7c3b13bc306e16c72dbb9c2fed733e2b0927d4",
           5026, "fe0918dfc0f1a89264a6eea4afe8e95d8e9fed3cc6c81b5c2f87fcb2b50c7320",
           282, "1d6c23095980c0c58a044f1cb23e26fdc1d27bd95b68db0b5b0c548788b99d50"),
    _voice("pt_BR-faber-medium", "Faber · Portuguese (Brazil)", "pt-BR", "pb", "pt-br",
           "pt/pt_BR/faber/medium", "Olá! Selecione um texto e eu vou ler em voz alta.",
           "858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7",
           4855, "7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f",
           279, "01f1a5bcfd0538782726059ae407eae9c2dd1b5b35f7298fd53a68de91afe563"),
)

# Metadata only: models stay opt-in downloads, never part of the application.
VOICES += tuple(
    Voice(**{**item, "files": tuple(tuple(file) for file in item["files"])})
    for item in json.loads(resource_files("language_lens").joinpath("data/voices.json").read_text(encoding="utf-8"))
)


def voice_by_id(voice_id: str) -> Voice:
    for voice in VOICES:
        if voice.id == voice_id:
            return voice
    raise ValueError("Choose an available pronunciation voice in 'Settings'.")


def voices_for(language: str) -> tuple[Voice, ...]:
    return tuple(voice for voice in VOICES if voice.language == language)


def selected_voice(language: str, preferences: dict[str, str]) -> Voice | None:
    choices = voices_for(language)
    return next((v for v in choices if v.id == preferences.get(language)),
                choices[0] if choices else None)


def voices_root() -> Path:
    return settings_path().parent / "voices"


def runtime_ready() -> bool:
    try:
        return version("piper-tts") == PIPER_VERSION
    except PackageNotFoundError:
        return False


def voice_runtime_ready(voice: Voice) -> bool:
    if not runtime_ready():
        return False
    if voice.phoneme_type == "japanese":
        from language_lens.services.language_packs import ready
        return ready("ja-speech")
    return True


def voice_present(voice: Voice, root: Path | None = None) -> bool:
    """Cheap UI check. The worker verifies hashes before every model load."""
    directory = (root or voices_root()) / voice.id
    try:
        return all((directory / name).stat().st_size == size for name, size, _ in voice.files)
    except OSError:
        return False


def valid_file(path: Path, size: int, sha256: str) -> bool:
    try:
        if path.stat().st_size != size:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == sha256
    except OSError:
        return False


def verified_model(voice: Voice, root: Path) -> Path:
    directory = root / voice.id
    if not all(valid_file(directory / name, size, checksum)
               for name, size, checksum in voice.files):
        raise ValueError("Voice files are missing or damaged. Use 'Download voice' or 'Check voice files' in 'Settings'.")
    return directory / (voice.id + ".onnx")
