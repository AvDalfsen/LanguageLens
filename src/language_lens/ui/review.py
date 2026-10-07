from __future__ import annotations

import html
import json
from threading import Event

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QCloseEvent, QCursor, QImage, QKeyEvent, QKeySequence, QShortcut, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QAbstractButton,
    QAbstractSlider,
    QBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from language_lens.config import Settings
from language_lens.domain import OcrLine, Rect, WordHit, WordTranslation, build_word_hits
from language_lens.services.capture import DesktopCapture
from language_lens.services.ocr import RapidOcrEngine
from language_lens.services.translation import ArgosTranslator, TranslationUnavailable
from language_lens.services.speech import SpeechJob, SpeechPlayer
from language_lens.services.jobs import TaskPool as QThreadPool
# Domain tasks retain their testable QRunnable interface; this dispatcher starts
# isolated QProcess workers, not Qt worker threads or native engines in the GUI.
from language_lens.services.voices import MAX_TEXT_LENGTH, runtime_ready, selected_voice, voice_present
from language_lens.ui.word_popup import WordPopup
from language_lens.ui.style import set_help
from language_lens.ui.sections import ExpandableSection, make_copyable
from language_lens.services.diagnostics import open_folder


class DraggablePanel(QFrame):
    """Move from non-interactive background without adding a drag toolbar."""

    moved = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._drag_point = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def enable_background_drag(self) -> None:
        # Scroll-area viewports and labels receive events before the frame.
        # Buttons/sliders/scrollbars keep their own cursor and mouse handling.
        for widget in self.findChildren(QWidget):
            if isinstance(widget, (QAbstractButton, QAbstractSlider)):
                widget.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                widget.installEventFilter(self)

    def _interactive_at(self, watched: QWidget, position: QPoint) -> bool:
        point = watched.mapTo(self, position)
        widget = self.childAt(point) or watched
        while widget is not None and widget is not self:
            if isinstance(widget, (QAbstractButton, QAbstractSlider)):
                return True
            if isinstance(widget, QLabel) and (widget.openExternalLinks() or widget.textInteractionFlags() & (
                    Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)):
                return True
            widget = widget.parentWidget()
        return False

    def _drag_event(self, watched: QWidget, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton or self._interactive_at(watched, event.position().toPoint()):
                return False
            self._drag_point = event.globalPosition().toPoint()
            self.grabMouse()
        elif kind == QEvent.Type.MouseMove and self._drag_point is not None:
            point = event.globalPosition().toPoint()
            self.moved.emit(point - self._drag_point)
            self._drag_point = point
        elif kind == QEvent.Type.MouseButtonRelease and self._drag_point is not None:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            self._end_drag()
        else:
            return False
        event.accept()
        return True

    def _end_drag(self) -> None:
        self._drag_point = None
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        return self._drag_event(watched, event) or super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._drag_event(self, event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._drag_event(self, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if not self._drag_event(self, event):
            super().mouseReleaseEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._end_drag()
        super().hideEvent(event)


# Keep these public task names for callers, while processing lives in services.
from language_lens.services import tasks as domain_tasks
from language_lens.services.tasks import TaskSignals, qimage_to_bgr_array, MoreCandidatesTask


class _OcrFactory:
    def _create_engine(self):
        return domain_tasks.create_ocr_engine(self.settings, engine_factory=RapidOcrEngine)


class OcrTask(_OcrFactory, domain_tasks.OcrTask):
    pass


class NativeOcrTask(_OcrFactory, domain_tasks.NativeOcrTask):
    pass


class TranslationTask(domain_tasks.TranslationTask):
    def _create_translator(self):
        return ArgosTranslator()


class ImageCanvas(QWidget):
    word_selected = Signal(object)
    word_audio_requested = Signal(object)
    pronunciation_retry_requested = Signal()
    more_candidates_requested = Signal(str)

    def __init__(
        self, pixmap: QPixmap | DesktopCapture, selection: QRect, overlay_parent: QWidget | None = None
    ) -> None:
        super().__init__(overlay_parent)
        self._pixmap = pixmap if isinstance(pixmap, QPixmap) else None
        self.capture: DesktopCapture | None = pixmap if isinstance(pixmap, DesktopCapture) else None
        self.viewport: QRect | None = None
        self.monitor_rects: tuple[QRect, ...] = ()
        self._selection = QRect(selection)
        self._hits: list[WordHit] = []
        self._word_indices: dict[str, list[int]] = {}
        self._span_indices: dict[tuple[int, int], int] = {}
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
        self.setAccessibleName("Captured screenshot")
        self.setAccessibleDescription("Hover over recognized words, or click one to pin its details. "
                                      "Use the left and right arrow keys to browse recognized words; Escape closes the screenshot.")
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
        self._bubble.search_requested.connect(self._search_candidates)

    def set_tooltip_avoid_rect(self, rect: QRect) -> None:
        if rect == self._tooltip_avoid_rect:
            return
        self._tooltip_avoid_rect = QRect(rect)
        self._refresh_bubble()

    def set_hits(self, hits: list[WordHit]) -> None:
        self.dismiss_word()
        self._expanded_translations.clear()
        self._candidate_lists_visible.clear()
        self._candidate_loading.clear()
        self._candidate_errors.clear()
        self._hits = list(hits)
        self._word_indices = {}
        self._span_indices = {}
        for index, hit in enumerate(hits):
            self._word_indices.setdefault(hit.lookup_text, []).append(index)
            self._span_indices.setdefault(self._span(hit), index)
        self.update()

    def set_translations(self, translations: dict[str, WordTranslation]) -> None:
        span = self._span(self._hovered) if self._hovered else None
        changed = False
        for word, translation in translations.items():
            for index in self._word_indices.get(word, ()):
                self._hits[index] = self._hits[index].with_translation(translation)
                changed = True
        if self._hovered and self._hovered.lookup_text in translations:
            index = self._span_indices.get(span)
            self._hovered = self._hits[index] if index is not None else None
            self._refresh_bubble()
        if changed:
            self.update()

    def _toggle_candidates(self) -> None:
        if self._hovered is None or not self.candidates_enabled:
            return
        word = self._hovered.lookup_text
        self._pinned = True
        self._hide_timer.stop()
        showing = word in self._candidate_lists_visible
        if showing:
            self._candidate_lists_visible.remove(word)
        else:
            self._candidate_lists_visible.add(word)
        self._refresh_bubble()

    def _search_candidates(self) -> None:
        if self._hovered is None or not self.candidates_enabled:
            return
        word = self._hovered.lookup_text
        if word not in self._candidate_loading and word not in self._expanded_translations:
            self._pinned = True
            self._hide_timer.stop()
            self._candidate_lists_visible.add(word)
            self._candidate_loading.add(word)
            self._candidate_errors.pop(word, None)
            self._refresh_bubble()
            self.more_candidates_requested.emit(word)

    def set_more_candidates(self, word: str, result: WordTranslation | None, error: str = "") -> None:
        was_loading = word in self._candidate_loading
        self._candidate_loading.discard(word)
        if result is not None and result.candidates:
            self._expanded_translations[word] = result
            if not was_loading:
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
        notes = item.get("ipa_notes", ()) if item else ()
        bubble.ipa.setToolTip("\n".join((
            "Estimated pronunciation, not a measurement of the voice's audio.",
            *notes,
            f'Original synthesis phonemes: [{item["phonemes"]}]' if item else "",
        )))
        detail = self._pronunciation_message
        if item:
            detail = {"context": "From selected sentence", "isolated": "Word in isolation",
                      "unavailable": "Pronunciation unavailable"}[item["mode"]]
            if self._show_ipa and item["ipa"]:
                notation = "Engine notation" if item.get("ipa_notation") == "engine" else "Estimated IPA"
                detail = notation + " · " + detail.lower()
            origin = item.get("reason") or (
                "Mapped from the selected sentence. The engine can still misread ambiguous words."
                if item["mode"] == "context" else "Generated for this word in isolation."
            )
            bubble.detail.setToolTip("\n".join((origin, *notes)))
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
        if self._source_size.isEmpty():
            return QRectF()
        available = self.rect()
        if self.viewport is not None:
            sx, sy = available.width() / self.viewport.width(), available.height() / self.viewport.height()
            return QRectF(-self.viewport.x() * sx, -self.viewport.y() * sy,
                          self._source_size.width() * sx, self._source_size.height() * sy)
        scaled = self._source_size.scaled(
            available.size(), Qt.AspectRatioMode.KeepAspectRatio
        )
        x = available.x() + (available.width() - scaled.width()) / 2
        y = available.y() + (available.height() - scaled.height()) / 2
        return QRectF(x, y, scaled.width(), scaled.height())

    @property
    def _source_size(self) -> QSize:
        return self.capture.size if self.capture is not None else self._pixmap.size()

    def _source_to_display(self, bounds) -> QRectF:
        if self._image_rect.isEmpty():
            return QRectF()
        sx = self._image_rect.width() / self._source_size.width()
        sy = self._image_rect.height() / self._source_size.height()
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
            (point.x() - self._image_rect.x()) * self._source_size.width() / self._image_rect.width(),
            (point.y() - self._image_rect.y()) * self._source_size.height() / self._image_rect.height(),
        )

    def monitor_display_rect(self, region: QRectF) -> QRect:
        """Keep controls on a real monitor, not in a virtual-desktop gap."""
        monitors = [self._source_to_display(Rect(r.x(), r.y(), r.width(), r.height())).intersected(QRectF(self.rect()))
                    for r in self.monitor_rects]
        monitors = [rect for rect in monitors if not rect.isEmpty()]
        if not monitors:
            return self.rect()
        chosen = next((rect for rect in monitors if rect.contains(region.center())), None)
        if chosen is None:
            chosen = max(monitors, key=lambda rect: (
                rect.intersected(region).width() * rect.intersected(region).height(),
                -(rect.center() - region.center()).manhattanLength(),
            ))
        return chosen.toAlignedRect().intersected(self.rect())

    def _bubble_position(self, word_rect: QRectF) -> QPoint:
        bubble_width = self._bubble.width()
        bubble_height = self._bubble.height()
        area = self.monitor_display_rect(word_rect)
        min_x, min_y = area.x() + 8, area.y() + 8
        max_x = max(min_x, area.x() + area.width() - bubble_width - 8)
        x = int(min(max(min_x, word_rect.center().x() - bubble_width / 2), max_x))
        above_y = int(word_rect.top() - bubble_height - 10)
        below_y = int(word_rect.bottom() + 10)
        max_y = max(min_y, area.y() + area.height() - bubble_height - 8)

        for y in (above_y, below_y,
                  self._tooltip_avoid_rect.top() - bubble_height - 10,
                  self._tooltip_avoid_rect.bottom() + 10):
            candidate = QRect(x, y, bubble_width, bubble_height)
            if (min_y <= y <= max_y and not candidate.intersects(self._tooltip_avoid_rect)
                    and not QRectF(candidate).intersects(word_rect)):
                return QPoint(x, y)

        # Ranked alternatives plus IPA can be taller than either vertical gap.
        # Try beside both the word and controls before allowing any overlap.
        side_y = int(min(max(min_y, word_rect.center().y() - bubble_height / 2), max_y))
        for side_x in (int(max(word_rect.right(), self._tooltip_avoid_rect.right()) + 10),
                       int(min(word_rect.left(), self._tooltip_avoid_rect.left()) - bubble_width - 10)):
            candidate = QRect(side_x, side_y, bubble_width, bubble_height)
            if (min_x <= side_x <= max_x and not candidate.intersects(self._tooltip_avoid_rect)
                    and not QRectF(candidate).intersects(word_rect)):
                return QPoint(side_x, side_y)

        # With very large selections there may be no collision-free side. The bubble
        # is a top-level review overlay, so this fallback remains visible over the panel.
        return QPoint(x, max(min_y, min(above_y, max_y)))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#07111f"))
        self._image_rect = self._calculate_image_rect()
        if self.capture is not None:
            self.capture.draw(painter, self._image_rect)
        else:
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
        self.word_selected.emit(hit)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._schedule_hide()
        super().leaveEvent(event)


class _ReviewTile(QWidget):
    """Additional per-monitor viewport; recognition/audio are owned by ReviewWindow."""

    def __init__(self, owner: ReviewWindow, capture: DesktopCapture, viewport: QRect, selection: QRect) -> None:
        super().__init__(owner, owner.windowFlags())
        self.owner = owner
        self.canvas = ImageCanvas(capture, selection, self)
        self.canvas.viewport = QRect(viewport)
        self.canvas.monitor_rects = capture.monitor_rects
        self.setGeometry(viewport.translated(capture.geometry.topLeft()))

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.canvas.setGeometry(self.rect())
        super().resizeEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        self.owner.keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.owner._closed:
            self.owner.close()
        self.canvas.dismiss_word()
        super().closeEvent(event)


class ReviewWindow(QWidget):
    finished = Signal()
    reselect_requested = Signal(object)
    speech_speed_changed = Signal(float)

    def __init__(self, capture: DesktopCapture | QPixmap, selection: QRect, settings: Settings) -> None:
        super().__init__()
        if isinstance(capture, QPixmap):
            capture = DesktopCapture(capture, QRect(QPoint(), capture.size()))
        self.settings = settings
        self._closed = False
        self._jobs = []
        self._more_job = None
        self._more_word = None
        self._current_word_index = -1
        self._manual_panel_position = None
        self._translator = ArgosTranslator()
        self._translation_cancelled = Event()
        self.speech = SpeechPlayer(self)
        self.speech.speed = settings.speech_speed
        self._speech_text = ""
        self._translated_text = ""
        self._translations: dict[str, WordTranslation] = {}
        self._failed_words: set[str] = set()
        self._translation_total = 0
        self._translation_layout_timer = QTimer(self)
        self._translation_layout_timer.setSingleShot(True)
        self._translation_layout_timer.timeout.connect(self._position_children)
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
        self._pixmap_size = capture.size
        rectangles = capture.monitor_rects or (capture.rect,)
        viewport = next((rect for rect in rectangles if rect.contains(selection.center())), None)
        if viewport is None:
            viewport = max(rectangles, key=lambda rect: (
                rect.intersected(selection).width() * rect.intersected(selection).height(),
            ))
        self.canvas = ImageCanvas(capture, selection, self)
        self.canvas.monitor_rects = capture.monitor_rects
        self.canvas.viewport = QRect(viewport)
        self._tiles = [_ReviewTile(self, capture, rect, selection) for rect in rectangles if rect != viewport]
        self._canvases = [self.canvas, *(tile.canvas for tile in self._tiles)]
        for canvas in self._canvases:
            # A monitor viewport must fit its real logical dimensions, even
            # when smaller than the standalone canvas's preferred minimum.
            canvas.setMinimumSize(1, 1)
            canvas.candidates_enabled = settings.source_language != settings.target_language
            canvas.word_selected.connect(lambda hit, canvas=canvas: self._word_selected(hit, canvas))
            canvas.word_audio_requested.connect(self._read_word)
            canvas.pronunciation_retry_requested.connect(self._prepare_pronunciation)
            canvas.more_candidates_requested.connect(self._request_more_candidates)
        self.status = QLabel("Reading the selected text locally…")
        self.status.setWordWrap(True)
        self.status.setObjectName("statusLabel")
        self.status.setAccessibleName("Recognition and translation status")
        self.translation = QLabel("")
        self.translation.setObjectName("sentenceTranslation")
        self.translation.setWordWrap(True)
        make_copyable(self.translation, "Whole-selection translation", lambda: self._translated_text)
        self.translation.hide()
        close_button = QPushButton("Close and return   Esc")
        close_button.clicked.connect(self.close)

        footer = DraggablePanel()
        footer.moved.connect(self._move_controls)
        footer.setObjectName("footer")
        footer_layout = QVBoxLayout(footer)
        self._footer_body = QWidget()
        body_layout = QVBoxLayout(self._footer_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(self.status)
        self.diagnostics_button = QPushButton("Open diagnostics folder")
        self.diagnostics_button.clicked.connect(open_folder)
        self.diagnostics_button.hide()
        body_layout.addWidget(self.diagnostics_button)
        self.recognized_section = ExpandableSection("Recognized text")
        self.recognized_section.toggle.setEnabled(False)
        set_help(self.recognized_section.toggle, "Show the original text recognized by local OCR to check whether an odd translation "
            "comes from recognition or translation. This view is read-only: selecting or copying it does not change word outlines, "
            "translations or pronunciation. Right-click for 'Copy all'; close this section to keep the screenshot unobstructed.")
        self.recognized_text = QLabel()
        self.recognized_text.setTextFormat(Qt.TextFormat.PlainText)
        self.recognized_text.setWordWrap(True)
        make_copyable(self.recognized_text, "Recognized source text", lambda: self._speech_text)
        recognized_layout = QVBoxLayout(self.recognized_section.content)
        recognized_layout.setContentsMargins(0, 0, 0, 0)
        recognized_layout.addWidget(self.recognized_text)
        body_layout.addWidget(self.recognized_section)
        body_layout.addWidget(self.translation)
        self.recognized_section.expanded.connect(lambda _expanded: self._position_children())
        self._footer_scroll = QScrollArea()
        self._footer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._footer_scroll.setWidgetResizable(True)
        self._footer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._footer_scroll.setWidget(self._footer_body)
        footer_layout.addWidget(self._footer_scroll)
        button_row = QGridLayout()
        self.read_button = QPushButton("Read selection")
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self._read_selection)
        self.speech_status = QLabel()
        self.speech_status.setObjectName("note")
        self.speech_status.setTextFormat(Qt.TextFormat.PlainText)
        self.speech_status.setWordWrap(True)
        self.speech.changed.connect(self._speech_changed)
        self.retry_ocr = QPushButton("Retry OCR")
        self.retry_ocr.clicked.connect(self._retry_ocr)
        self.reselect = QPushButton("Select another area")
        self.reselect.clicked.connect(lambda: self.reselect_requested.emit(self.canvas.capture))
        self.copy_button = QPushButton("Copy source text")
        self.copy_button.clicked.connect(self._copy_source)
        self.copy_button.setEnabled(False)
        self.retry_translation = QPushButton("Retry translation")
        self.retry_translation.clicked.connect(self._start_translation)
        self.retry_translation.setEnabled(False)
        self.collapse_translation = QPushButton("Hide translation")
        self.collapse_translation.clicked.connect(self._toggle_translation)
        self.collapse_translation.setEnabled(False)
        self._translation_hidden = False
        self._action_buttons = (self.retry_ocr, self.reselect, self.copy_button,
                self.read_button, self.retry_translation, self.collapse_translation)
        self._button_grid = button_row
        self._action_columns = 3
        self._close_button = close_button
        for index, button in enumerate(self._action_buttons):
            button_row.addWidget(button, index // 3, index % 3)
        body_layout.addWidget(self.speech_status)
        self._actions_body = QWidget()
        self._actions_body.setLayout(button_row)
        self._actions_scroll = QScrollArea()
        self._actions_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._actions_scroll.setWidgetResizable(True)
        self._actions_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._actions_scroll.setWidget(self._actions_body)
        footer_layout.addWidget(self._actions_scroll)
        # Keep the one existing close button reachable even when actions scroll.
        footer_layout.addWidget(close_button)
        speed_row = QHBoxLayout()
        self._speed_row = speed_row
        self.speed_label = QLabel()
        self.speed_label.setObjectName("note")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setAccessibleName("Pronunciation speed")
        self.speed_slider.setRange(50, 150)
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setPageStep(25)
        self.speed_slider.setValue(round(settings.speech_speed * 100))
        self.speed_slider.installEventFilter(self)
        set_help(self.speed_slider, "Adjust 'Pronunciation speed' from 0.5× to 1.5× for words and the whole selection. "
            "Slow down to hear difficult sounds; the local voice changes duration without raising or lowering pitch. "
            "Changing speed stops current audio; use 'Pronounce word' or 'Read selection' to hear the new speed. "
            "The choice is remembered for future captures and voice samples. IPA does not change. "
            "When this slider has focus, the left and right arrow keys adjust speed instead of browsing words.")
        self.speed_slider.valueChanged.connect(self._speed_changed)
        speed_row.addWidget(self.speed_label)
        speed_row.addWidget(self.speed_slider, 1)
        footer_layout.addLayout(speed_row)
        self.speed_label.setText(f"Pronunciation speed: {self.speech.speed:g}×")

        self._footer = footer
        footer.setParent(self)
        footer.enable_background_drag()
        # Reserve the widest speed label once, so changing digits cannot move
        # or resize the slider track underneath the pointer. The track can
        # still adapt to the monitor width when the footer is laid out.
        self.speed_label.ensurePolished()
        metrics = self.speed_label.fontMetrics()
        self._speed_label_width = max(
            metrics.horizontalAdvance(text) for text in (
                self.speed_label.text(),
                *(f"Pronunciation speed: {value / 100:g}×" for value in range(50, 151)),
            )
        ) + 8
        self.speed_label.setFixedWidth(self._speed_label_width)
        self.speed_label.setWordWrap(True)
        self._refresh_speech()

        # Tab follows the visual content/actions order, including hidden sections
        # when opened. The screenshot is deliberately not a fake accessible word list.
        focus_order = (self.recognized_section.toggle, self.recognized_text, self.translation,
                       *self._action_buttons, self._close_button, self.speed_slider)
        for before, after in zip(focus_order, focus_order[1:]):
            QWidget.setTabOrder(before, after)

        self.setGeometry(viewport.translated(capture.geometry.topLeft()))
        self._shortcuts = []
        for window in (self, *self._tiles):
            for key, step in (("Right", 1), ("Left", -1)):
                shortcut = QShortcut(QKeySequence(key), window)
                shortcut.activated.connect(lambda step=step: self._navigate_word(step))
                self._shortcuts.append(shortcut)
        self._retry_ocr()

    def _retry_ocr(self) -> None:
        if self._closed:
            return
        for job in self._jobs:
            if job is not None:
                job.shutdown()
        self._jobs.clear()
        # Shutdown emits playback changes. Clear the old source first so those
        # callbacks cannot re-enable controls for text that is being replaced.
        self._speech_text = ""
        self._translated_text = ""
        self._lines, self._hits = [], []
        self._translations.clear()
        self._failed_words.clear()
        self._translation_total = 0
        self._translation_layout_timer.stop()
        self._current_word_index = -1
        self._active_word = None
        self.shutdown_speech()
        self._refresh_speech()
        self._update_canvases("set_hits", [])
        self._update_canvases("set_pronunciations", [])
        self.translation.clear()
        self.translation.hide()
        self.recognized_text.clear()
        self.recognized_section.toggle.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.retry_translation.setEnabled(False)
        self.collapse_translation.setEnabled(False)
        self.status.setText("Reading selected text locally…")
        self.retry_ocr.setEnabled(False)
        capture, selection, settings = self.canvas.capture, self._selection, self.settings
        padding = max(16, min(48, round(min(selection.width(), selection.height()) * 0.35)))
        retry_rect = selection.adjusted(-padding, -padding, padding, padding).intersected(
            capture.rect
        )
        if capture.screens:
            task = NativeOcrTask(capture, selection, settings)
        else:
            pixmap = capture.pixmap
            task = OcrTask(
                pixmap.copy(selection).toImage(),
                settings,
                retry_image=pixmap.copy(retry_rect).toImage(),
                retry_offset=retry_rect.topLeft() - selection.topLeft(),
                selection_size=selection.size(),
            )
        task.signals.result.connect(self._ocr_finished)
        task.signals.setParent(self)
        task.signals.error.connect(self._ocr_failed)
        task.signals.progress.connect(self.status.setText)
        # One spanning window has only one DPR. Native windows per monitor retain
        # each screen's logical-to-physical mapping for display and mouse input.
        self._jobs.append(QThreadPool.globalInstance().start(task))

    def _ocr_failed(self, message: str) -> None:
        if not self._closed:
            self.retry_ocr.setEnabled(True)
            self._failed(message)

    def _copy_source(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._speech_text)

    def _toggle_translation(self) -> None:
        if not self.translation.text():
            return
        self._translation_hidden = not self._translation_hidden
        self.translation.setVisible(bool(self.translation.text()) and not self._translation_hidden)
        self.collapse_translation.setText("Show translation" if self._translation_hidden else "Hide translation")
        self._position_children()

    def _word_selected(self, hit: WordHit, canvas: ImageCanvas) -> None:
        if self._closed:
            return
        # Translation replaces canvas hit objects; repeated words also share
        # spelling. Source spans identify the exact occurrence in either case.
        index = next((index for index, item in enumerate(self._hits)
                      if canvas._span(item) == canvas._span(hit)), None)
        if index is None:
            return
        self._current_word_index = index
        for other in self._canvases:
            if other is not canvas:
                other.dismiss_word()
        # Explicitly choosing a word leaves any previously focused speed slider.
        canvas._bubble.setFocus(Qt.FocusReason.MouseFocusReason)

    def _navigate_word(self, step: int) -> None:
        if self._closed or not self._hits:
            return
        self._current_word_index = ((0 if step > 0 else len(self._hits) - 1) if self._current_word_index < 0
                                   else (self._current_word_index + step) % len(self._hits))
        hit = self._hits[self._current_word_index]
        self._update_canvases("dismiss_word")
        for canvas in self._canvases:
            viewport = canvas.viewport
            if viewport is None or viewport.contains(QPoint(round(hit.bounds.x + hit.bounds.width / 2), round(hit.bounds.y + hit.bounds.height / 2))):
                canvas._hovered = next(item for item in canvas._hits if canvas._span(item) == canvas._span(hit))
                canvas._pinned = True
                canvas._hide_timer.stop()
                canvas._refresh_bubble()
                canvas.update()
                canvas._bubble.setFocus()
                break

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        for tile in self._tiles:
            tile.show()
        self.activateWindow()
        self.raise_()

    def _update_canvases(self, method: str, *args, **kwargs) -> None:
        for canvas in self._canvases:
            getattr(canvas, method)(*args, **kwargs)

    def _ocr_finished(self, result: object) -> None:
        if self._closed:
            return
        self.retry_ocr.setEnabled(True)
        self._lines = [
            line.map_geometry(
                lambda x, y: (x + self._selection.x(), y + self._selection.y())
            )
            for line in result
        ]
        self._hits = build_word_hits(self._lines, self.settings.source_language)
        self._translation_total = len({hit.lookup_text for hit in self._hits})
        self._update_canvases("set_hits", self._hits)
        self._speech_text = " ".join(line.text for line in self._lines)
        self.recognized_text.setText(self._speech_text)
        self.recognized_section.toggle.setEnabled(bool(self._speech_text.strip()))
        self.copy_button.setEnabled(bool(self._speech_text))
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
            f"Found {len(self._hits)} words. Hover for details; click to pin. Use the left and right arrow keys to browse words."
        )
        self._start_translation()

    def _start_translation(self) -> None:
        if self._closed or not self._lines:
            return
        for job in self._jobs[1:]:
            if job is not None:
                job.shutdown()
        self.retry_translation.setEnabled(False)
        self._translations.clear()
        self._failed_words.clear()
        self.status.setText(self._word_instructions() + "\nTranslating the selection locally…")
        task = TranslationTask(
            self._lines, (hit.lookup_text for hit in self._hits), self.settings,
            translator=self._translator, cancelled=self._translation_cancelled,
        )
        task.signals.result.connect(self._translation_finished)
        task.signals.setParent(self)
        task.signals.error.connect(self._translation_failed)
        task.signals.progress.connect(self.status.setText)
        job = QThreadPool.globalInstance().start(task)
        self._jobs.append(job)
        if job is not None:
            job.finished.connect(lambda: self.retry_translation.setEnabled(True))

    def _translation_failed(self, message: str) -> None:
        if not self._closed:
            pending = {hit.lookup_text: hit.translation or WordTranslation((), "Translation stopped. Choose 'Retry translation'.")
                       for hit in self.canvas._hits}
            self._update_canvases("set_translations", pending)
            self.retry_translation.setEnabled(True)
            self._failed(message)

    def _translation_finished(self, result: object) -> None:
        if self._closed:
            return
        sentence, translations = result
        if sentence is not None:
            self._translated_text = sentence
            self.translation.setText(f"<b>Whole selection:</b> {html.escape(sentence)}" if sentence else "Whole-selection translation unavailable. Word lookups are independent.")
            self.translation.setVisible(not self._translation_hidden)
            self.collapse_translation.setEnabled(True)
        self._translations.update(translations)
        for word, item in translations.items():
            if item.candidates:
                self._failed_words.discard(word)
            else:
                self._failed_words.add(word)
        self._update_canvases("set_translations", translations)
        total = self._translation_total
        completed = len(self._translations)
        failed = len(self._failed_words)
        if completed < total:
            message = (self._word_instructions() + f"\nWord lookups: {completed} of {total} completed "
                       f"({total - completed} pending).")
        else:
            message = self._word_instructions()
        if failed:
            message += f" {failed} word lookup{'s' if failed != 1 else ''} unavailable; choose 'Retry translation' to try again."
        if not self._translated_text:
            message += " Whole-selection translation unavailable; word lookups are independent."
        self.status.setText(message)
        self._translation_layout_timer.start(0)

    def _word_instructions(self) -> str:
        return (f"Found {len(self._hits)} words. Hover for details; click to pin. "
                "Use the left and right arrow keys to browse words.")

    def _request_more_candidates(self, word: str) -> None:
        if self._closed:
            return
        task = MoreCandidatesTask(word, self.settings, self._translator, self._translation_cancelled)
        task.signals.result.connect(self._more_candidates_finished)
        task.signals.setParent(self)
        if self._more_job is not None and self._more_job.active:
            self._more_job.shutdown()
        self._more_word = word
        self._more_job = QThreadPool.globalInstance().start(task)
        self._jobs = self._jobs[:1] + [job for job in self._jobs[1:] if job is not None and job.active]
        self._jobs.append(self._more_job)

    def _more_candidates_finished(self, result: object) -> None:
        if not self._closed:
            word, translation, error = result
            self._update_canvases("set_more_candidates", word, translation, error)

    def _failed(self, message: str) -> None:
        if self._closed:
            return
        self.status.setText(f"Could not finish: {message}")
        self.diagnostics_button.show()
        self._position_children()

    def _refresh_speech(self) -> None:
        message = ""
        ready = False
        if not self.settings.speech_enabled:
            message = "Pronunciation is off in 'Settings'."
        elif self._voice is None:
            message = "No pronunciation voice is available for this text language yet."
        elif not runtime_ready():
            message = "Restart with 'Start Language Lens.bat' to install speech components."
        elif not voice_present(self._voice):
            message = "Use 'Download voice' in 'Settings' to read this text aloud."
        elif len(self._speech_text) > MAX_TEXT_LENGTH:
            message = "Select a shorter passage to read aloud (up to 2,000 characters)."
        elif self._speech_text.strip():
            ready = True
            message = self._voice.name
        self.read_button.setEnabled(ready)
        self.speed_slider.setEnabled(ready or self.speech.busy)
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

    def _speed_changed(self, value: int) -> None:
        speed = value / 100
        self.speech.stop()
        self.speech.speed = self.settings.speech_speed = speed
        self.speed_label.setText(f"Pronunciation speed: {speed:g}×")
        self.speech_speed_changed.emit(speed)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (watched is self.speed_slider and event.type() == QEvent.Type.ShortcutOverride
                and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right)):
            # The focused slider owns arrows; the window shortcuts own them elsewhere.
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _prepare_pronunciation(self) -> None:
        if self._closed or self.pronunciation_job.active:
            return
        from language_lens.services.voices import voice_runtime_ready
        has_runtime = runtime_ready() and bool(self._voice and voice_runtime_ready(self._voice))
        audio_available = bool(self.settings.speech_enabled and has_runtime and self._voice
                               and voice_present(self._voice))
        self._update_canvases("configure_pronunciation",
            self.settings.show_ipa, audio_available, self._voice.name if self._voice else ""
        )
        if not self.settings.show_ipa and not audio_available:
            return
        if self._voice is None:
            self._update_canvases("set_pronunciations", [], "IPA is not available for this text language yet.")
            return
        if not has_runtime:
            self._update_canvases("set_pronunciations", [], "Restart with 'Start Language Lens.bat' to install pronunciation components.")
            return
        if not self._speech_text.strip() or len(self._speech_text) > MAX_TEXT_LENGTH:
            self._update_canvases("set_pronunciations", [], "IPA needs a selection of up to 2,000 characters.")
            return
        self._prepared = None
        self._update_canvases("set_pronunciations", [], "Preparing pronunciation…")
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
            self._update_canvases("set_pronunciations", result["words"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._pronunciation_failed(str(exc))

    def _pronunciation_failed(self, message: str) -> None:
        if not self._closed:
            self._prepared = None
            self._update_canvases("set_pronunciations", [], f"Pronunciation unavailable: {message}", failed=True)

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
        self._update_canvases("set_playback", state, self._active_word)
        self._refresh_speech()
        if self.speech.busy:
            self.read_button.setText("Cancel audio" if state == "generating" else "Stop audio")
            self.read_button.setEnabled(state != "stopping")
        if message:
            self.speech_status.setText("Pronouncing word…" if state == "playing" and self._active_word else message)
            self.speech_status.show()
        self._position_children()

    def _position_children(self) -> None:
        """Prefer an anchor beside the selection; clamp a manual position."""
        self.canvas.setGeometry(self.rect())
        selection_rect = self.canvas.selection_display_rect()
        area = self.canvas.monitor_display_rect(selection_rect)
        margin = 22
        gap = 14
        available_width = max(1, area.width() - margin * 2)
        preferred_width = max(620, int(round(selection_rect.width())))
        footer_width = min(900, available_width, preferred_width)
        self._footer.setFixedWidth(footer_width)
        body_width = max(1, footer_width - 40)
        grid_margins = self._button_grid.contentsMargins()
        spacing = max(0, self._button_grid.horizontalSpacing())
        columns = 1
        for candidate in (3, 2):
            required = (grid_margins.left() + grid_margins.right()
                        + sum(max(button.minimumSizeHint().width()
                                  for button in self._action_buttons[column::candidate])
                              for column in range(candidate))
                        + spacing * (candidate - 1)
                        + self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent))
            if required <= body_width:
                columns = candidate
                break
        if columns != self._action_columns:
            for button in self._action_buttons:
                self._button_grid.removeWidget(button)
            for index, button in enumerate(self._action_buttons):
                self._button_grid.addWidget(button, index // columns, index % columns)
            self._action_columns = columns
        self.speed_label.setFixedWidth(min(self._speed_label_width, body_width))
        self._speed_row.setDirection(
            QBoxLayout.Direction.TopToBottom if body_width < self._speed_label_width + 120
            else QBoxLayout.Direction.LeftToRight)
        desired_body = max(30, self._footer_body.layout().heightForWidth(body_width))
        available_height = max(1, area.height() - margin * 2)
        footer_layout = self._footer.layout()
        margins = footer_layout.contentsMargins()
        close_height = self._close_button.sizeHint().height()
        speed_height = self._speed_row.totalHeightForWidth(body_width)
        if speed_height < 0:
            speed_height = self._speed_row.sizeHint().height()
        overhead = margins.top() + margins.bottom() + max(0, footer_layout.spacing()) * 3 + close_height + speed_height + 8
        content_budget = max(80, available_height - overhead)
        body_height = min(desired_body, max(40, min(220, area.height() // 3)), max(40, content_budget - 40))
        self._footer_scroll.setFixedHeight(body_height)
        actions_height = self._actions_body.layout().sizeHint().height() + 4
        # Recovery actions scroll on small screens; the close button does not.
        self._actions_scroll.setFixedHeight(min(actions_height, max(40, content_budget - body_height)))
        self._footer.layout().activate()
        hint = self._footer.layout().heightForWidth(footer_width)
        footer_height = min(available_height, max(118, hint, self._footer.sizeHint().height()))

        footer_x = int(round(selection_rect.center().x() - footer_width / 2))
        footer_x = max(area.x() + margin, min(footer_x, area.x() + area.width() - margin - footer_width))

        above_y = int(selection_rect.top()) - gap - footer_height
        below_y = int(selection_rect.bottom()) + gap + 1
        selection_is_low = selection_rect.center().y() >= area.center().y()
        footer_y = above_y if selection_is_low else below_y
        if footer_y < area.y() + margin or footer_y + footer_height > area.y() + area.height() - margin:
            footer_y = below_y if selection_is_low else above_y
        footer_y = max(area.y() + margin, min(footer_y, area.y() + area.height() - margin - footer_height))

        bounds = area.adjusted(margin, margin, -margin, -margin)
        position = self._manual_panel_position or QPoint(footer_x, footer_y)
        position = QPoint(max(bounds.left(), min(position.x(), bounds.right() - footer_width + 1)),
                          max(bounds.top(), min(position.y(), bounds.bottom() - footer_height + 1)))
        self._footer.setGeometry(QRect(position, QSize(footer_width, footer_height)))
        self._footer.raise_()
        self.canvas.set_tooltip_avoid_rect(
            self._footer.geometry().adjusted(-8, -8, 8, 8)
        )
        if not self.canvas._bubble.isHidden():
            self.canvas._bubble.raise_()

    def _move_controls(self, delta: QPoint) -> None:
        self._manual_panel_position = self._footer.pos() + delta
        self._position_children()

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._position_children()
        super().resizeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._closed:
            super().closeEvent(event)
            return
        self._closed = True
        self._translation_layout_timer.stop()
        for tile in self._tiles:
            tile.close()
            tile.deleteLater()
        self._translation_cancelled.set()
        for job in self._jobs:
            if job is not None:
                job.shutdown()
        self.shutdown_speech()
        self.canvas.dismiss_word()
        self.finished.emit()
        super().closeEvent(event)

    def shutdown_speech(self) -> None:
        self.pronunciation_job.shutdown()
        self.speech.shutdown()
        self._prepared = None

