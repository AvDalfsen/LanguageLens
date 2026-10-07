from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QColor, QGuiApplication, QPixmap
import pytest

from language_lens.services.capture import capture_desktop


@dataclass
class FakeScreen:
    bounds: QRect
    shot: QPixmap
    grabs: int = 0

    def geometry(self):
        return QRect(self.bounds)

    def grabWindow(self, handle):  # noqa: N802
        assert handle == 0
        self.grabs += 1
        return QPixmap(self.shot)


def screen(bounds, scale=1, color="red", pixel_size=None):
    size = pixel_size or QSize(round(bounds.width() * scale), round(bounds.height() * scale))
    shot = QPixmap(size)
    shot.setDevicePixelRatio(scale)
    shot.fill(QColor(color))
    return FakeScreen(bounds, shot)


def install_screens(monkeypatch, *screens):
    monkeypatch.setattr(QGuiApplication, "screens", staticmethod(lambda: list(screens)))


@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_capture_retains_native_resolution_and_maps_crop_exactly(monkeypatch, qapp, scale):
    monitor = screen(QRect(0, 0, 800, 600), scale)
    install_screens(monkeypatch, monitor)
    capture = capture_desktop()
    assert capture.pixmap.size() == QSize(800, 600)
    native = capture.screens[0]
    assert native.pixmap.size() == monitor.shot.size()
    assert native.pixmap.devicePixelRatio() == 1
    assert monitor.shot.devicePixelRatio() == scale  # source metadata was not mutated
    crop = capture.crop_screen(native, QRect(100, 80, 200, 40))
    assert crop.image.size() == QSize(round(200 * scale), round(40 * scale))
    assert crop.image.devicePixelRatio() == 1
    assert crop.map_point(20 * scale, 10 * scale) == pytest.approx((120, 90))


def test_4k_capture_is_not_reduced_to_1080p_for_ocr(monkeypatch, qapp):
    install_screens(monkeypatch, screen(QRect(0, 0, 1920, 1080), 2))
    capture = capture_desktop()
    assert capture.screens[0].pixmap.size() == QSize(3840, 2160)
    crop = capture.crop_screen(capture.screens[0], QRect(0, 0, 1920, 1080))
    assert crop.image.size() == QSize(3840, 2160)


def test_mixed_dpi_negative_origins_and_gaps_preserve_geometry(monkeypatch, qapp):
    left = screen(QRect(-800, -200, 800, 600), 1.25, "red")
    right = screen(QRect(200, 0, 1000, 800), 2, "blue")
    install_screens(monkeypatch, right, left)
    capture = capture_desktop()
    assert capture.geometry == QRect(-800, -200, 2000, 1000)
    assert capture.monitor_rects == (QRect(1000, 200, 1000, 800), QRect(0, 0, 800, 600))
    image = capture.pixmap.toImage()
    assert image.pixelColor(10, 10) == QColor("red")
    assert image.pixelColor(1200, 300) == QColor("blue")
    assert image.pixelColor(900, 300) == QColor("black")
    assert capture.crop_screen(capture.screens[0], QRect(100, 100, 80, 40)) is None
    assert capture.crop_screen(capture.screens[1], QRect(850, 200, 50, 50)) is None


def test_current_monitor_uses_pointer_not_primary_and_grabs_only_that_monitor(monkeypatch, qapp):
    primary = screen(QRect(0, 0, 800, 600))
    left = screen(QRect(-600, -100, 600, 900), 1.5, "blue")
    install_screens(monkeypatch, primary, left)
    capture = capture_desktop("current", QPoint(-300, 100))
    assert capture.geometry == left.bounds
    assert capture.pixmap.size() == QSize(600, 900)
    assert len(capture.screens) == 1
    assert primary.grabs == 0
    assert left.grabs == 1
    assert capture.monitor_rects == (QRect(0, 0, 600, 900),)
    crop = capture.crop_screen(capture.screens[0], QRect(100, 200, 80, 20))
    assert crop.image.size() == QSize(120, 30)
    assert crop.map_point(30, 15) == pytest.approx((120, 210))


def test_crop_uses_actual_dimensions_and_rounds_outward(monkeypatch, qapp):
    # Deliberately make the native dimensions differ from the DPR metadata.
    install_screens(monkeypatch, screen(QRect(0, 0, 80, 60), 1.5,
                                       pixel_size=QSize(101, 91)))
    capture = capture_desktop()
    crop = capture.crop_screen(capture.screens[0], QRect(1, 1, 3, 3))
    assert crop.native_rect == QRect(1, 1, 5, 6)
    assert crop.map_point(0, 0) == pytest.approx((80 / 101, 60 / 91))
    assert crop.map_point(5, 6) == pytest.approx((6 * 80 / 101, 7 * 60 / 91))


def test_native_crop_is_pixel_exact_not_a_resized_preview(monkeypatch, qapp):
    monitor = screen(QRect(0, 0, 40, 30), 2)
    # A one-physical-pixel stripe must survive even though the preview is smaller.
    image = monitor.shot.toImage()
    image.setPixelColor(21, 20, QColor("blue"))
    monitor.shot = QPixmap.fromImage(image)
    install_screens(monkeypatch, monitor)
    capture = capture_desktop()
    crop = capture.crop_screen(capture.screens[0], QRect(10, 10, 10, 5))
    assert crop.image.pixelColor(1, 0) == QColor("blue")
    assert crop.image.pixelColor(0, 0) == QColor("red")
    assert crop.image.pixelColor(2, 0) == QColor("red")


def test_native_crop_clips_out_of_bounds_selection(monkeypatch, qapp):
    install_screens(monkeypatch, screen(QRect(0, 0, 80, 60), 2))
    capture = capture_desktop()
    crop = capture.crop_screen(capture.screens[0], QRect(-10, -20, 100, 100))
    assert crop.native_rect == QRect(0, 0, 160, 120)
    assert capture.crop_screen(capture.screens[0], QRect()) is None


def test_pointer_in_desktop_gap_does_not_silently_capture_wrong_monitor(monkeypatch, qapp):
    install_screens(monkeypatch, screen(QRect(0, 0, 80, 60)), screen(QRect(100, 0, 80, 60)))
    with pytest.raises(RuntimeError, match="outside the available monitors"):
        capture_desktop("current", QPoint(90, 20))


def test_missing_screen_and_failed_grab_are_explicit_errors(monkeypatch, qapp):
    install_screens(monkeypatch)
    with pytest.raises(RuntimeError, match="available display"):
        capture_desktop()
    install_screens(monkeypatch, FakeScreen(QRect(0, 0, 80, 60), QPixmap()))
    with pytest.raises(RuntimeError, match="could not be captured"):
        capture_desktop()


def test_invalid_scope_does_not_capture(monkeypatch, qapp):
    monitor = screen(QRect(0, 0, 80, 60))
    install_screens(monkeypatch, monitor)
    with pytest.raises(ValueError, match="Capture scope"):
        capture_desktop("unknown")
    assert monitor.grabs == 0
