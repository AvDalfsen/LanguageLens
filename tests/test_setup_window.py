from PySide6.QtCore import QCoreApplication, QEvent, QRect, QSize
from PySide6.QtGui import QFontDatabase, QKeySequence
from PySide6.QtWidgets import QBoxLayout, QStyle
from PySide6.QtTest import QTest
from pathlib import Path
import subprocess
import sys
import pytest

from language_lens.app import STYLESHEET
from language_lens.config import Settings
from language_lens.ui.setup import SetupWindow
from language_lens.ui.style import LensStyle
import language_lens.ui.pronunciation as pronunciation
import language_lens.ui.setup as setup


def settle(qapp):
    QTest.qWait(120)
    for _ in range(8):
        qapp.processEvents()


@pytest.fixture(scope="module", autouse=True)
def settings_fonts(qapp):
    # Qt's offscreen backend may not discover Windows fonts automatically.
    fonts = [QFontDatabase.addApplicationFont(str(path))
             for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf")
             if (path := Path("C:/Windows/Fonts") / name).is_file()]
    yield
    for font_id in fonts:
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)


@pytest.fixture
def window_factory(qapp, monkeypatch):
    windows = []
    model_ready = [False]
    original_start = setup.ServiceJob.start
    def start(job, command, payload, *args, **kwargs):
        if command == "status":
            settings = payload["settings"]
            job.event.emit({"result": {"source": settings["source_language"], "target": settings["target_language"],
                "ready": model_ready[0], "prepared": False, "route": []}})
        else:
            original_start(job, command, payload, *args, **kwargs)
    monkeypatch.setattr(setup.ServiceJob, "start", start)
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: True)
    monkeypatch.setattr(pronunciation, "voice_present", lambda *args: False)

    def create(settings=None, area=QRect(0, 0, 1600, 1400)):
        window = SetupWindow(settings or Settings())
        window.setStyleSheet(STYLESHEET)
        monkeypatch.setattr(window, "_available_geometry", lambda: QRect(area))
        windows.append(window)
        window.show()
        settle(qapp)
        return window
    create.model_ready = model_ready

    yield create
    for window in windows:
        window._sizing_timer.stop()
        window._preference_timer.stop()
        window.pronunciation.shutdown()
        window.close()
        window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_default_window_fits_all_settings_without_scrollbars(window_factory):
    window = window_factory()
    assert window.scroll.verticalScrollBar().maximum() == 0
    assert window.scroll.horizontalScrollBar().maximum() == 0
    assert window.current_settings().settings_window_size is None
    assert QRect(0, 0, 1600, 1400).contains(window.frameGeometry())


@pytest.mark.parametrize("area", [QRect(0, 0, 640, 480), QRect(-400, -100, 400, 480)])
def test_small_desktop_limits_window_and_keeps_scrollbars(window_factory, area):
    window = window_factory(area=area)
    assert area.contains(window.frameGeometry())
    assert window.scroll.verticalScrollBar().maximum() > 0
    assert window.current_settings().settings_window_size is None
    assert not window._sizing_timer.isActive()


def test_saved_manual_size_takes_precedence_over_auto_fit(window_factory):
    window = window_factory(Settings(settings_window_size=[760, 520]))
    assert window.size() == QSize(760, 520)
    assert window.scroll.verticalScrollBar().maximum() > 0
    assert window.current_settings().settings_window_size == [760, 520]


def test_oversized_preference_is_clamped_without_overwriting_it(window_factory):
    area = QRect(0, 0, 900, 650)
    window = window_factory(Settings(settings_window_size=[2000, 1800]), area)
    assert area.contains(window.frameGeometry())
    assert window.current_settings().settings_window_size == [2000, 1800]


def test_saved_size_on_narrow_desktop_stacks_footer_buttons(window_factory):
    window = window_factory(Settings(settings_window_size=[900, 650]), QRect(0, 0, 300, 600))
    assert window._button_row.direction() == QBoxLayout.Direction.TopToBottom
    assert window.try_button.parentWidget().rect().contains(window.try_button.geometry())
    assert window.start_button.parentWidget().rect().contains(window.start_button.geometry())


def test_maximized_state_and_normal_size_are_restored(window_factory, qapp):
    window = window_factory(Settings(settings_window_size=[820, 550], settings_window_maximized=True))
    assert window.isMaximized()
    assert window.current_settings().settings_window_maximized
    assert window.current_settings().settings_window_size == [820, 550]
    window.showNormal()
    settle(qapp)
    assert window.size() == QSize(820, 550)
    assert not window.current_settings().settings_window_maximized
    window.showMaximized()
    settle(qapp)
    assert window.current_settings().settings_window_maximized
    assert window.current_settings().settings_window_size == [820, 550]


def test_minimize_does_not_change_saved_size_or_maximized_preference(window_factory, qapp):
    window = window_factory(Settings(settings_window_size=[820, 550]))
    window.showMinimized()
    settle(qapp)
    assert window.current_settings().settings_window_size == [820, 550]
    assert not window.current_settings().settings_window_maximized
    window.showNormal()
    settle(qapp)
    assert window.size() == QSize(820, 550)


def test_manual_resize_is_remembered_and_immediately_flushed_on_hide(window_factory, qapp):
    window = window_factory()
    notifications = []
    window.window_preferences_changed.connect(lambda: notifications.append(window.current_settings()))
    window.resize(820, 550)
    settle(qapp)
    assert window.current_settings().settings_window_size == [820, 550]
    window.hide()
    assert len(notifications) == 1
    assert notifications[0].settings_window_size == [820, 550]
    window.show()
    settle(qapp)
    assert window.size() == QSize(820, 550)


def test_layout_growth_auto_fits_but_does_not_override_manual_size(window_factory, qapp):
    window = window_factory()
    initial = window.size()
    window.model_progress.show()
    window.model_details.setText("Download progress and speed")
    window.model_details.show()
    settle(qapp)
    assert window.height() > initial.height()
    assert window.scroll.verticalScrollBar().maximum() == 0
    assert window.current_settings().settings_window_size is None
    window.resize(800, 520)
    window.model_details.setText("Additional details " * 100)
    settle(qapp)
    assert window.size() == QSize(800, 520)


@pytest.mark.parametrize("source", ["en", "pt", "de", "ja"])
@pytest.mark.parametrize("models_ready", [False, True])
def test_auto_fit_handles_language_and_model_status_changes(
    window_factory, qapp, monkeypatch, source, models_ready,
):
    window = window_factory()
    window_factory.model_ready[0] = models_ready
    window.source.setCurrentIndex(window.source.findData(source))
    window.refresh_model_status()
    settle(qapp)
    assert window.scroll.verticalScrollBar().maximum() == 0
    assert window.scroll.horizontalScrollBar().maximum() == 0
    assert window.current_settings().settings_window_size is None
    assert not window._sizing_timer.isActive()


def test_auto_fit_remeasures_larger_styled_text(window_factory, qapp):
    window = window_factory()
    initial_height = window.height()
    window.setStyleSheet(STYLESHEET.replace("14px", "20px").replace("12px", "17px"))
    settle(qapp)
    assert window.height() > initial_height
    # A taller layout should use the available width before falling back to scroll.
    assert window.scroll.verticalScrollBar().maximum() == 0
    assert window.scroll.horizontalScrollBar().maximum() == 0
    assert window.current_settings().settings_window_size is None


def test_option_help_covers_behaviour_and_tradeoffs(window_factory):
    window = window_factory()
    controls = [window.source, window.target, window.hotkey, window.capture_scope,
                window.start_button, window.try_button, window.prepare_button,
                window.pronunciation.enabled, window.pronunciation.show_ipa,
                window.pronunciation.voices, window.pronunciation.install, window.pronunciation.preview]
    assert all(len(control.toolTip()) > 150 for control in controls)
    assert all(control.toolTipDuration() == 30_000 for control in controls)
    assert "less memory" in window.capture_scope.toolTip()
    assert "other monitors uncovered" in window.capture_scope.toolTip()
    assert "reduces screenshot/rendering work" in window.capture_scope.toolTip()


def test_local_file_and_maintenance_labels_do_not_imply_online_mode_or_detected_fault(window_factory):
    from html import unescape
    window = window_factory()
    assert window.prepare_button.text() == "Download required files"
    assert "no online translation mode" in window.prepare_button.toolTip()
    assert window.repair_button.text() == "Reinstall translation model"
    assert "does not mean a problem has been detected" in window.repair_button.toolTip()
    window._apply_model_status({"ready": True, "prepared": True, "route": ["pt", "en"]})
    assert window.prepare_button.text() == "Check required files"
    assert "checked and ready" in window.capabilities.text()
    assert window.start_button.text() == "Start listening"
    assert "'Start listening'" in unescape(window.hotkey.toolTip())


def test_missing_pair_has_one_setup_action_and_uses_full_preparation(window_factory, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    window = window_factory(Settings(source_language="nl", target_language="fr"))
    calls = []
    monkeypatch.setattr(setup.ServiceJob, "start", lambda job, command, payload: calls.append((command, payload)))
    assert "missing for this language pair" in window.model_status.text()
    assert not hasattr(window, "install_button")
    downloads = [button for button in window.findChildren(QPushButton)
                 if button.text().startswith("Download") and button is not window.pronunciation.install
                 and not window.maintenance.isAncestorOf(button)]
    assert downloads == [window.prepare_button]
    assert window.prepare_button.isEnabled()
    assert not window.repair_button.isEnabled()
    window.prepare_button.click()
    assert len(calls) == 1 and calls[0][0] == "prepare"
    assert calls[0][1]["settings"]["source_language"] == "nl"
    assert calls[0][1]["settings"]["target_language"] == "fr"
    assert window._installing and not window.prepare_button.isEnabled()
    assert not window.cancel_button.isHidden()
    window.model_job.finished.emit()
    assert window.prepare_button.isEnabled() and not window._installing
    window._apply_model_status({"ready": True, "prepared": False, "route": ["nl", "en", "fr"]})
    assert window.prepare_button.text() == "Download required files"
    window._apply_model_status({"ready": True, "prepared": True, "route": ["nl", "en", "fr"]})
    assert window.prepare_button.text() == "Check required files"


def test_named_controls_in_settings_help_are_single_quoted(window_factory):
    import re
    from html import unescape
    from PySide6.QtWidgets import QWidget, QLabel
    window = window_factory()
    names = ["Start listening", "Try a capture now", "Quit", "Settings", "Text language",
             "All monitors", "Monitor under the pointer", "Check required files", "Cancel model task",
             "Check voice files", "Cancel download", "Stop sample", "Hear sample"]
    for widget in window.findChildren(QWidget):
        texts = [unescape(widget.toolTip())]
        if isinstance(widget, QLabel):
            texts.append(unescape(widget.text()))
        for text in texts:
            if text in names:
                continue  # a form's label is the element itself, not a reference in prose
            for name in names:
                for match in re.finditer(re.escape(name), text):
                    assert text[max(0, match.start() - 1):match.start()] == "'", (name, text)
                    assert text[match.end():match.end() + 1] == "'", (name, text)


def test_main_button_starts_pauses_and_restarts_the_controller_listener(window_factory, monkeypatch):
    from types import SimpleNamespace
    import language_lens.app as app_module
    window = window_factory()
    window._apply_model_status({"ready": True, "prepared": True, "route": ["pt", "en"]})
    listeners = []
    class Listener:
        def __init__(self, hotkey, _callback):
            self.hotkey, self.started, self.stopped = hotkey, False, False
            listeners.append(self)
        def start(self):
            self.started = True
        def stop(self):
            self.stopped = True
    monkeypatch.setattr(app_module, "WindowsHotkeyListener", Listener)
    monkeypatch.setattr(app_module, "persist", lambda *_args: None)
    controller = SimpleNamespace(settings=Settings(), _listener=None, setup=window,
        _capture_allowed=lambda _settings: window.capture_ready,
        _refresh_tray_listening=lambda: None,
        global_capture=SimpleNamespace(emit=lambda: None),
        tray=SimpleNamespace(setToolTip=lambda _text: None, showMessage=lambda *_args: None))
    window.listen_requested.connect(lambda settings: app_module.LensController.start_listening(controller, settings))
    window.pause_requested.connect(lambda: app_module.LensController.pause_listening(controller))
    window.start_button.click()
    assert listeners[0].started and window.start_button.text() == "Pause listening"
    assert window.current_settings().hotkey == listeners[0].hotkey and not window.hotkey.isEnabled()
    window.start_button.click()
    assert listeners[0].stopped and controller._listener is None
    assert window.start_button.text() == "Start listening" and window.hotkey.isEnabled()
    window.hotkey.setKeySequence(QKeySequence("Ctrl+Alt+Q"))
    window.start_button.click()
    assert listeners[-1].started and listeners[-1].hotkey == "<ctrl>+<alt>+q"
    assert window.start_button.text() == "Pause listening"
    app_module.LensController.pause_listening(controller)


def test_pause_stays_available_when_models_are_checked_missing_or_downloading(window_factory, monkeypatch):
    window = window_factory()
    window.set_listening("<f8>")
    window.refresh_model_status()
    assert window.start_button.isEnabled() and window.start_button.text() == "Pause listening"
    window._apply_model_status({"ready": False, "prepared": False, "route": []})
    assert window.start_button.isEnabled()
    monkeypatch.setattr(setup.ServiceJob, "start", lambda *_args: None)
    window._start_model_job("prepare")
    assert window._installing and window.start_button.isEnabled()
    window.set_listening(None)
    assert not window.start_button.isEnabled() and window.hotkey.isEnabled()
    assert window.start_button.text() == "Start listening"


@pytest.mark.parametrize("ready,prepared", [(False, False), (False, True), (True, False), (True, True)])
def test_capture_controls_require_verified_ocr_and_translation(window_factory, ready, prepared):
    window = window_factory()
    assert not window.try_button.isEnabled() and not window.start_button.isEnabled()
    window._apply_model_status({"ready": ready, "prepared": prepared, "route": []})
    assert window.capture_ready == (ready and prepared)
    assert window.try_button.isEnabled() == (ready and prepared)
    assert window.start_button.isEnabled() == (ready and prepared)
    window.set_capture_busy(True)
    assert not window.try_button.isEnabled() and not window.start_button.isEnabled()
    window.set_capture_busy(False)
    assert window.try_button.isEnabled() == (ready and prepared)
    window.refresh_model_status()
    assert not window.try_button.isEnabled() and not window.start_button.isEnabled()


def test_pair_change_and_model_work_invalidate_readiness(window_factory, monkeypatch):
    window = window_factory()
    changes = []
    window.readiness_changed.connect(changes.append)
    window._apply_model_status({"ready": True, "prepared": True, "route": []})
    window.target.setCurrentIndex(window.target.findData("fr"))
    assert changes == [True, False] and not window.capture_ready
    window._apply_model_status({"ready": True, "prepared": True, "route": []})
    monkeypatch.setattr(setup.ServiceJob, "start", lambda *_args: None)
    window._start_model_job("prepare")
    assert changes == [True, False, True, False]
    assert not window.try_button.isEnabled() and not window.start_button.isEnabled()
    window.model_job.finished.emit()
    assert not window.try_button.isEnabled() and not window.start_button.isEnabled()


def test_shortcut_recorder_accepts_keypress_and_remembers_custom_choice(window_factory, qapp):
    from PySide6.QtCore import Qt
    window = window_factory()
    changed = []
    window.hotkey_changed.connect(changed.append)
    assert window.hotkey.keySequence().toString() == "F8"
    assert window.hotkey.maximumSequenceLength() == 1
    window.hotkey.setFocus()
    QTest.keyClick(window.hotkey, Qt.Key.Key_Q, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
    QTest.qWait(1100)
    assert window.current_settings().hotkey == "<ctrl>+<alt>+q"
    assert changed == ["<ctrl>+<alt>+q"] and window.hotkey_valid
    restored = window_factory(window.current_settings())
    assert restored.hotkey.keySequence().toString() == "Ctrl+Alt+Q"
    window.reset_hotkey.click()
    assert window.current_settings().hotkey == "<f8>" and changed[-1] == "<f8>"


def test_unsupported_shortcut_disables_listening_but_not_capture(window_factory):
    window = window_factory()
    window._apply_model_status({"ready": True, "prepared": True, "route": []})
    for text in ("F12", "Meta+Q", ";", ""):
        window.hotkey.setKeySequence(QKeySequence(text))
        assert not window.hotkey_valid and not window.start_button.isEnabled()
        assert window.try_button.isEnabled()
        assert window.hotkey_note.text() != "Click the shortcut field and press your preferred key combination."
        assert window.current_settings().hotkey == "<f8>"  # last valid setting, not broken config
    window.reset_hotkey.click()
    assert window.hotkey_valid and window.start_button.isEnabled()


def test_clicking_shortcut_shows_listening_prompt_and_blur_restores_previous_value(window_factory, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLineEdit
    window = window_factory(Settings(hotkey="<ctrl>+<alt>+q"))
    window.target.setFocus()
    qapp.processEvents()
    display = window.hotkey.findChild(QLineEdit)
    changed = []
    window.hotkey_changed.connect(changed.append)
    QTest.mouseClick(display, Qt.MouseButton.LeftButton)
    assert display.text() == "Listening for new hotkey..."
    assert window.current_settings().hotkey == "<ctrl>+<alt>+q"
    assert window.hotkey_valid
    window.target.setFocus()
    qapp.processEvents()
    assert display.text() == "Ctrl+Alt+Q"
    assert window.hotkey.keySequence().toString() == "Ctrl+Alt+Q"
    assert window.current_settings().hotkey == "<ctrl>+<alt>+q"
    assert changed == []


def test_modifier_only_or_tab_does_not_replace_shortcut(window_factory, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLineEdit
    window = window_factory()
    window.target.setFocus()
    display = window.hotkey.findChild(QLineEdit)
    changed = []
    window.hotkey_changed.connect(changed.append)
    for key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Tab):
        QTest.mouseClick(display, Qt.MouseButton.LeftButton)
        QTest.keyClick(window.hotkey, key)
        window.target.setFocus()
        qapp.processEvents()
        assert display.text() == "F8"
        assert window.hotkey_valid and window.current_settings().hotkey == "<f8>"
    assert changed == []


def test_popup_focus_loss_also_restores_shortcut_display(window_factory, qapp):
    from PySide6.QtCore import Qt, QEvent
    from PySide6.QtGui import QFocusEvent
    from PySide6.QtWidgets import QLineEdit
    window = window_factory()
    window.target.setFocus()
    display = window.hotkey.findChild(QLineEdit)
    QTest.mouseClick(display, Qt.MouseButton.LeftButton)
    assert display.text() == "Listening for new hotkey..."
    qapp.sendEvent(window.hotkey, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.PopupFocusReason))
    assert display.text() == "F8" and window.current_settings().hotkey == "<f8>"


def test_new_shortcut_is_kept_and_second_click_can_cancel_without_clearing_it(window_factory, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLineEdit
    window = window_factory()
    window.target.setFocus()
    display = window.hotkey.findChild(QLineEdit)
    changed = []
    window.hotkey_changed.connect(changed.append)
    QTest.mouseClick(display, Qt.MouseButton.LeftButton)
    QTest.keyClick(window.hotkey, Qt.Key.Key_F9)
    assert window.current_settings().hotkey == "<f9>"
    assert display.text() == "F9"
    QTest.mouseClick(display, Qt.MouseButton.LeftButton)
    assert display.text() == "Listening for new hotkey..."
    window.target.setFocus()
    qapp.processEvents()
    assert display.text() == "F9" and window.current_settings().hotkey == "<f9>"
    assert changed == ["<f9>"]


def test_modifier_only_timeout_restores_current_shortcut_after_listening_was_paused(window_factory, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLineEdit
    window = window_factory()
    window.set_listening("<f9>")
    window.set_listening(None)
    window.target.setFocus()
    display = window.hotkey.findChild(QLineEdit)
    QTest.mouseClick(display, Qt.MouseButton.LeftButton)
    QTest.keyClick(window.hotkey, Qt.Key.Key_Control)
    QTest.qWait(1100)
    assert display.text() == "Listening for new hotkey..."
    window.target.setFocus()
    qapp.processEvents()
    assert display.text() == "F9" and window.current_settings().hotkey == "<f9>"
    assert window.hotkey_valid


def test_recorded_shortcut_is_saved_without_starting_listening(window_factory, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from language_lens.config import save_settings, load_settings
    import language_lens.app as app_module
    window = window_factory()
    path = tmp_path / "settings.json"
    monkeypatch.setattr(app_module, "save_settings", lambda settings: save_settings(settings, path))
    controller = SimpleNamespace(settings=Settings(), setup=window, _refresh_tray_listening=lambda: None)
    window.hotkey_changed.connect(lambda value: app_module.LensController._save_hotkey(controller, value))
    window.hotkey.setKeySequence(QKeySequence("Alt+Shift+9"))
    assert load_settings(path).hotkey == "<alt>+<shift>+9"
    reopened = window_factory(load_settings(path))
    assert reopened.hotkey.keySequence().toString() == "Alt+Shift+9"
    assert window._active_hotkey is None and reopened._active_hotkey is None


def test_tooltip_style_is_near_instant_and_preserves_other_style_hints(qapp):
    style = LensStyle(qapp.style().objectName())
    assert style.styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay) == 50
    assert style.styleHint(QStyle.StyleHint.SH_ToolTip_FallAsleepDelay) == (
        style.baseStyle().styleHint(QStyle.StyleHint.SH_ToolTip_FallAsleepDelay)
    )
    style.deleteLater()


def test_tooltip_delay_survives_application_stylesheet(qapp):
    # Production installs the style once, before creating widgets. Replacing
    # QApplication's native style with widgets from earlier tests still alive
    # exercises a different, unsafe Qt ownership/lifecycle path on Windows.
    script = """
import ctypes, sys
if sys.platform == 'win32':
    ctypes.windll.kernel32.SetErrorMode(3)
from PySide6.QtWidgets import QApplication, QStyle, QComboBox
from language_lens.app import STYLESHEET
from language_lens.ui.style import LensStyle
app = QApplication([])
app.setStyle(LensStyle(app.style().objectName()))
app.setStyleSheet(STYLESHEET)
widget = QComboBox()
assert widget.style().styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay) == 50
widget.close()
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
