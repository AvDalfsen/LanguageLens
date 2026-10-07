"""Domain task requests and OCR processing shared by Qt and isolated workers."""
from __future__ import annotations
from collections.abc import Iterable
from threading import Event
from dataclasses import asdict
from PySide6.QtCore import QObject, QPoint, QRect, QRunnable, QSize, Qt, Signal
from PySide6.QtGui import QImage
from language_lens.config import Settings
from language_lens.domain import OcrLine, WordTranslation, reading_order
from language_lens.services.capture import DesktopCapture
from language_lens.services.ocr import RapidOcrEngine
from language_lens.services.translation import ArgosTranslator
from language_lens.services.offline import local_ocr_parameters
from language_lens.services.errors import describe_failure


def create_ocr_engine(settings, engine_factory=None):
    return (engine_factory or RapidOcrEngine)(settings.source_language,
        params=local_ocr_parameters(settings.source_language))


class TaskSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(str)


def qimage_to_bgr_array(image: QImage):
    """Return an owned, contiguous uint8 BGR array for RapidOCR/OpenCV.

    Convert through Qt so screenshot formats/endianness are handled correctly;
    strip row padding before copying, and do not retain a view of Qt's buffer.
    """
    import numpy as np

    if image.isNull():
        raise ValueError("Cannot run OCR on an empty image.")
    converted = image.convertToFormat(QImage.Format.Format_BGR888)
    buffer = np.frombuffer(converted.bits(), dtype=np.uint8, count=converted.sizeInBytes())
    rows = buffer.reshape(converted.height(), converted.bytesPerLine())
    return rows[:, : converted.width() * 3].reshape(converted.height(), converted.width(), 3).copy()


class OcrTask(QRunnable):
    def __init__(
        self,
        image: QImage,
        settings: Settings,
        retry_image: QImage | None = None,
        retry_offset: QPoint | None = None,
        selection_size: QSize | None = None,
        retry_scale: float = 2.0,
    ) -> None:
        super().__init__()
        self.image = image
        self.settings = settings
        self.retry_image = retry_image
        self.retry_offset = QPoint(retry_offset) if retry_offset is not None else QPoint()
        self.selection_size = QSize(selection_size) if selection_size is not None else image.size()
        self.retry_scale = retry_scale
        self.signals = TaskSignals()

    def _map_retry_lines(self, lines: list[OcrLine]) -> list[OcrLine]:
        mapped: list[OcrLine] = []
        for line in lines:
            adjusted = line.map_geometry(
                lambda x, y: (
                    x / self.retry_scale + self.retry_offset.x(),
                    y / self.retry_scale + self.retry_offset.y(),
                )
            )
            bounds = adjusted.bounds
            center_x = bounds.x + bounds.width / 2
            center_y = bounds.y + bounds.height / 2
            if (
                0 <= center_x <= self.selection_size.width()
                and 0 <= center_y <= self.selection_size.height()
            ):
                mapped.append(adjusted)
        return mapped

    def recognize(self, engine, progress) -> list[OcrLine]:
        lines = engine.recognize(
            qimage_to_bgr_array(self.image), self.settings.min_ocr_confidence
        )
        if not lines and self.retry_image is not None:
            progress(
                "Nothing found on the first scan. Retrying with padding and enlargement…"
            )
            scaled_size = QSize(
                max(1, round(self.retry_image.width() * self.retry_scale)),
                max(1, round(self.retry_image.height() * self.retry_scale)),
            )
            enlarged = self.retry_image.scaled(
                scaled_size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            retry_lines = engine.recognize(
                qimage_to_bgr_array(enlarged), self.settings.min_ocr_confidence
            )
            lines = self._map_retry_lines(retry_lines)
        return lines

    def _create_engine(self):
        return create_ocr_engine(self.settings)

    def run(self) -> None:
        try:
            engine = self._create_engine()
            lines = recognize_regions([(self, (0, 0, 1, 1))], self.selection_size,
                                      engine, self.signals.progress.emit, self.settings.source_language)
            self.signals.result.emit(lines)
        except Exception as exc:
            self.signals.error.emit(describe_failure(exc, "ocr").message)


class NativeOcrTask(QRunnable):
    """OCR each monitor's unscaled selection, then map into logical coordinates.

    All QPixmap cropping happens in __init__ on the GUI thread. The worker
    receives only QImages, so no screen or GUI objects are used off-thread.
    """

    def __init__(self, capture: DesktopCapture, selection: QRect, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.signals = TaskSignals()
        self.selection = QRect(selection)
        self.regions = []
        padding = max(16, min(48, round(min(selection.width(), selection.height()) * 0.35)))
        padded = selection.adjusted(-padding, -padding, padding, padding)
        for screen in capture.screens:
            crop = capture.crop_screen(screen, selection)
            if crop is None:
                continue
            retry = capture.crop_screen(screen, padded)
            task = OcrTask(
                crop.image, settings, retry_image=retry.image,
                retry_offset=retry.native_rect.topLeft() - crop.native_rect.topLeft(),
                selection_size=crop.image.size(),
            )
            self.regions.append((crop, task))

    def _create_engine(self):
        return create_ocr_engine(self.settings)

    def run(self) -> None:
        try:
            if not self.regions:
                self.signals.result.emit([])
                return
            engine = self._create_engine()
            self.signals.result.emit(recognize_regions(ocr_regions(self), self.selection.size(),
                engine, self.signals.progress.emit, self.settings.source_language))
        except Exception as exc:
            self.signals.error.emit(describe_failure(exc, "ocr").message)


class TranslationTask(QRunnable):
    def __init__(self, lines: list[OcrLine], words: Iterable[str], settings: Settings,
                 *, translator: ArgosTranslator | None = None, cancelled: Event | None = None) -> None:
        super().__init__()
        self.lines = lines
        self.words = tuple(dict.fromkeys(words))
        self.settings = settings
        self.signals = TaskSignals()
        self.translator = translator
        self.cancelled = cancelled or Event()

    def _create_translator(self):
        return ArgosTranslator()

    def run(self) -> None:
        from language_lens.services.translation import selection_results
        for result in selection_results(self.translator or self._create_translator(),
                " ".join(line.text for line in self.lines), self.words,
                self.settings.source_language, self.settings.target_language,
                self.signals.progress.emit, self.cancelled.is_set):
            self.signals.result.emit(result)


class MoreCandidatesTask(QRunnable):
    def __init__(self, word: str, settings: Settings, translator: ArgosTranslator, cancelled: Event) -> None:
        super().__init__()
        self.word, self.settings, self.translator, self.cancelled = word, settings, translator, cancelled
        self.signals = TaskSignals()

    def run(self) -> None:
        if self.cancelled.is_set():
            return
        result, error = None, ""
        try:
            result = self.translator.word_candidates(
                self.word, self.settings.source_language, self.settings.target_language, expanded=True,
            )
        except Exception as exc:
            error = describe_failure(exc, "more").message
        if not self.cancelled.is_set():
            self.signals.result.emit((self.word, result, error))


def ocr_regions(task):
    if isinstance(task, NativeOcrTask):
        return [(region, (crop.logical_rect.x() - task.selection.x(),
                          crop.logical_rect.y() - task.selection.y(),
                          crop.logical_rect.width() / crop.image.width(),
                          crop.logical_rect.height() / crop.image.height()))
                for crop, region in task.regions]
    return [(task, (0, 0, 1, 1))]


def recognize_regions(regions, selection_size, engine, report, language):
    lines = []
    for task, (x, y, sx, sy) in regions:
        for line in task.recognize(engine, report):
            mapped = line.map_geometry(lambda px, py: (x + px * sx, y + py * sy))
            bounds = mapped.bounds
            # Native crops round outward; reject text centered outside selection.
            if (0 <= bounds.x + bounds.width / 2 < selection_size.width()
                    and 0 <= bounds.y + bounds.height / 2 < selection_size.height()):
                lines.append(mapped)
    return reading_order(lines, language)


def encode_task(task):
    payload = {"settings": asdict(task.settings)}
    images = {}
    if isinstance(task, (NativeOcrTask, OcrTask)):
        command = "ocr"
        payload["regions"] = []
        for index, (region, mapping) in enumerate(ocr_regions(task)):
            original, retry = f"crop{index}.png", f"retry{index}.png"
            images[original] = region.image
            if region.retry_image is not None:
                images[retry] = region.retry_image
            payload["regions"].append({"image": original, "retry": retry if retry in images else None,
                "offset": [region.retry_offset.x(), region.retry_offset.y()],
                "size": [region.selection_size.width(), region.selection_size.height()],
                "retry_scale": region.retry_scale, "mapping": mapping})
        size = task.selection.size() if isinstance(task, NativeOcrTask) else task.selection_size
        payload["selection_size"] = [size.width(), size.height()]
    elif isinstance(task, TranslationTask):
        command = "translate"
        payload.update(text=" ".join(line.text for line in task.lines), words=task.words)
    elif isinstance(task, MoreCandidatesTask):
        command = "more"
        payload["word"] = task.word
    else:
        raise TypeError("Unsupported domain task.")
    return command, payload, images


