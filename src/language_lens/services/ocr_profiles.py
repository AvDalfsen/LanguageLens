"""Recognition policy shared by inference, asset preparation and readiness.

Selection evidence and limits: docs/ocr-upright-selection.md, with earlier
evidence in docs/ocr-joint-selection.md. Keep this module
free of native imports: the GUI checks readiness without loading OCR models.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

# Keep the shared components identical to the fixed-model settings experiment.
# Strings keep policy identity available without loading the native runtime.
SHARED_MODELS = {"Det": ("PPOCRV6", "CH", "SMALL"),
                 "Cls": ("PPOCRV4", "CH", "MOBILE")}


@dataclass(frozen=True)
class OcrProfile:
    name: str
    generation: str
    script: str
    size: str
    backend: str = "rapidocr"

    @property
    def character_boxes(self) -> bool:
        # Other scripts retain the bidi-aware shaped geometry fallback.
        return self.script in {"LATIN", "CH", "EN"}

    def parameters(self) -> dict:
        if self.backend == "tesseract":
            from language_lens.services.tesseract_ocr import russian_parameters
            return russian_parameters()
        from rapidocr import EngineType, LangCls, LangDet, LangRec, ModelType, OCRVersion

        parameters = {"Rec.lang_type": getattr(LangRec, self.script),
                "Rec.model_type": getattr(ModelType, self.size),
                "Rec.ocr_version": getattr(OCRVersion, self.generation),
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.rec_batch_num": 6,
                "Global.text_score": .35, "Global.log_level": "critical",
                "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1}
        for section, (generation, script, size) in SHARED_MODELS.items():
            language = LangDet if section == "Det" else LangCls
            parameters.update({f"{section}.lang_type": getattr(language, script),
                               f"{section}.ocr_version": getattr(OCRVersion, generation),
                               f"{section}.model_type": getattr(ModelType, size),
                               f"{section}.engine_type": EngineType.ONNXRUNTIME})
        return parameters


LATIN_V5 = OcrProfile("latin-v5", "PPOCRV5", "LATIN", "MOBILE")
MULTILINGUAL_SMALL = OcrProfile("multilingual-v6-small", "PPOCRV6", "CH", "SMALL")
MULTILINGUAL_MEDIUM = OcrProfile("multilingual-v6-medium", "PPOCRV6", "CH", "MEDIUM")
CYRILLIC_V5 = OcrProfile("cyrillic-v5", "PPOCRV5", "CYRILLIC", "MOBILE")
TESSERACT_RUSSIAN = OcrProfile("tesseract-best-rus-eng", "TESSERACT5", "RUS_ENG", "BEST", "tesseract")

# Explicit language assignments, including the app's nb and pb aliases. CH is
# the catalogue key for the unified v6 recognizer, not a Chinese-only alphabet.
PROFILES_BY_LANGUAGE = {
    "ar": OcrProfile("arabic-v5", "PPOCRV5", "ARABIC", "MOBILE"),
    "zh": MULTILINGUAL_SMALL,
    "cs": MULTILINGUAL_SMALL,
    "da": MULTILINGUAL_SMALL,
    "nl": MULTILINGUAL_SMALL,
    "en": MULTILINGUAL_SMALL,
    "fi": MULTILINGUAL_SMALL,
    "fr": LATIN_V5,
    "de": LATIN_V5,
    "el": OcrProfile("greek-v5", "PPOCRV5", "EL", "MOBILE"),
    "hi": OcrProfile("hindi-v5", "PPOCRV5", "DEVANAGARI", "MOBILE"),
    "hu": MULTILINGUAL_MEDIUM,
    "it": LATIN_V5,
    "ja": MULTILINGUAL_SMALL,
    "ko": OcrProfile("korean-v5", "PPOCRV5", "KOREAN", "MOBILE"),
    "nb": MULTILINGUAL_SMALL,
    "pl": MULTILINGUAL_SMALL,
    "pt": LATIN_V5,
    "pb": MULTILINGUAL_SMALL,
    "ro": MULTILINGUAL_SMALL,
    "ru": TESSERACT_RUSSIAN,
    "es": LATIN_V5,
    "sv": MULTILINGUAL_SMALL,
    "tr": MULTILINGUAL_SMALL,
    "uk": CYRILLIC_V5,
}


def profile_for(language: str) -> OcrProfile:
    return PROFILES_BY_LANGUAGE.get(language, LATIN_V5)


def parameters_for(language: str) -> dict:
    """Combine the fixed recognizer with this language's measured settings."""
    from language_lens.services.ocr_settings import settings_for
    profile = profile_for(language)
    if profile.backend == "tesseract":
        return profile.parameters()
    return {**profile.parameters(), **settings_for(language).parameters()}


def policy_identity() -> str:
    """Invalidate prepared markers when models or measured settings change."""
    from language_lens.services.ocr_settings import settings_for
    assignments = {language: {"model": asdict(profile),
                              "settings": asdict(settings_for(language))}
                   for language, profile in sorted(PROFILES_BY_LANGUAGE.items())}
    from language_lens.services.tesseract_ocr import MODEL_SHA256, russian_parameters
    policy = {"shared_models": SHARED_MODELS, "languages": assignments,
              "tesseract": {"parameters": russian_parameters(), "models": MODEL_SHA256}}
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
