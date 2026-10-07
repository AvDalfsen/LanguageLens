from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
import pytest

from language_lens.services.capture import DesktopCapture, ScreenCapture
from language_lens.ui.selection import SelectionOverlay


def selector(qapp):
    overlay = SelectionOverlay(DesktopCapture(QPixmap(800, 600), QRect(0, 0, 800, 600)))
    overlay.show()
    return overlay


@pytest.mark.parametrize("close_with_escape", [False, True])
def test_close_and_escape_cancel_exactly_once(qapp, close_with_escape):
    overlay = selector(qapp)
    cancelled, selected = [], []
    overlay.cancelled.connect(lambda: cancelled.append(True))
    overlay.selected.connect(lambda *args: selected.append(args))
    if close_with_escape:
        QTest.keyClick(overlay, Qt.Key.Key_Escape)
    else:
        # Alt+F4/window-manager close reaches the same closeEvent.
        overlay.close()
    overlay.close()
    assert cancelled == [True]
    assert not selected
    assert not overlay.isVisible()


def test_successful_selection_is_not_also_cancelled(qapp):
    overlay = selector(qapp)
    cancelled, selected = [], []
    overlay.cancelled.connect(lambda: cancelled.append(True))
    overlay.selected.connect(lambda *args: selected.append(args))
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 100))
    overlay.close()
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 100))
    assert not cancelled
    assert len(selected) == 1
    capture, region = selected[0]
    assert capture is overlay._capture
    assert region == QRect(QPoint(40, 40), QPoint(200, 100))
    assert not overlay.isVisible()


def test_tiny_selection_stays_open_until_cancelled(qapp):
    overlay = selector(qapp)
    selected, cancelled = [], []
    overlay.selected.connect(lambda *args: selected.append(args))
    overlay.cancelled.connect(lambda: cancelled.append(True))
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(42, 42))
    assert overlay.isVisible()
    assert overlay.selection.isEmpty()
    assert not selected
    assert not cancelled
    overlay.close()
    assert cancelled == [True]


def test_selection_in_desktop_gap_stays_open(qapp):
    capture = DesktopCapture(QPixmap(1000, 600), QRect(-400, 0, 1000, 600), (
        ScreenCapture(QPixmap(400, 600), QRect(-400, 0, 400, 600)),
        ScreenCapture(QPixmap(400, 600), QRect(200, 0, 400, 600)),
    ))
    overlay = SelectionOverlay(capture)
    overlay.show()
    selected = []
    overlay.selected.connect(lambda *args: selected.append(args))
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(450, 200))
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(550, 250))
    assert not selected
    assert overlay.isVisible()
    assert overlay.selection.isEmpty()
    assert "desktop gap" in overlay._hint
    overlay.close()


def test_secondary_monitor_selection_uses_global_coordinates_and_closes_all_tiles(qapp):
    capture = DesktopCapture(QPixmap(1800, 800), QRect(-800, -100, 1800, 800), (
        ScreenCapture(QPixmap(1000, 1600), QRect(-800, -100, 800, 800)),
        ScreenCapture(QPixmap(2000, 1200), QRect(0, 0, 1000, 600)),
    ))
    overlay = SelectionOverlay(capture)
    overlay.show()
    tile = overlay._tiles[0]
    assert overlay.geometry() == capture.screens[0].geometry
    assert tile.geometry() == capture.screens[1].geometry
    assert tile.isWindow() and tile.isVisible()
    selected, cancelled = [], []
    overlay.selected.connect(lambda *args: selected.append(args))
    overlay.cancelled.connect(lambda: cancelled.append(True))
    QTest.mousePress(tile, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    QTest.mouseRelease(tile, Qt.MouseButton.LeftButton, pos=QPoint(200, 140))
    assert len(selected) == 1
    assert selected[0][0] is capture
    assert selected[0][1] == QRect(900, 200, 101, 41)
    assert not cancelled
    assert not overlay.isVisible() and not tile.isVisible()


@pytest.mark.parametrize("escape", [True, False])
def test_close_from_secondary_monitor_cancels_entire_selector_once(qapp, escape):
    capture = DesktopCapture(QPixmap(1800, 600), QRect(0, 0, 1800, 600), (
        ScreenCapture(QPixmap(800, 600), QRect(0, 0, 800, 600)),
        ScreenCapture(QPixmap(1500, 900), QRect(800, 0, 1000, 600)),
    ))
    overlay = SelectionOverlay(capture)
    overlay.show()
    tile = overlay._tiles[0]
    cancelled = []
    overlay.cancelled.connect(lambda: cancelled.append(True))
    if escape:
        QTest.keyClick(tile, Qt.Key.Key_Escape)
    else:
        tile.close()
    assert cancelled == [True]
    assert not overlay.isVisible() and not tile.isVisible()


def test_drag_can_span_monitor_tiles_without_losing_virtual_coordinates(qapp):
    capture = DesktopCapture(QPixmap(1800, 600), QRect(-800, 0, 1800, 600), (
        ScreenCapture(QPixmap(1000, 750), QRect(-800, 0, 800, 600)),
        ScreenCapture(QPixmap(2000, 1200), QRect(0, 0, 1000, 600)),
    ))
    overlay = SelectionOverlay(capture)
    overlay.show()
    selected = []
    overlay.selected.connect(lambda *args: selected.append(args))
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(750, 100))
    QTest.mouseRelease(overlay._tiles[0], Qt.MouseButton.LeftButton, pos=QPoint(100, 140))
    assert selected[0][1] == QRect(750, 100, 151, 41)
