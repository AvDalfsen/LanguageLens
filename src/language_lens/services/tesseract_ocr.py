"""Offline Russian OCR policy and native word geometry (no native GUI imports)."""
from __future__ import annotations

import os
from typing import Any

from language_lens.domain import OcrLine, OcrSpanBox
from language_lens.text import word_spans

# Exact official tessdata_best revision and hashes used in the upright benchmark.
MODEL_REVISION = "e12c65a915945e4c28e237a9b52bc4a8f39a0cec"
MODEL_SHA256 = {
    "rus": "b617eb6830ffabaaa795dd87ea7fd251adfe9cf0efe05eb9a2e8128b7728d6b6",
    "eng": "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba",
}


def russian_parameters() -> dict:
    return {"language": "rus+eng", "psm": 11, "scale": 2,
            "preprocessing": "dark-invert",
            "variables": {"load_system_dawg": "true", "load_freq_dawg": "true",
                          "thresholding_method": "2"}}


class TesseractOcrEngine:
    """The measured LSTM-only Russian/English pipeline, with source word boxes."""

    # Its benchmark did not use the RapidOCR padded empty-selection fallback.
    supports_empty_retry = False

    def __init__(self, source_language: str, *, params: dict) -> None:
        from language_lens.services.ocr import OcrUnavailable
        if source_language != "ru":
            raise ValueError("No tested Tesseract policy for this language.")
        os.environ.setdefault("OMP_THREAD_LIMIT", "2")
        try:
            import tesserocr
        except ImportError as exc:
            raise OcrUnavailable("Tesseract OCR is not installed.") from exc
        self.source_language = source_language
        self._api = tesserocr
        self._scale = params["scale"]
        self._preprocessing = params["preprocessing"]
        self._engine = tesserocr.PyTessBaseAPI(
            path=params["tessdata_path"], lang=params["language"],
            oem=tesserocr.OEM.LSTM_ONLY, psm=params["psm"], variables=params["variables"],
        )

    def recognize(self, image: Any, min_confidence: float | None = None) -> list[OcrLine]:
        """Accept BGR pixels; native scores are reported, without RapidOCR's floor.

        Tesseract scores are not calibrated to RapidOCR scores. The benchmark
        retained every recognized line; applying the neural confidence floor
        would introduce an untested pipeline.
        """
        import numpy as np
        from PIL import Image, ImageOps

        pixels = Image.fromarray(image[:, :, ::-1])
        if self._scale != 1:
            pixels = pixels.resize((round(pixels.width * self._scale),
                                    round(pixels.height * self._scale)), Image.Resampling.BICUBIC)
        if self._preprocessing == "dark-invert":
            gray = np.asarray(ImageOps.grayscale(pixels))
            edges = np.concatenate((gray[0], gray[-1], gray[:, 0], gray[:, -1]))
            if float(np.median(edges)) < 128:
                pixels = ImageOps.invert(pixels)
        self._engine.ClearAdaptiveClassifier()
        self._engine.SetImage(pixels)
        text = self._engine.GetUTF8Text().strip()
        if not text:
            return []
        iterator = self._engine.GetIterator()
        level = self._api.RIL
        spans, cursor, boxes = [], 0, []

        def polygon(box):
            x, y, right, bottom = (v / self._scale for v in box)
            return ((x, y), (right, y), (right, bottom), (x, bottom))

        while iterator is not None:
            try:
                word = (iterator.GetUTF8Text(level.WORD) or "").strip()
                box = iterator.BoundingBox(level.WORD)
            except RuntimeError:
                # Tesseract can return an iterator with no text on a blank image.
                word, box = "", None
            if word and box:
                boxes.append(box)
                start = text.find(word, cursor)
                if start >= 0:
                    cursor = start + len(word)
                    # Tesseract includes punctuation in a word. Bind its box to
                    # the app's lexical spans so punctuation cannot force the
                    # hover builder back to whole-block font geometry.
                    spans.extend(OcrSpanBox(start + left, start + right, polygon(box))
                                 for left, right in word_spans(word, self.source_language))
            if not iterator.Next(level.WORD):
                break
        bounds = ((min(b[0] for b in boxes), min(b[1] for b in boxes),
                   max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes
                  else (0, 0, pixels.width, pixels.height))
        confidence = max(0., min(1., self._engine.MeanTextConf() / 100))
        # Keep the native block's reading order: sorting its lines geometrically
        # changes sparse-layout transcripts. Hover uses the individual word boxes.
        return [OcrLine(text=text, confidence=confidence, polygon=polygon(bounds),
                        token_spans=tuple(word_spans(text, self.source_language)), span_boxes=tuple(spans))]
