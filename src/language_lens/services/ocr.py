from __future__ import annotations

import math
import unicodedata
from typing import Any

from language_lens.domain import OcrLine, OcrSpanBox, suppress_contained_ocr_fragments
from language_lens.text import normalized_offsets, word_spans


class OcrUnavailable(RuntimeError):
    pass


SCRIPT_BY_LANGUAGE = {
    "ar": "ARABIC",
    "el": "EL",
    "hi": "DEVANAGARI",
    # PP-OCRv5's CH model recognizes Chinese, English and Japanese; there is
    # no separate JAPAN recognition model in that generation.
    "ja": "CH",
    "ko": "KOREAN",
    "ru": "CYRILLIC",
    "uk": "CYRILLIC",
    "zh": "CH",
}


def _aligned_boxes(text: str, raw_boxes) -> tuple[OcrSpanBox, ...]:
    """Accept only an exact, complete textual alignment to the recognizer output."""
    normalized, offsets = normalized_offsets(text)
    cursor, boxes = 0, []
    for item in raw_boxes:
        if not isinstance(item, (tuple, list)) or len(item) != 3 or not isinstance(item[0], str):
            return ()
        surface, _score, polygon = item
        surface = unicodedata.normalize("NFC", surface)
        if not surface or polygon is None:
            return ()
        start = normalized.find(surface, cursor)
        if start < 0 or any(unicodedata.category(c)[0] in "LMN" for c in normalized[cursor:start]):
            return ()
        end = start + len(surface)
        try:
            points = tuple((float(x), float(y)) for x, y in polygon)
        except (TypeError, ValueError):
            return ()
        if len(points) != 4 or not all(math.isfinite(v) for point in points for v in point):
            return ()
        xs, ys = zip(*points)
        if min(xs) >= max(xs) or min(ys) >= max(ys):
            return ()
        boxes.append(OcrSpanBox(offsets[start][0], offsets[end - 1][1], points))
        cursor = end
    if any(unicodedata.category(c)[0] in "LMN" for c in normalized[cursor:]):
        return ()
    return tuple(boxes)


def _attach_boxes(lines: list[OcrLine], word_results) -> list[OcrLine]:
    """Match by text and geometry, not indexes: RapidOCR can omit empty groups."""
    from dataclasses import replace

    assigned: dict[int, tuple[OcrSpanBox, ...]] = {}
    for group in word_results:
        if not isinstance(group, (tuple, list)) or not group:
            continue
        candidates = []
        for index, line in enumerate(lines):
            if index in assigned or any(unicodedata.bidirectional(c) in {"R", "AL"} for c in line.text):
                continue  # The upstream character-box projection assumes LTR text.
            boxes = _aligned_boxes(line.text, group)
            if not boxes:
                continue
            points = [point for box in boxes for point in box.polygon]
            center_x = sum(x for x, _y in points) / len(points)
            center_y = sum(y for _x, y in points) / len(points)
            bounds = line.bounds
            if not (bounds.x - 3 <= center_x <= bounds.right + 3
                    and bounds.y - 3 <= center_y <= bounds.bottom + 3):
                continue
            distance = ((center_x - bounds.x - bounds.width / 2) / max(bounds.width, 1)) ** 2
            distance += ((center_y - bounds.y - bounds.height / 2) / max(bounds.height, 1)) ** 2
            candidates.append((distance, index, boxes))
        if candidates:
            _distance, index, boxes = min(candidates, key=lambda candidate: candidate[0])
            assigned[index] = boxes
    return [replace(line, span_boxes=assigned.get(index, ())) for index, line in enumerate(lines)]


class RapidOcrEngine:
    """RapidOCR adapter configured for screen text in the selected script."""

    def __init__(self, source_language: str) -> None:
        try:
            from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        except ImportError as exc:  # pragma: no cover - exercised in installed app
            raise OcrUnavailable("RapidOCR is not installed.") from exc

        script_name = SCRIPT_BY_LANGUAGE.get(source_language, "LATIN")
        self.source_language = source_language
        # RapidOCR's supported character-box extraction is for Latin/Chinese
        # recognition; other scripts use the bidi-aware shaped fallback.
        self._return_character_boxes = script_name in {"LATIN", "CH"}
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
        result = self._engine(
            image, use_det=True, use_cls=True, use_rec=True,
            return_word_box=self._return_character_boxes,
            return_single_char_box=self._return_character_boxes,
        )
        boxes = result.boxes if result.boxes is not None else []
        texts = result.txts if result.txts is not None else []
        scores = result.scores if result.scores is not None else []
        lines = [
            OcrLine(
                text=str(text).strip(),
                confidence=float(score),
                polygon=tuple((float(x), float(y)) for x, y in box),
                token_spans=tuple(word_spans(str(text).strip(), self.source_language)),
            )
            for box, text, score in zip(boxes, texts, scores)
            if str(text).strip() and float(score) >= min_confidence
        ]
        word_results = getattr(result, "word_results", None)
        if word_results is not None:
            lines = _attach_boxes(lines, word_results)
        return suppress_contained_ocr_fragments(lines, self.source_language)

