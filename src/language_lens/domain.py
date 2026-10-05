from __future__ import annotations

from dataclasses import dataclass, replace
import unicodedata
from typing import Callable, Iterable

import regex

from language_lens.text import normalize_lookup_word, word_spans


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
class OcrSpanBox:
    """OCR geometry aligned to source-character offsets within one line."""

    start: int
    end: int
    polygon: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class OcrLine:
    text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]
    span_boxes: tuple[OcrSpanBox, ...] = ()
    token_spans: tuple[tuple[int, int], ...] | None = None

    @property
    def bounds(self) -> Rect:
        xs = [point[0] for point in self.polygon]
        ys = [point[1] for point in self.polygon]
        return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def map_geometry(self, transform: Callable[[float, float], tuple[float, float]]) -> "OcrLine":
        """Apply crop/scale transforms to the line and its aligned OCR boxes."""
        return replace(
            self,
            polygon=tuple(transform(x, y) for x, y in self.polygon),
            span_boxes=tuple(
                replace(box, polygon=tuple(transform(x, y) for x, y in box.polygon))
                for box in self.span_boxes
            ),
        )


@dataclass(frozen=True, slots=True)
class WordTranslation:
    """Distinct candidates in model rank order; note explains degraded results."""

    candidates: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True, slots=True)
class WordHit:
    text: str
    lookup_text: str
    bounds: Rect
    line_index: int
    translation: WordTranslation | None = None
    source_start: int = -1
    source_end: int = -1

    def with_translation(self, translation: WordTranslation | None) -> "WordHit":
        return replace(self, translation=translation)


def _is_rtl(text: str) -> bool:
    first = next((unicodedata.bidirectional(c) for c in text
                  if unicodedata.bidirectional(c) in {"L", "R", "AL"}), "L")
    return first in {"R", "AL"}


def _span_ratios(text: str, spans: tuple[tuple[int, int], ...], vertical: bool):
    """Shape the fallback with Qt, including bidi runs and proportional fonts.

    The screenshot's exact font is unknown. Recognizer coordinates take priority;
    these ratios are only an estimate when the model cannot supply usable boxes.
    """
    if not spans:
        return []
    if not vertical:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont, QGuiApplication, QTextLayout, QTextOption

        if isinstance(QGuiApplication.instance(), QGuiApplication):
            font = QFont("Segoe UI")
            font.setPixelSize(24)
            layout = QTextLayout(text, font)
            options = QTextOption()
            options.setWrapMode(QTextOption.WrapMode.NoWrap)
            options.setAlignment(Qt.AlignmentFlag.AlignLeft)
            options.setTextDirection(Qt.LayoutDirection.LayoutDirectionAuto)
            layout.setTextOption(options)
            layout.beginLayout()
            shaped = layout.createLine()
            shaped.setLineWidth(1_000_000)
            layout.endLayout()
            utf16 = [0]
            for character in text:
                utf16.append(utf16[-1] + (2 if ord(character) > 0xFFFF else 1))
            full = shaped.naturalTextRect()
            ratios = []
            for start, end in spans:
                runs = shaped.glyphRuns(utf16[start], utf16[end] - utf16[start])
                rectangles = [run.boundingRect() for run in runs if run.boundingRect().width() > 0]
                if not rectangles or full.width() <= 0:
                    break
                left = min(rect.left() for rect in rectangles)
                right = max(rect.right() for rect in rectangles)
                ratios.append((max(0.0, (left - full.left()) / full.width()),
                               min(1.0, (right - full.left()) / full.width())))
            if len(ratios) == len(spans):
                return ratios
    # Fontless callers and vertical text use graphemes, never code-point counts.
    edges = [0.0] * (len(text) + 1)
    advance = 0.0
    for cluster in regex.finditer(r"\X", text):
        for index in range(cluster.start(), cluster.end()):
            edges[index] = advance
        advance += 2.0 if unicodedata.east_asian_width(cluster.group()[0]) in {"W", "F"} else 1.0
        edges[cluster.end()] = advance
    ratios = [(edges[start] / max(advance, 1), edges[end] / max(advance, 1)) for start, end in spans]
    return [(1 - right, 1 - left) for left, right in ratios] if _is_rtl(text) and not vertical else ratios


def _project_span(line: OcrLine, left: float, right: float, vertical: bool) -> Rect:
    """Project onto the line quadrilateral, including rotated/vertical text."""
    if len(line.polygon) == 4:
        a, b, c, d = line.polygon
        if vertical:
            a, b, c, d = a, d, c, b
        def point(first, last, ratio):
            return tuple(first[i] + (last[i] - first[i]) * ratio for i in (0, 1))
        points = (point(a, b, left), point(a, b, right), point(d, c, right), point(d, c, left))
        xs, ys = zip(*points)
        return Rect(min(xs), min(ys), max(max(xs) - min(xs), 1), max(max(ys) - min(ys), 1))
    bounds = line.bounds
    if vertical:
        return Rect(bounds.x, bounds.y + bounds.height * left, bounds.width, bounds.height * (right - left))
    return Rect(bounds.x + bounds.width * left, bounds.y, bounds.width * (right - left), bounds.height)


def _ocr_word_rect(line: OcrLine, start: int, end: int) -> Rect | None:
    boxes = [box for box in line.span_boxes if start <= box.start < box.end <= end]
    covered = {i for box in boxes for i in range(box.start, box.end)}
    if not boxes or any(i not in covered for i in range(start, end)
                        if unicodedata.category(line.text[i])[0] in "LMN"):
        return None
    xs, ys = zip(*(point for box in boxes for point in box.polygon))
    return Rect(min(xs), min(ys), max(max(xs) - min(xs), 1), max(max(ys) - min(ys), 1))


def build_word_hits(lines: Iterable[OcrLine], source_language: str | None = None) -> list[WordHit]:
    """Use language-aware source spans and OCR geometry, with a shaped fallback."""
    hits: list[WordHit] = []
    source_offset = 0
    for line_index, line in enumerate(lines):
        text = line.text
        line_start = source_offset
        source_offset += len(line.text) + 1  # same single-space join as speech/translation
        if not text:
            continue
        spans = line.token_spans if line.token_spans is not None else tuple(word_spans(text, source_language))
        vertical = line.bounds.height > line.bounds.width * 1.5
        rectangles = {span: _ocr_word_rect(line, *span) for span in spans}
        missing = tuple(span for span in spans if rectangles[span] is None)
        for span, (left, right) in zip(missing, _span_ratios(text, missing, vertical)):
            rectangles[span] = _project_span(line, left, right, vertical)
        for start, end in spans:
            word = text[start:end]
            hits.append(
                WordHit(
                    text=word,
                    lookup_text=normalize_lookup_word(word),
                    bounds=rectangles[(start, end)],
                    line_index=line_index,
                    source_start=line_start + start,
                    source_end=line_start + end,
                )
            )
    return hits


def suppress_contained_ocr_fragments(
    lines: Iterable[OcrLine], source_language: str | None = None
) -> list[OcrLine]:
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
    return reading_order(kept, source_language)


def reading_order(lines: Iterable[OcrLine], source_language: str | None = None) -> list[OcrLine]:
    """Group physical rows, then respect their text direction."""
    candidates = list(lines)
    if (source_language in {"ja", "zh"} and candidates
            and all(line.bounds.height > line.bounds.width * 1.5 for line in candidates)):
        return sorted(candidates, key=lambda line: (-line.bounds.x, line.bounds.y))
    rows: list[list[OcrLine]] = []
    for line in sorted(candidates, key=lambda line: (line.bounds.y, line.bounds.x)):
        bounds = line.bounds
        row = next((row for row in rows if abs(
            bounds.y + bounds.height / 2 - row[0].bounds.y - row[0].bounds.height / 2
        ) <= min(bounds.height, row[0].bounds.height) * 0.5), None)
        if row is None:
            rows.append([line])
        else:
            row.append(line)
    return [line for row in rows for line in sorted(
        row, key=lambda line: line.bounds.x,
        reverse=source_language == "ar" or _is_rtl(" ".join(line.text for line in row)),
    )]

