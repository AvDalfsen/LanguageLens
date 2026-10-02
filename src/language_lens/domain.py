from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.right and self.y <= y <= self.bottom


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]

    @property
    def bounds(self) -> Rect:
        xs = [point[0] for point in self.polygon]
        ys = [point[1] for point in self.polygon]
        return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


@dataclass(frozen=True, slots=True)
class WordHit:
    text: str
    lookup_text: str
    bounds: Rect
    line_index: int
    translation: str | None = None

    def with_translation(self, translation: str) -> "WordHit":
        return replace(self, translation=translation)


# Unicode letters/numbers, optionally joined by an apostrophe or hyphen.
WORD_PATTERN = re.compile(r"[^\W_]+(?:[’'\-][^\W_]+)*", re.UNICODE)


def normalize_lookup_word(word: str) -> str:
    """Trim punctuation while preserving meaningful internal apostrophes/hyphens."""
    match = WORD_PATTERN.search(word)
    return match.group(0).casefold() if match else word.casefold().strip()


def build_word_hits(lines: Iterable[OcrLine]) -> list[WordHit]:
    """Approximate word rectangles by projecting OCR character spans onto each line.

    RapidOCR gives reliable line polygons. Its character boxes are model-dependent, so
    horizontal screen text gets a deterministic proportional fallback here.
    """
    hits: list[WordHit] = []
    for line_index, line in enumerate(lines):
        text = line.text.strip()
        if not text:
            continue
        bounds = line.bounds
        span = max(len(text), 1)
        for match in WORD_PATTERN.finditer(text):
            left_ratio = match.start() / span
            right_ratio = match.end() / span
            x = bounds.x + bounds.width * left_ratio
            width = max(4.0, bounds.width * (right_ratio - left_ratio))
            word = match.group(0)
            hits.append(
                WordHit(
                    text=word,
                    lookup_text=normalize_lookup_word(word),
                    bounds=Rect(x, bounds.y, width, max(bounds.height, 4.0)),
                    line_index=line_index,
                )
            )
    return hits


def suppress_contained_ocr_fragments(lines: Iterable[OcrLine]) -> list[OcrLine]:
    """Remove small OCR results that duplicate part of a larger result.

    Decorative outlines and high-contrast glyphs can make a detector return both a
    word (for example ``Broke``) and a second one-letter box inside that word. A real
    adjacent one-letter word is retained because its center is outside the larger box.
    """
    candidates = list(lines)

    def character_count(line: OcrLine) -> int:
        return sum(character.isalnum() for character in line.text)

    def area(rect: Rect) -> float:
        return max(rect.width, 0.0) * max(rect.height, 0.0)

    def intersection_area(first: Rect, second: Rect) -> float:
        width = max(0.0, min(first.right, second.right) - max(first.x, second.x))
        height = max(0.0, min(first.bottom, second.bottom) - max(first.y, second.y))
        return width * height

    preferred = sorted(
        candidates,
        key=lambda line: (character_count(line), line.confidence, area(line.bounds)),
        reverse=True,
    )
    kept: list[OcrLine] = []
    for candidate in preferred:
        bounds = candidate.bounds
        candidate_area = area(bounds)
        if candidate_area <= 0:
            continue
        center_x = bounds.x + bounds.width / 2
        center_y = bounds.y + bounds.height / 2
        duplicate = any(
            dominant.bounds.contains(center_x, center_y)
            and intersection_area(bounds, dominant.bounds) / candidate_area >= 0.72
            and character_count(dominant) >= character_count(candidate)
            and dominant.confidence >= candidate.confidence - 0.25
            for dominant in kept
        )
        if not duplicate:
            kept.append(candidate)
    return reading_order(kept)


def reading_order(lines: Iterable[OcrLine]) -> list[OcrLine]:
    """Return lines in a stable top-to-bottom, left-to-right order."""
    return sorted(lines, key=lambda line: (round(line.bounds.y / 12), line.bounds.x))

