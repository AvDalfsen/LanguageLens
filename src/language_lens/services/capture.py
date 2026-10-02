from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap


@dataclass(slots=True)
class DesktopCapture:
    pixmap: QPixmap
    geometry: QRect


def capture_desktop() -> DesktopCapture:
    """Capture the Qt virtual desktop in the same coordinates used by the overlay.

    Screen-grab pixmaps may use physical pixels while Qt windows use DPI-independent
    coordinates. Compositing every screen into a DPR=1 virtual-desktop pixmap keeps
    capture pixels, mouse selection, and overlay geometry in one coordinate system.
    """
    screens = QGuiApplication.screens()
    if not screens:
        raise RuntimeError("Windows did not report an available display.")

    geometry = screens[0].geometry()
    for screen in screens[1:]:
        geometry = geometry.united(screen.geometry())

    desktop = QPixmap(geometry.size())
    desktop.setDevicePixelRatio(1.0)
    desktop.fill(QColor("black"))
    painter = QPainter(desktop)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for screen in screens:
        shot = screen.grabWindow(0)
        target = screen.geometry().translated(-geometry.topLeft())
        painter.drawPixmap(target, shot)
    painter.end()
    return DesktopCapture(pixmap=desktop, geometry=QRect(geometry))

