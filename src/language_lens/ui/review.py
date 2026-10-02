from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import (
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QColor, QCloseEvent, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from language_lens.config import Settings
from language_lens.domain import OcrLine, Rect, WordHit, build_word_hits
from language_lens.services.ocr import RapidOcrEngine
from language_lens.services.translation import ArgosTranslator


class TaskSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(str)


def qimage_to_rgb_array(image: QImage):
    import numpy as np

    converted = image.convertToFormat(QImage.Format.Format_RGB888)
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
            polygon = tuple(
                (
                    x / self.retry_scale + self.retry_offset.x(),
                    y / self.retry_scale + self.retry_offset.y(),
                )
                for x, y in line.polygon
            )
            adjusted = OcrLine(line.text, line.confidence, polygon)
            bounds = adjusted.bounds
            center_x = bounds.x + bounds.width / 2
            center_y = bounds.y + bounds.height / 2
            if (
                0 <= center_x <= self.selection_size.width()
                and 0 <= center_y <= self.selection_size.height()
            ):
                mapped.append(adjusted)
        return mapped

    def run(self) -> None:
        try:
            engine = RapidOcrEngine(self.settings.source_language)
            lines = engine.recognize(
                qimage_to_rgb_array(self.image), self.settings.min_ocr_confidence
            )
            if not lines and self.retry_image is not None:
                self.signals.progress.emit(
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
                    qimage_to_rgb_array(enlarged), self.settings.min_ocr_confidence
                )
                lines = self._map_retry_lines(retry_lines)
            self.signals.result.emit(lines)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class TranslationTask(QRunnable):
    def __init__(self, lines: list[OcrLine], words: Iterable[str], settings: Settings) -> None:
        super().__init__()
        self.lines = lines
        self.words = tuple(dict.fromkeys(words))
        self.settings = settings
        self.signals = TaskSignals()

    def run(self) -> None:
        try:
            translator = ArgosTranslator()
            sentence = " ".join(line.text for line in self.lines)
            sentence_translation = translator.translate(
                sentence, self.settings.source_language, self.settings.target_language
            )
            translations = {
                word: translator.translate(
                    word, self.settings.source_language, self.settings.target_language
                )
                for word in self.words
            }
            self.signals.result.emit((sentence_translation, translations))
        except Exception as exc:
            self.signals.error.emit(str(exc))


class ImageCanvas(QWidget):
    def __init__(
        self, pixmap: QPixmap, selection: QRect, overlay_parent: QWidget | None = None
    ) -> None:
        super().__init__(overlay_parent)
        self._pixmap = pixmap
        self._selection = QRect(selection)
        self._hits: list[WordHit] = []
        self._hovered: WordHit | None = None
        self._image_rect = QRectF()
        self._tooltip_avoid_rect = QRect()
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(480, 260)

        self._bubble_parent = overlay_parent or self
        self._bubble = QLabel(self._bubble_parent)
        self._bubble.setObjectName("translationBubble")
        self._bubble.setWordWrap(True)
        self._bubble.setMaximumWidth(360)
        self._bubble.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._bubble.hide()

    def set_tooltip_avoid_rect(self, rect: QRect) -> None:
        if rect == self._tooltip_avoid_rect:
            return
        self._tooltip_avoid_rect = QRect(rect)
        self._hovered = None
        self._bubble.hide()

    def set_hits(self, hits: list[WordHit]) -> None:
        self._hits = hits
        self.update()

    def set_translations(self, translations: dict[str, str]) -> None:
        self._hits = [
            hit.with_translation(translations.get(hit.lookup_text, hit.text)) for hit in self._hits
        ]
        self._hovered = None
        self._bubble.hide()
        self.update()

    def _calculate_image_rect(self) -> QRectF:
        if self._pixmap.isNull():
            return QRectF()
        available = self.rect()
        scaled = self._pixmap.size().scaled(
            available.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = available.x() + (available.width() - scaled.width()) / 2
        y = available.y() + (available.height() - scaled.height()) / 2
        return QRectF(x, y, scaled.width(), scaled.height())

    def _source_to_display(self, bounds) -> QRectF:
        if self._image_rect.isEmpty():
            return QRectF()
        sx = self._image_rect.width() / self._pixmap.width()
        sy = self._image_rect.height() / self._pixmap.height()
        return QRectF(
            self._image_rect.x() + bounds.x * sx,
            self._image_rect.y() + bounds.y * sy,
            bounds.width * sx,
            bounds.height * sy,
        )

    def selection_display_rect(self) -> QRectF:
        """Return the selected source area in this canvas's current coordinates."""
        self._image_rect = self._calculate_image_rect()
        return self._source_to_display(
            Rect(
                self._selection.x(),
                self._selection.y(),
                self._selection.width(),
                self._selection.height(),
            )
        )

    def _display_to_source(self, point: QPointF) -> QPointF | None:
        if not self._image_rect.contains(point):
            return None
        return QPointF(
            (point.x() - self._image_rect.x()) * self._pixmap.width() / self._image_rect.width(),
            (point.y() - self._image_rect.y()) * self._pixmap.height() / self._image_rect.height(),
        )

    def _bubble_position(self, word_rect: QRectF) -> QPoint:
        bubble_width = self._bubble.width()
        bubble_height = self._bubble.height()
        max_x = max(8, self.width() - bubble_width - 8)
        x = int(min(max(8, word_rect.center().x() - bubble_width / 2), max_x))
        above_y = int(word_rect.top() - bubble_height - 10)
        below_y = int(word_rect.bottom() + 10)
        max_y = max(8, self.height() - bubble_height - 8)

        for y in (above_y, below_y):
            candidate = QRect(x, y, bubble_width, bubble_height)
            if 8 <= y <= max_y and not candidate.intersects(self._tooltip_avoid_rect):
                return QPoint(x, y)

        # With very large selections there may be no collision-free side. The bubble
        # is a top-level review overlay, so this fallback remains visible over the panel.
        return QPoint(x, max(8, min(above_y, max_y)))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#07111f"))
        self._image_rect = self._calculate_image_rect()
        painter.drawPixmap(self._image_rect, self._pixmap, QRectF(self._pixmap.rect()))

        selection_rect = self.selection_display_rect()
        painter.setPen(QPen(QColor(94, 234, 212, 150), 1))
        painter.drawRect(selection_rect)

        for hit in self._hits:
            rect = self._source_to_display(hit.bounds)
            hovered = hit == self._hovered
            painter.fillRect(rect, QColor(94, 234, 212, 74 if hovered else 25))
            painter.setPen(QPen(QColor(94, 234, 212, 220 if hovered else 85), 2 if hovered else 1))
            painter.drawRect(rect)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        source = self._display_to_source(event.position())
        hovered = None
        if source is not None:
            hovered = next(
                (hit for hit in self._hits if hit.bounds.contains(source.x(), source.y())), None
            )
        if hovered == self._hovered:
            return
        self._hovered = hovered
        if hovered is None:
            self._bubble.hide()
        else:
            translation = hovered.translation or "Translating…"
            self._bubble.setText(f"<b>{hovered.text}</b><br>{translation}")
            self._bubble.adjustSize()
            word_rect = self._source_to_display(hovered.bounds)
            position = self._bubble_position(word_rect)
            overlay_position = self.mapTo(self._bubble_parent, position)
            self._bubble.move(overlay_position)
            self._bubble.raise_()
            self._bubble.show()
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = None
        self._bubble.hide()
        self.update()
        super().leaveEvent(event)


class ReviewWindow(QWidget):
    finished = Signal()

    def __init__(self, pixmap: QPixmap, selection: QRect, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._lines: list[OcrLine] = []
        self._hits: list[WordHit] = []
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setObjectName("reviewWindow")

        self._selection = QRect(selection)
        self._pixmap_size = pixmap.size()
        self.canvas = ImageCanvas(pixmap, selection, self)
        self.status = QLabel("Reading the selected text locally…")
        self.status.setObjectName("statusLabel")
        self.translation = QLabel("")
        self.translation.setObjectName("sentenceTranslation")
        self.translation.setWordWrap(True)
        self.translation.hide()
        close_button = QPushButton("Close and return   Esc")
        close_button.clicked.connect(self.close)

        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QVBoxLayout(footer)
        footer_layout.addWidget(self.status)
        footer_layout.addWidget(self.translation)
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(close_button)
        footer_layout.addLayout(button_row)

        self._footer = footer
        footer.setParent(self)

        padding = max(16, min(48, round(min(selection.width(), selection.height()) * 0.35)))
        retry_rect = selection.adjusted(-padding, -padding, padding, padding).intersected(
            pixmap.rect()
        )
        task = OcrTask(
            pixmap.copy(selection).toImage(),
            settings,
            retry_image=pixmap.copy(retry_rect).toImage(),
            retry_offset=retry_rect.topLeft() - selection.topLeft(),
            selection_size=selection.size(),
        )
        task.signals.result.connect(self._ocr_finished)
        task.signals.error.connect(self._failed)
        task.signals.progress.connect(self.status.setText)
        QThreadPool.globalInstance().start(task)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.showFullScreen()
        self.activateWindow()
        self.raise_()

    def _ocr_finished(self, result: object) -> None:
        self._lines = [
            OcrLine(
                text=line.text,
                confidence=line.confidence,
                polygon=tuple(
                    (x + self._selection.x(), y + self._selection.y())
                    for x, y in line.polygon
                ),
            )
            for line in result
        ]
        self._hits = build_word_hits(self._lines)
        self.canvas.set_hits(self._hits)
        if not self._lines:
            self.status.setText(
                "No text found after a second enlarged scan. Try including a little "
                "space around the text, or select a clearer/larger version."
            )
            return
        self.status.setText(
            f"Found {len(self._hits)} words. Hover over a word for its local translation."
        )
        task = TranslationTask(
            self._lines, (hit.lookup_text for hit in self._hits), self.settings
        )
        task.signals.result.connect(self._translation_finished)
        task.signals.error.connect(self._failed)
        QThreadPool.globalInstance().start(task)

    def _translation_finished(self, result: object) -> None:
        sentence, translations = result
        self.canvas.set_translations(translations)
        self.translation.setText(f"<b>Whole selection:</b> {sentence}")
        self.translation.show()
        self._position_children()

    def _failed(self, message: str) -> None:
        self.status.setText(f"Could not finish: {message}")

    def _position_children(self) -> None:
        """Anchor controls beside the selected text without covering it."""
        self.canvas.setGeometry(self.rect())
        selection_rect = self.canvas.selection_display_rect()
        margin = 22
        gap = 14
        available_width = max(1, self.width() - margin * 2)
        preferred_width = max(520, int(round(selection_rect.width())))
        footer_width = min(900, available_width, preferred_width)
        self._footer.adjustSize()
        available_height = max(1, self.height() - margin * 2)
        footer_height = min(available_height, max(118, min(190, self._footer.sizeHint().height())))

        footer_x = int(round(selection_rect.center().x() - footer_width / 2))
        footer_x = max(margin, min(footer_x, self.width() - margin - footer_width))

        above_y = int(selection_rect.top()) - gap - footer_height
        below_y = int(selection_rect.bottom()) + gap + 1
        selection_is_low = selection_rect.center().y() >= self.height() / 2
        footer_y = above_y if selection_is_low else below_y
        if footer_y < margin or footer_y + footer_height > self.height() - margin:
            footer_y = below_y if selection_is_low else above_y
        footer_y = max(margin, min(footer_y, self.height() - margin - footer_height))

        self._footer.setGeometry(
            footer_x,
            footer_y,
            footer_width,
            footer_height,
        )
        self._footer.raise_()
        self.canvas.set_tooltip_avoid_rect(
            self._footer.geometry().adjusted(-8, -8, 8, 8)
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._position_children()
        super().resizeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.finished.emit()
        super().closeEvent(event)

