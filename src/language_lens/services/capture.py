from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from PySide6.QtCore import QPoint, QRect, QRectF
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPixmap


@dataclass(slots=True)
class ScreenCapture:
    """Unscaled physical pixels and their global, logical screen rectangle."""

    pixmap: QPixmap
    geometry: QRect


@dataclass(slots=True)
class CaptureCrop:
    image: QImage
    native_rect: QRect
    logical_rect: QRectF

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.logical_rect.x() + x * self.logical_rect.width() / self.image.width(),
            self.logical_rect.y() + y * self.logical_rect.height() / self.image.height(),
        )


@dataclass(slots=True, init=False)
class DesktopCapture:
    _pixmap: QPixmap | None
    geometry: QRect
    screens: tuple[ScreenCapture, ...] = ()

    def __init__(self, pixmap: QPixmap | None, geometry: QRect, screens=()) -> None:
        self._pixmap = pixmap
        self.geometry = QRect(geometry)
        self.screens = tuple(screens)

    @property
    def size(self):
        return self.geometry.size()

    @property
    def rect(self) -> QRect:
        return QRect(QPoint(), self.size)

    @property
    def pixmap(self) -> QPixmap:
        """Compatibility preview, allocated only when explicitly requested."""
        if self._pixmap is None:
            self._pixmap = QPixmap(self.size)
            self._pixmap.setDevicePixelRatio(1.0)
            self._pixmap.fill(QColor("black"))
            if self.screens:
                painter = QPainter(self._pixmap)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                self.draw(painter, QRectF(self.rect))
                painter.end()
        return self._pixmap

    @pixmap.setter
    def pixmap(self, value: QPixmap) -> None:
        self._pixmap = value

    @property
    def monitor_rects(self) -> tuple[QRect, ...]:
        return tuple(screen.geometry.translated(-self.geometry.topLeft()) for screen in self.screens)

    def draw(self, painter: QPainter, target: QRectF) -> None:
        """Draw native tiles directly without allocating a desktop-sized preview."""
        if not self.screens:
            painter.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
            return
        painter.fillRect(target, QColor("black"))
        sx, sy = target.width() / self.geometry.width(), target.height() / self.geometry.height()
        for screen, bounds in zip(self.screens, self.monitor_rects):
            region = QRectF(target.x() + bounds.x() * sx, target.y() + bounds.y() * sy,
                            bounds.width() * sx, bounds.height() * sy)
            painter.drawPixmap(region, screen.pixmap, QRectF(screen.pixmap.rect()))

    def crop_screen(self, screen: ScreenCapture, rect: QRect) -> CaptureCrop | None:
        """Crop without resizing, rounding outward at fractional pixel boundaries.

        rect is local to the display composite. Derive scale from actual pixel
        dimensions, not rounded DPI metadata; map the rounded crop back exactly.
        """
        bounds = screen.geometry.translated(-self.geometry.topLeft())
        selected = rect.intersected(bounds)
        if selected.isEmpty():
            return None
        sx = screen.pixmap.width() / bounds.width()
        sy = screen.pixmap.height() / bounds.height()
        left = max(0, floor((selected.x() - bounds.x()) * sx))
        top = max(0, floor((selected.y() - bounds.y()) * sy))
        right = min(screen.pixmap.width(), ceil((selected.x() + selected.width() - bounds.x()) * sx))
        bottom = min(screen.pixmap.height(), ceil((selected.y() + selected.height() - bounds.y()) * sy))
        native = QRect(left, top, right - left, bottom - top)
        image = screen.pixmap.copy(native).toImage()
        image.setDevicePixelRatio(1.0)
        logical = QRectF(bounds.x() + left / sx, bounds.y() + top / sy,
                         native.width() / sx, native.height() / sy)
        return CaptureCrop(image, native, logical)


def capture_desktop(scope: str = "all", position: QPoint | None = None) -> DesktopCapture:
    """Keep native monitor images separately from the logical display composite."""
    screens = QGuiApplication.screens()
    if not screens:
        raise RuntimeError("Windows did not report an available display.")
    if scope not in {"all", "current"}:
        raise ValueError("Capture scope must be 'all' or 'current'.")
    if scope == "current":
        position = position if position is not None else QCursor.pos()
        screen = next((screen for screen in screens if screen.geometry().contains(position)), None)
        if screen is None:
            raise RuntimeError("The pointer is outside the available monitors. Move it onto a monitor and retry.")
        screens = [screen]

    native_screens = []
    for screen in screens:
        bounds = screen.geometry()
        shot = screen.grabWindow(0)
        if bounds.isEmpty() or shot.isNull():
            raise RuntimeError("A monitor could not be captured. Check the display connection and retry.")
        # Only metadata changes: the physical pixel buffer is never resized.
        shot.setDevicePixelRatio(1.0)
        native_screens.append(ScreenCapture(shot, QRect(bounds)))

    geometry = QRect(native_screens[0].geometry)
    for screen in native_screens[1:]:
        geometry = geometry.united(screen.geometry)

    return DesktopCapture(None, geometry, tuple(native_screens))

