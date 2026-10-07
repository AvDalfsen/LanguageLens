from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QCloseEvent, QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from language_lens.services.capture import DesktopCapture


class SelectionOverlay(QWidget):
    selected = Signal(object, object)
    cancelled = Signal()

    def __init__(self, capture: DesktopCapture) -> None:
        super().__init__()
        self._capture = capture
        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._finished = False
        self._hint = "Drag around the text • Esc cancels"
        rectangles = capture.monitor_rects or (capture.rect,)
        self._viewport = QRect(rectangles[0])
        self._tiles: list[_SelectionTile] = []
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(self._viewport.translated(capture.geometry.topLeft()))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for rect in rectangles[1:]:
            self._tiles.append(_SelectionTile(self, rect))

    @property
    def selection(self) -> QRect:
        if self._start is None or self._end is None:
            return QRect()
        return QRect(self._start, self._end).normalized().intersected(self._capture.rect)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        for tile in self._tiles:
            tile.show()
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def paintEvent(self, event) -> None:  # noqa: N802
        self._paint_tile(self, self._viewport)

    def _paint_tile(self, widget: QWidget, viewport: QRect) -> None:
        painter = QPainter(widget)
        image_rect = QRectF(-viewport.x(), -viewport.y(),
                            self._capture.size.width(), self._capture.size.height())
        self._capture.draw(painter, image_rect)
        painter.fillRect(widget.rect(), QColor(0, 0, 0, 115))
        selection = self.selection.translated(-viewport.topLeft())
        if not selection.isEmpty():
            painter.save()
            painter.setClipRect(selection)
            self._capture.draw(painter, image_rect)
            painter.restore()
            painter.setPen(QPen(QColor("#5eead4"), 2))
            painter.drawRect(selection.adjusted(0, 0, -1, -1))

        painter.setPen(QColor("white"))
        hint = QRect(24, 20, min(520, widget.width() - 48), 42)
        painter.fillRect(hint, QColor(8, 15, 28, 210))
        painter.drawText(
            hint.adjusted(16, 0, -8, 0),
            Qt.AlignmentFlag.AlignVCenter,
            self._hint,
        )

    def _update_tiles(self) -> None:
        self.update()
        for tile in self._tiles:
            tile.update()

    def _source_position(self, event: QMouseEvent) -> QPoint:
        return event.globalPosition().toPoint() - self._capture.geometry.topLeft()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._finished:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = self._source_position(event)
            self._end = self._start
            self._update_tiles()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._finished and self._start is not None:
            self._end = self._source_position(event)
            self._update_tiles()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._finished or event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        self._end = self._source_position(event)
        selection = self.selection
        monitors = self._capture.monitor_rects
        on_monitor = not monitors or any(selection.intersects(rect) for rect in monitors)
        if not on_monitor:
            self._hint = "Select text on a monitor, not in the desktop gap • Esc cancels"
        if on_monitor and selection.width() >= 12 and selection.height() >= 12:
            # Mark success before closing so closeEvent cannot also cancel it.
            self._finished = True
            self.close()
            self.selected.emit(self._capture, selection)
        else:
            self._start = None
            self._end = None
            self._update_tiles()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        cancelled = not self._finished
        self._finished = True
        for tile in self._tiles:
            tile.close()
            tile.deleteLater()
        super().closeEvent(event)
        self.deleteLater()
        if cancelled:
            self.cancelled.emit()


class _SelectionTile(QWidget):
    """A native window per monitor so Qt applies that monitor's own DPI scale."""

    def __init__(self, owner: SelectionOverlay, viewport: QRect) -> None:
        super().__init__(owner, owner.windowFlags())
        self.owner = owner
        self.viewport = QRect(viewport)
        self.setGeometry(viewport.translated(owner._capture.geometry.topLeft()))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, event) -> None:  # noqa: N802
        self.owner._paint_tile(self, self.viewport)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.owner.mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self.owner.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self.owner.mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        self.owner.keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.owner._finished:
            self.owner.close()
        super().closeEvent(event)

