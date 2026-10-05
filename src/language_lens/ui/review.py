from __future__ import annotations

from collections.abc import Iterable
import html
import json
from threading import Event

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
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QCloseEvent, QCursor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
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
from language_lens.domain import OcrLine, Rect, WordHit, WordTranslation, build_word_hits
from language_lens.services.ocr import RapidOcrEngine
from language_lens.services.translation import ArgosTranslator, TranslationUnavailable
from language_lens.services.speech import SpeechJob, SpeechPlayer
from language_lens.services.voices import MAX_TEXT_LENGTH, runtime_ready, selected_voice, voice_present
from language_lens.ui.word_popup import WordPopup


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
    def __init__(self, lines: list[OcrLine], words: Iterable[str], settings: Settings,
                 *, translator: ArgosTranslator | None = None, cancelled: Event | None = None) -> None:
        super().__init__()
        self.lines = lines
        self.words = tuple(dict.fromkeys(words))
        self.settings = settings
        self.signals = TaskSignals()
        self.translator = translator
        self.cancelled = cancelled or Event()

    def run(self) -> None:
        try:
            if self.cancelled.is_set():
                return
            translator = self.translator or ArgosTranslator()
            sentence = " ".join(line.text for line in self.lines)
            sentence_translation = translator.translate(
                sentence, self.settings.source_language, self.settings.target_language
            )
            translations = {}
            self.signals.result.emit((sentence_translation, {}))
            for word in self.words:
                if self.cancelled.is_set():
                    return
                try:
                    translations[word] = translator.word_candidates(
                        word, self.settings.source_language, self.settings.target_language
                    )
                except TranslationUnavailable:
                    translations[word] = WordTranslation((), "Translation unavailable for this word.")
                # Qt queues signals across threads: emit a snapshot, not a mutating dict.
                self.signals.result.emit((sentence_translation, dict(translations)))
        except Exception as exc:
            self.signals.error.emit(str(exc))


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
            error = str(exc) or "Could not load more candidates. Please retry."
        if not self.cancelled.is_set():
            self.signals.result.emit((self.word, result, error))


class ImageCanvas(QWidget):
    word_audio_requested = Signal(object)
    pronunciation_retry_requested = Signal()
    more_candidates_requested = Signal(str)

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
        self._pinned = False
        self.candidates_enabled = True
        self._expanded_translations: dict[str, WordTranslation] = {}
        self._candidate_lists_visible: set[str] = set()
        self._candidate_loading: set[str] = set()
        self._candidate_errors: dict[str, str] = {}
        self._popup_word: str | None = None
        self._pronunciations: dict[tuple[int, int], dict] = {}
        self._show_ipa = False
        self._audio_enabled = False
        self._voice_name = ""
        self._pronunciation_message = ""
        self._pronunciation_failed = False
        self._playback_state = "idle"
        self._active_word: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(480, 260)

        self._bubble_parent = overlay_parent or self
        self._bubble = WordPopup(self._bubble_parent)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(400)
        self._hide_timer.timeout.connect(self._hide_if_outside)
        self._bubble.entered.connect(self._hide_timer.stop)
        self._bubble.left.connect(self._schedule_hide)
        self._bubble.dismissed.connect(self.dismiss_word)
        self._bubble.play_requested.connect(self._request_word_audio)
        self._bubble.retry_requested.connect(self.pronunciation_retry_requested)
        self._bubble.more_requested.connect(self._toggle_candidates)

    def set_tooltip_avoid_rect(self, rect: QRect) -> None:
        if rect == self._tooltip_avoid_rect:
            return
        self._tooltip_avoid_rect = QRect(rect)
        self._refresh_bubble()

    def set_hits(self, hits: list[WordHit]) -> None:
        self._hits = hits
        self.update()

    def set_translations(self, translations: dict[str, WordTranslation]) -> None:
        span = self._span(self._hovered) if self._hovered else None
        self._hits = [
            hit.with_translation(translations.get(hit.lookup_text, hit.translation)) for hit in self._hits
        ]
        self._hovered = next((hit for hit in self._hits if self._span(hit) == span), None)
        self._refresh_bubble()
        self.update()

    def _toggle_candidates(self) -> None:
        if self._hovered is None or not self.candidates_enabled:
            return
        word = self._hovered.lookup_text
        self._pinned = True
        self._hide_timer.stop()
        compact = self._hovered.translation
        showing = word in self._candidate_lists_visible
        if word in self._expanded_translations:
            if showing:
                self._candidate_lists_visible.remove(word)
            else:
                self._candidate_lists_visible.add(word)
            self._refresh_bubble()
        elif not showing and compact is not None and len(compact.candidates) > 1:
            self._candidate_lists_visible.add(word)
            self._refresh_bubble()
        elif word not in self._candidate_loading:
            self._candidate_lists_visible.add(word)
            self._candidate_loading.add(word)
            self._candidate_errors.pop(word, None)
            self._refresh_bubble()
            self.more_candidates_requested.emit(word)

    def set_more_candidates(self, word: str, result: WordTranslation | None, error: str = "") -> None:
        self._candidate_loading.discard(word)
        if result is not None and result.candidates:
            self._expanded_translations[word] = result
            self._candidate_lists_visible.add(word)
            self._candidate_errors.pop(word, None)
        else:
            self._candidate_errors[word] = error or "No candidates returned. Please retry."
        if self._hovered and self._hovered.lookup_text == word:
            self._refresh_bubble()

    @staticmethod
    def _span(hit: WordHit) -> tuple[int, int]:
        return hit.source_start, hit.source_end

    def configure_pronunciation(self, show_ipa: bool, audio_enabled: bool, voice_name: str) -> None:
        self._show_ipa, self._audio_enabled, self._voice_name = show_ipa, audio_enabled, voice_name

    def set_pronunciations(self, words: list[dict], message: str = "", failed: bool = False) -> None:
        self._pronunciations = {(word["start"], word["end"]): word for word in words}
        self._pronunciation_message = message
        self._pronunciation_failed = failed
        self._refresh_bubble()

    def set_playback(self, state: str, active_word: tuple[int, int] | None) -> None:
        self._playback_state, self._active_word = state, active_word
        self._refresh_bubble()

    def _request_word_audio(self) -> None:
        if self._hovered is not None:
            self.word_audio_requested.emit(self._hovered)

    def _refresh_bubble(self) -> None:
        hit = self._hovered
        if hit is None:
            return
        bubble = self._bubble
        item = self._pronunciations.get(self._span(hit))
        bubble.word.setText(hit.text)
        word = hit.lookup_text
        expanded_result = self._expanded_translations.get(word)
        showing = word in self._candidate_lists_visible
        # Once a wider search has completed, its first result is the best match we
        # know about even while the rest of that list is collapsed.
        result = expanded_result or hit.translation
        bubble.set_translation(result, show_all=showing)
        count = len(expanded_result.candidates) if expanded_result else (
            len(hit.translation.candidates) if hit.translation else None
        )
        bubble.set_expansion_state(
            available=self.candidates_enabled and bool(result and result.candidates),
            loading=word in self._candidate_loading,
            showing=showing,
            searched=expanded_result is not None,
            count=count,
            error=self._candidate_errors.get(word, ""),
        )
        bubble.ipa.setVisible(self._show_ipa and bool(item and item["ipa"]))
        bubble.ipa.setText(f'[{item["ipa"]}]' if item and item["ipa"] else "")
        detail = self._pronunciation_message
        if item:
            detail = {"context": "From selected sentence", "isolated": "Word in isolation",
                      "unavailable": "Pronunciation unavailable"}[item["mode"]]
            if self._show_ipa and item["ipa"]:
                detail = "Estimated IPA · " + detail.lower()
            bubble.detail.setToolTip(item.get("reason") or
                "Mapped from the selected sentence. The engine can still misread ambiguous words.")
        else:
            bubble.detail.setToolTip(detail)
        bubble.detail.setText(detail)
        bubble.detail.setVisible(bool(detail) and (self._show_ipa or self._audio_enabled))
        bubble.voice.setText(self._voice_name)
        bubble.voice.setVisible(bool(self._voice_name) and (self._show_ipa or self._audio_enabled))
        busy = self._playback_state in ("generating", "loading", "playing", "stopping")
        own_audio = busy and self._active_word == self._span(hit)
        bubble.play.setVisible(self._audio_enabled)
        bubble.play.setText("Stop word" if own_audio else "Pronounce word")
        bubble.play.setEnabled(bool(item and item["phonemes"] and item["mode"] != "unavailable")
                               and (not busy or own_audio) and self._playback_state != "stopping")
        bubble.retry.setVisible(self._pronunciation_failed)
        bubble.fit_to_height(max(120, self.height() - 16))
        if word != self._popup_word:
            bubble.reset_scroll()
            self._popup_word = word
        bubble.move(self.mapTo(self._bubble_parent, self._bubble_position(self._source_to_display(hit.bounds))))
        bubble.show()
        bubble.raise_()

    def dismiss_word(self) -> None:
        self._hide_timer.stop()
        self._pinned = False
        self._hovered = None
        self._popup_word = None
        self._bubble.hide()
        self.update()

    def _schedule_hide(self) -> None:
        if not self._pinned and not self._hide_timer.isActive():
            self._hide_timer.start()

    def _hide_if_outside(self) -> None:
        if self._pinned:
            return
        cursor = QCursor.pos()
        if self._bubble.isVisible() and self._bubble.rect().contains(self._bubble.mapFromGlobal(cursor)):
            return
        source = self._display_to_source(QPointF(self.mapFromGlobal(cursor)))
        if source is not None and self._hovered and self._hovered.bounds.contains(source.x(), source.y()):
            return
        self.dismiss_word()

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

        for y in (above_y, below_y,
                  self._tooltip_avoid_rect.top() - bubble_height - 10,
                  self._tooltip_avoid_rect.bottom() + 10):
            candidate = QRect(x, y, bubble_width, bubble_height)
            if (8 <= y <= max_y and not candidate.intersects(self._tooltip_avoid_rect)
                    and not QRectF(candidate).intersects(word_rect)):
                return QPoint(x, y)

        # Ranked alternatives plus IPA can be taller than either vertical gap.
        # Try beside both the word and controls before allowing any overlap.
        side_y = int(min(max(8, word_rect.center().y() - bubble_height / 2), max_y))
        for side_x in (int(max(word_rect.right(), self._tooltip_avoid_rect.right()) + 10),
                       int(min(word_rect.left(), self._tooltip_avoid_rect.left()) - bubble_width - 10)):
            candidate = QRect(side_x, side_y, bubble_width, bubble_height)
            if (8 <= side_x <= max_x and not candidate.intersects(self._tooltip_avoid_rect)
                    and not QRectF(candidate).intersects(word_rect)):
                return QPoint(side_x, side_y)

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
        if self._pinned:
            return
        source = self._display_to_source(event.position())
        hovered = None
        if source is not None:
            hovered = next(
                (hit for hit in self._hits if hit.bounds.contains(source.x(), source.y())), None
            )
        if hovered is None:
            self._schedule_hide()
            return
        self._hide_timer.stop()
        if hovered == self._hovered:
            return
        self._hovered = hovered
        self._refresh_bubble()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        source = self._display_to_source(event.position())
        hit = next((hit for hit in self._hits if source is not None
                    and hit.bounds.contains(source.x(), source.y())), None)
        if hit is None:
            self.dismiss_word()
            return
        self._hovered, self._pinned = hit, True
        self._hide_timer.stop()
        self._refresh_bubble()
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._schedule_hide()
        super().leaveEvent(event)


class ReviewWindow(QWidget):
    finished = Signal()

    def __init__(self, pixmap: QPixmap, selection: QRect, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self._closed = False
        self._translator = ArgosTranslator()
        self._translation_cancelled = Event()
        self.speech = SpeechPlayer(self)
        self._speech_text = ""
        self._voice = selected_voice(settings.source_language, settings.speech_voices)
        self._prepared: dict | None = None
        self._active_word: tuple[int, int] | None = None
        self.pronunciation_job = SpeechJob(self)
        self.pronunciation_job.succeeded.connect(self._pronunciation_finished)
        self.pronunciation_job.failed.connect(self._pronunciation_failed)
        self._lines: list[OcrLine] = []
        self._hits: list[WordHit] = []
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setObjectName("reviewWindow")

        self._selection = QRect(selection)
        self._pixmap_size = pixmap.size()
        self.canvas = ImageCanvas(pixmap, selection, self)
        self.canvas.candidates_enabled = settings.source_language != settings.target_language
        self.canvas.word_audio_requested.connect(self._read_word)
        self.canvas.pronunciation_retry_requested.connect(self._prepare_pronunciation)
        self.canvas.more_candidates_requested.connect(self._request_more_candidates)
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
        self.read_button = QPushButton("Read selection")
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self._read_selection)
        self.speech_status = QLabel()
        self.speech_status.setObjectName("note")
        self.speech_status.setTextFormat(Qt.TextFormat.PlainText)
        self.speech_status.setWordWrap(True)
        self.speech.changed.connect(self._speech_changed)
        button_row.addWidget(self.read_button)
        button_row.addStretch()
        button_row.addWidget(close_button)
        footer_layout.addWidget(self.speech_status)
        footer_layout.addLayout(button_row)

        self._footer = footer
        footer.setParent(self)
        self._refresh_speech()

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
        if self._closed:
            return
        self._lines = [
            line.map_geometry(
                lambda x, y: (x + self._selection.x(), y + self._selection.y())
            )
            for line in result
        ]
        self._hits = build_word_hits(self._lines, self.settings.source_language)
        self.canvas.set_hits(self._hits)
        self._speech_text = " ".join(line.text for line in self._lines)
        self._refresh_speech()
        self._prepare_pronunciation()
        self._position_children()
        if not self._lines:
            self.status.setText(
                "No text found after a second enlarged scan. Try including a little "
                "space around the text, or select a clearer/larger version."
            )
            return
        self.status.setText(
            f"Found {len(self._hits)} words. Hover for details; click a word to keep them open."
        )
        task = TranslationTask(
            self._lines, (hit.lookup_text for hit in self._hits), self.settings,
            translator=self._translator, cancelled=self._translation_cancelled,
        )
        task.signals.result.connect(self._translation_finished)
        task.signals.error.connect(self._failed)
        QThreadPool.globalInstance().start(task)

    def _translation_finished(self, result: object) -> None:
        if self._closed:
            return
        sentence, translations = result
        self.canvas.set_translations(translations)
        self.translation.setText(f"<b>Whole selection:</b> {html.escape(sentence)}")
        self.translation.show()
        self._position_children()

    def _request_more_candidates(self, word: str) -> None:
        if self._closed:
            return
        task = MoreCandidatesTask(word, self.settings, self._translator, self._translation_cancelled)
        task.signals.result.connect(self._more_candidates_finished)
        QThreadPool.globalInstance().start(task)

    def _more_candidates_finished(self, result: object) -> None:
        if not self._closed:
            word, translation, error = result
            self.canvas.set_more_candidates(word, translation, error)

    def _failed(self, message: str) -> None:
        if self._closed:
            return
        self.status.setText(f"Could not finish: {message}")

    def _refresh_speech(self) -> None:
        message = ""
        ready = False
        if not self.settings.speech_enabled:
            message = "Pronunciation is off in Settings."
        elif self._voice is None:
            message = "No pronunciation voice is available for this text language yet."
        elif not runtime_ready():
            message = "Restart with Start Language Lens.bat to install speech components."
        elif not voice_present(self._voice):
            message = "Download a pronunciation voice in Settings to read this text aloud."
        elif len(self._speech_text) > MAX_TEXT_LENGTH:
            message = "Select a shorter passage to read aloud (up to 2,000 characters)."
        elif self._speech_text.strip():
            ready = True
            message = self._voice.name
        self.read_button.setEnabled(ready)
        self.read_button.setText("Read selection")
        self.read_button.setToolTip("Read the original text aloud in the selected voice.")
        self.speech_status.setText(message)
        self.speech_status.setVisible(bool(message))

    def _read_selection(self) -> None:
        if self.speech.busy:
            self.speech.stop()
        elif self._voice is not None and self._speech_text:
            self._active_word = None
            if self._prepared is not None:
                self.speech.speak_phonemes(tuple(self._prepared["sentence_phonemes"]), self._voice,
                                          (self._speech_text, "selection"))
            else:
                self.speech.speak(self._speech_text, self._voice)

    def _prepare_pronunciation(self) -> None:
        if self._closed or self.pronunciation_job.active:
            return
        has_runtime = runtime_ready()
        audio_available = bool(self.settings.speech_enabled and has_runtime and self._voice
                               and voice_present(self._voice))
        self.canvas.configure_pronunciation(
            self.settings.show_ipa, audio_available, self._voice.name if self._voice else ""
        )
        if not self.settings.show_ipa and not audio_available:
            return
        if self._voice is None:
            self.canvas.set_pronunciations([], "IPA is not available for this text language yet.")
            return
        if not has_runtime:
            self.canvas.set_pronunciations([], "Restart with Start Language Lens.bat to install pronunciation components.")
            return
        if not self._speech_text.strip() or len(self._speech_text) > MAX_TEXT_LENGTH:
            self.canvas.set_pronunciations([], "IPA needs a selection of up to 2,000 characters.")
            return
        self._prepared = None
        self.canvas.set_pronunciations([], "Preparing pronunciation…")
        self.pronunciation_job.start(
            "pronunciation", self._voice, self._speech_text,
            spans=[[hit.source_start, hit.source_end] for hit in self._hits],
        )

    def _pronunciation_finished(self, directory) -> None:
        if self._closed:
            return
        try:
            result = json.loads((directory / "pronunciation.json").read_text(encoding="utf-8"))
            if (result["text"] != self._speech_text or result["voice_id"] != self._voice.id
                    or [(word["start"], word["end"]) for word in result["words"]]
                    != [(hit.source_start, hit.source_end) for hit in self._hits]):
                raise ValueError("Pronunciation does not match the current selection.")
            self._prepared = result
            self.canvas.set_pronunciations(result["words"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._pronunciation_failed(str(exc))

    def _pronunciation_failed(self, message: str) -> None:
        if not self._closed:
            self._prepared = None
            self.canvas.set_pronunciations([], f"Pronunciation unavailable: {message}", failed=True)

    def _read_word(self, hit: WordHit) -> None:
        if self._closed or not self.settings.speech_enabled or self._voice is None:
            return
        if self.speech.busy:
            if self._active_word == (hit.source_start, hit.source_end):
                self.speech.stop()
            return
        if self._prepared is None:
            return
        word = next((word for word in self._prepared["words"]
                     if (word["start"], word["end"]) == (hit.source_start, hit.source_end)), None)
        if word is None or word["mode"] == "unavailable" or not word["phonemes"]:
            return
        self._active_word = (hit.source_start, hit.source_end)
        self.speech.speak_phonemes((word["phonemes"],), self._voice,
                                  (self._speech_text, *self._active_word))

    def _speech_changed(self, state: str, message: str) -> None:
        if self._closed:
            return
        self.canvas.set_playback(state, self._active_word)
        self._refresh_speech()
        if self.speech.busy:
            self.read_button.setText("Cancel audio" if state == "generating" else "Stop audio")
            self.read_button.setEnabled(state != "stopping")
        if message:
            self.speech_status.setText("Pronouncing word…" if state == "playing" and self._active_word else message)
            self.speech_status.show()
        self._position_children()

    def _position_children(self) -> None:
        """Anchor controls beside the selected text without covering it."""
        self.canvas.setGeometry(self.rect())
        selection_rect = self.canvas.selection_display_rect()
        margin = 22
        gap = 14
        available_width = max(1, self.width() - margin * 2)
        preferred_width = max(520, int(round(selection_rect.width())))
        footer_width = min(900, available_width, preferred_width)
        self._footer.setFixedWidth(footer_width)
        self._footer.layout().activate()
        available_height = max(1, self.height() - margin * 2)
        hint = self._footer.layout().heightForWidth(footer_width)
        footer_height = min(available_height, max(118, hint, self._footer.sizeHint().height()))

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
        if not self.canvas._bubble.isHidden():
            self.canvas._bubble.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._position_children()
        super().resizeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._closed = True
        self._translation_cancelled.set()
        self.shutdown_speech()
        self.canvas.dismiss_word()
        self.finished.emit()
        super().closeEvent(event)

    def shutdown_speech(self) -> None:
        self.pronunciation_job.shutdown()
        self.speech.shutdown()
        self._prepared = None

