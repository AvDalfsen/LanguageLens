from types import SimpleNamespace

from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMenu

from language_lens.app import LensController, STYLESHEET
from language_lens.services.availability import Availability


def make_menu(qapp):
    menu = QMenu()
    menu.setStyleSheet(STYLESHEET)
    capture = menu.addAction("Capture now")
    settings = menu.addAction("Settings")
    listening = menu.addAction("Start listening")
    menu.addSeparator()
    menu.addAction("Quit")
    capture.setEnabled(False)
    listening.setEnabled(False)
    menu.show()
    qapp.processEvents()
    return menu, capture, settings, listening


def color_count(image, rect, color):
    return sum(image.pixelColor(x, y) == color
               for x in range(rect.left(), rect.right() + 1)
               for y in range(rect.top(), rect.bottom() + 1))


def test_enabled_tray_action_highlights_on_hover_but_disabled_actions_stay_grey(qapp):
    menu, capture, settings, listening = make_menu(qapp)
    hover_color = QColor("#174b50")
    disabled_color = QColor("#6f7b8d")
    QTest.mouseMove(menu, menu.actionGeometry(settings).center())
    qapp.processEvents()
    image = menu.grab().toImage()
    assert menu.activeAction() is settings
    assert color_count(image, menu.actionGeometry(settings), hover_color) > 100
    for action in (capture, listening):
        rect = menu.actionGeometry(action)
        assert color_count(image, rect, disabled_color) > 0
        assert color_count(image, rect, hover_color) == 0
        QTest.mouseMove(menu, rect.center())
        qapp.processEvents()
        assert color_count(menu.grab().toImage(), rect, hover_color) == 0


def test_tray_model_readiness_changes_both_enabled_state_and_rendered_text(qapp):
    menu, capture, _settings, listening = make_menu(qapp)
    controller = SimpleNamespace(_listener=None, _desired_hotkey=None, _busy=False, _shutting_down=False,
        _capture_action=capture, _listening_action=listening,
        setup=SimpleNamespace(capture_ready=True, hotkey_valid=True, availability=Availability(True)),
        tray=SimpleNamespace(setToolTip=lambda _text: None))
    controller._refresh_tray_listening = lambda: LensController._refresh_tray_listening(controller)
    controller._sync_listener = controller._refresh_tray_listening
    def pause():
        controller._listener = None
        controller._refresh_tray_listening()
    controller.pause_listening = pause
    # Match the actual readiness signal, including a later invalidation.
    LensController._readiness_changed(controller, True)
    assert capture.isEnabled() and listening.isEnabled()
    qapp.processEvents()
    enabled = menu.grab().toImage()
    for action in (capture, listening):
        assert color_count(enabled, menu.actionGeometry(action), QColor("#e8eef8")) > 0
    controller.setup.capture_ready = False
    controller.setup.availability = Availability(False)
    LensController._readiness_changed(controller, False)
    assert not capture.isEnabled() and not listening.isEnabled()
    qapp.processEvents()
    disabled = menu.grab().toImage()
    for action in (capture, listening):
        rect = menu.actionGeometry(action)
        assert color_count(disabled, rect, QColor("#6f7b8d")) > 0
        assert color_count(disabled, rect, QColor("#e8eef8")) == 0
