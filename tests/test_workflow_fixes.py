"""Audit 1–7 regressions, using actual widgets without desktop capture/downloads."""
from copy import deepcopy
import errno
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QFontDatabase, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QSystemTrayIcon

from language_lens import app as app_module
from language_lens.config import Settings
from language_lens.services.capture import DesktopCapture
from language_lens.services import startup, task_worker
from language_lens.services.errors import KnownTaskError, describe_failure
from language_lens.services.translation import ArgosTranslator, ModelRouteUnavailable
from language_lens.ui import pronunciation, review, setup


class FakeSpeechJob(QObject):
    activity_changed = Signal(bool)
    progress = Signal(int, int)
    stage_changed = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.calls = []

    def start(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.active = True
        self.activity_changed.emit(True)

    def cancel(self):
        self.active = False
        self.activity_changed.emit(False)
        self.cancelled.emit()

    def shutdown(self):
        if self.active:
            self.cancel()


class FakeTray(QObject):
    activated = Signal(object)
    ActivationReason = QSystemTrayIcon.ActivationReason
    MessageIcon = QSystemTrayIcon.MessageIcon

    def __init__(self, _icon, parent):
        super().__init__(parent)
        self.messages = []

    def setContextMenu(self, menu):
        self.menu = menu

    def setToolTip(self, text):
        self.tooltip = text

    def showMessage(self, *args):
        self.messages.append(args)

    def show(self):
        pass

    def hide(self):
        pass


@pytest.fixture
def controller(qapp, monkeypatch):
    saved, jobs, listeners, warnings = [], [], [], []

    class Listener:
        def __init__(self, hotkey, callback):
            self.hotkey, self.callback, self.stopped = hotkey, callback, False
            listeners.append(self)

        def start(self):
            if getattr(self, "fail", False):
                raise RuntimeError("Occupied shortcut")

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(app_module, "load_settings", lambda: Settings(source_language="en", target_language="nl"))
    monkeypatch.setattr(app_module, "save_settings", lambda value: saved.append(deepcopy(value)))
    monkeypatch.setattr(app_module, "QSystemTrayIcon", FakeTray)
    monkeypatch.setattr(app_module, "WindowsHotkeyListener", Listener)
    monkeypatch.setattr(app_module, "offline_ready", lambda *_args: True)
    monkeypatch.setattr(app_module, "record_failure", lambda *_args: None)
    monkeypatch.setattr(app_module, "foreground_window", lambda: 123)
    monkeypatch.setattr(app_module, "restore_foreground", lambda *_args: None)
    monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *_args: warnings.append(True))
    monkeypatch.setattr(setup.ServiceJob, "start", lambda _job, command, *_args: jobs.append(command))
    monkeypatch.setattr(pronunciation, "SpeechJob", FakeSpeechJob)
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: True)
    monkeypatch.setattr(pronunciation, "voice_present", lambda *_args: False)
    monkeypatch.setattr(review, "TaskPool", SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=lambda _task: None)))
    image = QPixmap(1280, 720)
    image.fill(Qt.GlobalColor.black)
    monkeypatch.setattr(app_module, "capture_desktop", lambda *_args: DesktopCapture(image, image.rect()))
    lens = app_module.LensController(qapp)
    lens.saved, lens.jobs, lens.listeners, lens.warnings = saved, jobs, listeners, warnings
    lens.setup._status_timer.stop()
    lens.setup._apply_model_status({"ready": True, "prepared": True, "route": ["en", "nl"]})
    yield lens
    lens._shutdown()
    qapp.aboutToQuit.disconnect(lens._shutdown)
    lens.tray.menu.close()
    lens.tray.menu.deleteLater()
    lens.setup.close()
    lens.setup.deleteLater()
    lens.deleteLater()


def test_voice_download_updates_every_capture_entry_and_preserves_pause(controller):
    lens = controller
    lens.start_listening(lens.setup.current_settings())
    original = lens._listener
    lens.setup.pronunciation._install()
    assert original.stopped and lens._listener is None
    assert lens._desired_hotkey == "<f8>"
    assert not lens.setup.try_button.isEnabled() and not lens._capture_action.isEnabled()
    assert lens.setup.start_button.text() == lens._listening_action.text() == "Pause listening"
    assert lens.setup.start_button.isEnabled() and lens._listening_action.isEnabled()
    assert not lens.setup.prepare_button.isEnabled()
    assert lens.setup.pronunciation.install.text() == "Cancel download"
    lens.begin_capture(True)
    assert not lens._busy
    lens.setup.pronunciation.download.cancel()
    assert lens._listener is not None and lens.setup.try_button.isEnabled()


@pytest.mark.parametrize("hotkey", ["<escape>", "<right>", "<ctrl>+h"])
def test_global_shortcut_suspended_across_selection_review_and_reselection(controller, hotkey, qapp):
    lens = controller
    lens.setup._hotkey_value = hotkey
    lens.start_listening(lens.setup.current_settings())
    original = lens._listener
    lens.begin_capture(True)
    assert original.stopped and lens._listener is None
    assert not lens._capture_action.isEnabled()
    assert not lens.setup.pronunciation.install.isEnabled()
    calls = len(lens.setup.pronunciation.download.calls)
    lens.setup.pronunciation._install()
    assert len(lens.setup.pronunciation.download.calls) == calls
    capture = lens._selector._capture
    lens._selector.selected.emit(capture, QRect(30, 100, 600, 50))
    assert lens._review is not None and lens._listener is None
    lens._review.reselect_requested.emit(capture)
    assert lens._selector is not None and lens._listener is None
    QTest.keyClick(lens._selector, Qt.Key.Key_Escape)
    qapp.processEvents()
    assert not lens._busy and lens._listener is not None
    assert lens._listener.hotkey == hotkey


def test_settings_temporarily_suspend_shortcut_and_pause_during_review_is_final(controller):
    lens = controller
    lens.start_listening(lens.setup.current_settings())
    original = lens._listener
    lens.show_settings()
    assert original.stopped and lens._listener is None
    assert lens.setup.start_button.text() == "Pause listening"
    lens.setup.hide()
    assert lens._listener is not None
    lens.begin_capture(True)
    lens._listening_action.trigger()
    lens._session_finished()
    assert lens._desired_hotkey is None and lens._listener is None
    assert lens._listening_action.text() == "Start listening"


def test_hotkey_conflict_on_restore_reports_inactive_state(controller, monkeypatch):
    lens = controller
    lens.start_listening(lens.setup.current_settings())
    lens.begin_capture(True)
    def fail(*_args):
        raise RuntimeError("Could not initialize listener")
    monkeypatch.setattr(app_module, "WindowsHotkeyListener", fail)
    lens._session_finished()
    assert lens.warnings and lens.setup.isVisible()
    assert lens._listener is None and lens._desired_hotkey is None
    assert lens._listening_action.text() == "Start listening"


def test_preferences_autosave_and_capture_uses_independent_snapshot(controller, qapp):
    lens = controller
    lens.setup.show()
    lens.setup.pronunciation.show_ipa.setChecked(True)
    lens.setup.capture_scope.setCurrentIndex(lens.setup.capture_scope.findData("all"))
    QTest.qWait(340)
    assert lens.saved[-1].show_ipa and lens.saved[-1].capture_scope == "all"
    lens.begin_capture(False)
    frozen = lens._capture_settings
    assert frozen.show_ipa
    lens.setup.pronunciation.show_ipa.setChecked(False)
    lens._save_preferences()
    assert not lens.settings.show_ipa and frozen.show_ipa
    assert frozen is not lens.settings
    lens.setup.pronunciation.show_ipa.setChecked(True)
    lens._shutdown()
    assert lens.saved[-1].show_ipa and not lens._save_timer.isActive()


def test_close_to_tray_saves_preferences_and_explains_it_only_once(controller):
    lens = controller
    lens.setup.show()
    lens.setup.pronunciation.show_ipa.setChecked(True)
    lens.setup.close()
    assert lens.saved[-1].show_ipa and lens.saved[-1].tray_close_notice_shown
    assert len(lens.tray.messages) == 1
    lens.setup.show()
    lens.setup.close()
    assert len(lens.tray.messages) == 1


def test_failed_inspection_is_unknown_not_missing_and_retry_does_not_download(controller):
    lens = controller
    lens.setup._status_failed("Windows denied access to local files.")
    assert not lens.setup.capture_ready
    assert "not installed" not in lens.setup.model_status.text()
    assert "unknown" in lens.setup.capabilities.text()
    assert lens.setup.prepare_button.text() == "Retry file check"
    assert not lens.setup.diagnostics_button.isHidden()
    lens.setup.prepare_button.click()
    lens.setup._status_timer.stop()
    lens.setup._start_status_check()
    assert lens.jobs[-1] == "status" and "prepare" not in lens.jobs


def test_late_maintenance_completion_cannot_restart_checks_after_shutdown(controller):
    lens = controller
    lens.setup._installing = True
    lens._shutdown()
    count = len(lens.jobs)
    lens.setup._install_finished()
    lens.setup._start_status_check()
    assert len(lens.jobs) == count and not lens.setup._status_timer.isActive()
    assert not lens.setup.try_button.isEnabled() and not lens._capture_action.isEnabled()


@pytest.mark.parametrize("width,height", [(1280, 720), (640, 360)])
def test_large_selection_keeps_full_controls_visible_and_movable(monkeypatch, qapp, width, height):
    monkeypatch.setattr(review, "TaskPool", SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=lambda _task: None)))
    image = QPixmap(width, height)
    image.fill(Qt.GlobalColor.black)
    window = review.ReviewWindow(image, QRect(30, 80, width - 60, height - 160), Settings(speech_enabled=False))
    window.setStyleSheet(app_module.STYLESHEET)
    window.show()
    qapp.processEvents()
    assert window._footer.isVisible() and window.rect().contains(window._footer.geometry())
    labels = [button.text() for button in window.findChildren(review.QPushButton)]
    assert not {"Move", "Hide controls", "Show controls"}.intersection(labels)
    assert sum(label.startswith("Close") for label in labels) == 1
    window.activateWindow()
    QTest.keyClick(window, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
    qapp.processEvents()
    assert window._footer.isVisible()
    assert "Ctrl+H" not in [shortcut.key().toString() for shortcut in window._shortcuts]
    assert window._action_columns in (1, 2, 3)
    assert window._actions_body.minimumSizeHint().width() <= window._actions_scroll.viewport().width()
    if height == 360:
        assert window._actions_scroll.verticalScrollBar().maximum() > 0, (
            window._actions_scroll.size(), window._actions_body.size(),
            window._actions_body.minimumSizeHint(), window._actions_body.layout().sizeHint(),
            window._footer.geometry(), window.canvas.monitor_display_rect(window.canvas.selection_display_rect()))
    window._move_controls(QPoint(10000, -10000))
    assert window.rect().contains(window._footer.geometry())
    position = window._footer.pos()
    window.status.setText("A delayed worker result arrived.")
    window._position_children()
    assert window._footer.pos() == position
    window.close()


@pytest.mark.parametrize("surface", ["frame", "status", "viewport"])
def test_panel_background_drag_moves_without_a_toolbar(monkeypatch, qapp, surface):
    monkeypatch.setattr(review, "TaskPool", SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=lambda _task: None)))
    window = review.ReviewWindow(QPixmap(1280, 900), QRect(300, 130, 500, 50), Settings(speech_enabled=False))
    window.show()
    qapp.processEvents()
    panel = window._footer
    target = {"frame": panel, "status": window.status, "viewport": window._footer_scroll.viewport()}[surface]
    # The viewport centre can now contain the interactive recognized-text
    # disclosure. Exercise its background, not an arbitrary child control.
    point = QPoint(3, 3) if surface in {"frame", "viewport"} else target.rect().center()
    original = panel.pos()
    QTest.mousePress(target, Qt.MouseButton.LeftButton, pos=point)
    assert panel._drag_point is not None
    # Once dragging starts the frame receives mouse movement via its grab.
    current = target.mapTo(panel, point)
    QTest.mouseMove(panel, current + QPoint(55, 25))
    QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=current)
    assert panel.pos() == original + QPoint(55, 25)
    assert panel._drag_point is None
    assert window.canvas._tooltip_avoid_rect.contains(panel.geometry())
    window.close()


def test_panel_drag_does_not_intercept_buttons_sliders_or_scrollbars(monkeypatch, qapp):
    monkeypatch.setattr(review, "TaskPool", SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=lambda _task: None)))
    window = review.ReviewWindow(QPixmap(1280, 900), QRect(300, 130, 500, 50), Settings(speech_enabled=False))
    window.show()
    qapp.processEvents()
    panel, original = window._footer, window._footer.pos()
    requested = []
    window.reselect_requested.connect(requested.append)
    QTest.mouseClick(window.reselect, Qt.MouseButton.LeftButton)
    assert requested and panel.pos() == original and panel._drag_point is None
    window._translation_finished(("Long text " * 500, {}))
    window.speed_slider.setEnabled(True)
    qapp.processEvents()
    for control in (window.speed_slider, window._footer_scroll.verticalScrollBar()):
        point = control.rect().center()
        QTest.mousePress(control, Qt.MouseButton.LeftButton, pos=point)
        assert panel._drag_point is None
        QTest.mouseRelease(control, Qt.MouseButton.LeftButton, pos=point)
        assert panel.pos() == original
    window.read_button.setEnabled(False)
    QTest.mouseClick(window.read_button, Qt.MouseButton.LeftButton)
    assert panel._drag_point is None
    window.close()


def test_japanese_settings_widen_to_fit_without_overwriting_manual_size(controller, qapp):
    font_ids = [QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
                for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf")]
    window = controller.setup
    window.setStyleSheet(app_module.STYLESHEET)
    window._available_geometry = lambda: QRect(0, 0, 1920, 1080)
    window.source.setCurrentIndex(window.source.findData("ja"))
    window._status_timer.stop()
    window.show()
    QTest.qWait(150)
    assert window.scroll.verticalScrollBar().maximum() == 0
    assert window.current_settings().settings_window_size is None
    window.resize(800, 600)
    window._fit_or_restore_size()
    assert window.width() == 800 and window.height() == 600
    for font in font_ids:
        if font >= 0:
            QFontDatabase.removeApplicationFont(font)


def test_narrow_review_keeps_canvas_and_close_controls_on_screen(monkeypatch, qapp):
    monkeypatch.setattr(review, "TaskPool", SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=lambda _task: None)))
    image = QPixmap(320, 480)
    image.fill(Qt.GlobalColor.black)
    window = review.ReviewWindow(image, QRect(30, 90, 260, 40), Settings(speech_enabled=False))
    window.setStyleSheet(app_module.STYLESHEET)
    window.show()
    qapp.processEvents()
    assert window.canvas.size() == window.size()
    assert window.rect().contains(window._footer.geometry())
    assert window._action_columns == 1
    close_rect = QRect(window._close_button.mapTo(window, QPoint()), window._close_button.size())
    assert window.rect().contains(close_rect)
    assert window._close_button.parentWidget() is window._footer
    window.close()


@pytest.mark.parametrize("error,code", [
    (PermissionError("PRIVATE OCR"), "permission"),
    (OSError(errno.ENOSPC, "PRIVATE OCR"), "disk_full"),
    (URLError("PRIVATE OCR"), "network"),
    (TimeoutError("PRIVATE OCR"), "timeout"),
    (ModelRouteUnavailable("PRIVATE OCR"), "route_unavailable"),
    (KnownTaskError("integrity"), "integrity"),
    (ImportError("PRIVATE OCR"), "runtime"),
])
def test_failure_categories_follow_causes_without_leaking_text(error, code):
    wrapper = RuntimeError("PRIVATE CAPTURE")
    wrapper.__cause__ = error
    failure = describe_failure(wrapper, "prepare")
    assert failure.code == code and failure.stage == "prepare"
    assert "PRIVATE" not in json.dumps(failure.event())


def test_inspection_exception_is_not_swallowed_as_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ArgosTranslator, "is_pair_installed", lambda *_args: (_ for _ in ()).throw(PermissionError("secret")))
    with pytest.raises(PermissionError):
        task_worker.execute("status", {"settings": {"source_language": "en", "target_language": "nl"}}, tmp_path, lambda *_args: None)


@pytest.mark.parametrize("error", [AttributeError("private"), KeyError("private"), StopIteration("private")])
def test_backend_enumeration_errors_are_not_reported_as_missing(monkeypatch, error):
    def failed():
        raise error
    monkeypatch.setattr(ArgosTranslator, "_modules", lambda *_args: (None, SimpleNamespace(get_installed_languages=failed)))
    with pytest.raises(type(error)):
        ArgosTranslator().is_pair_installed("en", "nl")


def test_startup_handshake_is_atomic_scoped_and_diagnostics_hide_exception_text(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = tmp_path / "LanguageLens"
    root.mkdir()
    path = root / ("startup-" + "a" * 32 + ".json")
    monkeypatch.setenv("LANGUAGE_LENS_STARTUP_FILE", str(path))
    startup.report_startup("ready")
    assert json.loads(path.read_text())["status"] == "ready"
    assert not path.with_suffix(".tmp").exists()
    monkeypatch.setenv("LANGUAGE_LENS_STARTUP_FILE", str(root / "settings.json"))
    startup.report_startup("ready")
    assert not (root / "settings.json").exists()
    try:
        raise ImportError("PRIVATE OCR")
    except ImportError as error:
        startup.record_startup_failure(error)
    assert "PRIVATE" not in (root / "logs" / "startup.log").read_text()


def powershell(script, *, env=None):
    return subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                          capture_output=True, text=True, timeout=45, env=env)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
def test_launcher_preflight_and_recoverable_environment_backup(tmp_path):
    helper = Path(__file__).resolve().parents[1] / "scripts" / "environment.ps1"
    environment = tmp_path / ".venv"
    environment.mkdir()
    (environment / "keep.txt").write_text("old environment")
    script = f". '{helper}'; Test-LensPython '{sys.executable}' -RequirePip; Test-LensEnvironment '{tmp_path}'; Backup-LensEnvironment '{tmp_path}' | Out-Null"
    result = powershell(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[:2] == ["True", "False"]
    backups = list(tmp_path.glob(".venv.backup-*"))
    assert len(backups) == 1 and (backups[0] / "keep.txt").read_text() == "old environment"
    assert not environment.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
def test_recovery_checks_package_health_and_finds_python_before_moving_environment(tmp_path):
    # Disposable launcher copy and fake preflight: no pip, network, or real
    # environment modification. A healthy interpreter alone is not sufficient.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    original = Path(__file__).resolve().parents[1] / "scripts" / "setup.ps1"
    copy = scripts / "setup.ps1"
    copy.write_text(original.read_text())
    (scripts / "environment.ps1").write_text("""
function Test-LensEnvironment { return $false }
function Test-LensPython { return $true }
function Find-LensPython { throw 'Compatible Python unavailable' }
function Backup-LensEnvironment { throw 'Unexpected backup before preflight' }
""")
    environment = tmp_path / ".venv"
    environment.mkdir()
    (environment / "keep.txt").write_text("preserve")
    result = powershell(f"& '{copy}' -ProjectRoot '{tmp_path}'")
    assert result.returncode != 0 and "Compatible Python unavailable" in result.stderr
    assert "Unexpected backup" not in result.stderr
    assert (environment / "keep.txt").read_text() == "preserve"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher")
@pytest.mark.parametrize("status", ["ready", "error", "early_exit", "timeout"])
def test_launcher_requires_startup_acknowledgement_and_reports_failures(tmp_path, status):
    import os
    run = Path(__file__).resolve().parents[1] / "scripts" / "run.ps1"
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "pythonw.exe").touch()  # mock Start-Process below; never executed
    status_write = ""
    if status in {"ready", "error"}:
        payload = json.dumps({"status": status, "message": "safe startup failure"})
        status_write = f"[IO.File]::WriteAllText($env:LANGUAGE_LENS_STARTUP_FILE, '{payload}');"
    exited = "$true" if status == "early_exit" else "$false"
    script = f"""function Start-Process {{
    {status_write}
    $Fake = [pscustomobject]@{{HasExited={exited}; ExitCode=17}}
    $Fake | Add-Member ScriptMethod Dispose {{}}
    $Fake | Add-Member ScriptMethod Kill {{ $this.HasExited = $true; Write-Output 'killed unready child' }}
    return $Fake
}}
& '{run}' -ProjectRoot '{tmp_path}' -StartupTimeoutSeconds 1
"""
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), LANGUAGE_LENS_STARTUP_FILE="previous")
    result = powershell(script, env=env)
    if status == "ready":
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        expected = "safe startup failure" if status == "error" else "code 17" if status == "early_exit" else "did not finish starting"
        assert expected in result.stderr
    assert not list((tmp_path / "LanguageLens").glob("startup-*.json"))
