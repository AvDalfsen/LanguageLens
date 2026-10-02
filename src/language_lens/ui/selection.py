from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
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
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(capture.geometry)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @property
    def selection(self) -> QRect:
        if self._start is None or self._end is None:
            return QRect()
        return QRect(self._start, self._end).normalized().intersected(self.rect())

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._capture.pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 115))
        selection = self.selection
        if not selection.isEmpty():
            painter.drawPixmap(selection, self._capture.pixmap, selection)
            painter.setPen(QPen(QColor("#5eead4"), 2))
            painter.drawRect(selection.adjusted(0, 0, -1, -1))

        painter.setPen(QColor("white"))
        painter.fillRect(QRect(24, 20, 520, 42), QColor(8, 15, 28, 210))
        painter.drawText(
            QRect(40, 20, 490, 42),
            Qt.AlignmentFlag.AlignVCenter,
            "Drag around the text • Esc cancels",
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._end = self._start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._start is not None:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._start is None:
            return
        self._end = event.position().toPoint()
        selection = self.selection
        if selection.width() >= 12 and selection.height() >= 12:
            self.hide()
            self.selected.emit(self._capture.pixmap, selection)
            self.deleteLater()
        else:
            self._start = None
            self._end = None
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.cancelled.emit()
            self.deleteLater()
            return
        super().keyPressEvent(event)

