from __future__ import annotations

from typing import Any

from language_lens.domain import OcrLine, suppress_contained_ocr_fragments


class OcrUnavailable(RuntimeError):
    pass


SCRIPT_BY_LANGUAGE = {
    "ar": "ARABIC",
    "el": "EL",
    "hi": "DEVANAGARI",
    "ja": "JAPAN",
    "ko": "KOREAN",
    "ru": "CYRILLIC",
    "uk": "CYRILLIC",
    "zh": "CH",
}


class RapidOcrEngine:
    """RapidOCR adapter configured for screen text in the selected script."""

    def __init__(self, source_language: str) -> None:
        try:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        except ImportError as exc:  # pragma: no cover - exercised in installed app
            raise OcrUnavailable("RapidOCR is not installed.") from exc

        script_name = SCRIPT_BY_LANGUAGE.get(source_language, "LATIN")
        language = getattr(LangRec, script_name)
        self._engine = RapidOCR(
            params={
                "Rec.lang_type": language,
                "Rec.model_type": ModelType.MOBILE,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Global.text_score": 0.35,
            }
        )

    def recognize(self, image: Any, min_confidence: float = 0.45) -> list[OcrLine]:
        """Recognize an RGB numpy array and return filtered, ordered text lines."""
        result = self._engine(image, use_det=True, use_cls=True, use_rec=True)
        boxes = result.boxes if result.boxes is not None else []
        texts = result.txts if result.txts is not None else []
        scores = result.scores if result.scores is not None else []
        lines = [
            OcrLine(
                text=str(text).strip(),
                confidence=float(score),
                polygon=tuple((float(x), float(y)) for x, y in box),
            )
            for box, text, score in zip(boxes, texts, scores)
            if str(text).strip() and float(score) >= min_confidence
        ]
        return suppress_contained_ocr_fragments(lines)

