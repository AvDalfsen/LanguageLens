from __future__ import annotations

import ctypes
from copy import deepcopy
import os
import sys

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from language_lens.config import Settings, load_settings, save_settings
from language_lens.services.capture import capture_desktop
from language_lens.services.hotkey import WindowsHotkeyListener
from language_lens.services.windows import foreground_window, restore_foreground
from language_lens.ui.review import ReviewWindow
from language_lens.ui.selection import SelectionOverlay
from language_lens.ui.setup import SetupWindow
from language_lens.ui.style import LensStyle
from language_lens.ui.identity import app_icon
from language_lens.services.diagnostics import initialize, record_failure
from language_lens.services.instance import SingleInstance
from language_lens.services.offline import offline_ready
from language_lens.services.startup import report_startup
from language_lens.runtime import recovery_instruction


def persist(settings, parent=None, *, notify=True) -> bool:
    try:
        save_settings(settings)
        return True
    except (OSError, ValueError) as exc:
        record_failure("settings-save", exc)
        if notify:
            QMessageBox.warning(parent, "Settings not saved", "Lens can continue, but your settings could not be saved. Check disk space and directory permissions.")
        return False


STYLESHEET = """
QWidget {
    background: #0b1424;
    color: #e8eef8;
    font-family: "Segoe UI";
    font-size: 14px;
}
QLabel#title { font-size: 30px; font-weight: 700; color: #f8fafc; }
QLabel#intro { font-size: 15px; color: #a9b8ce; }
QLabel#note { color: #8292aa; font-size: 12px; }
QFrame#card, QFrame#footer {
    background: #111e32;
    border: 1px solid #21314a;
    border-radius: 12px;
}
QFrame#footer { border-radius: 0; border-left: 0; border-right: 0; border-bottom: 0; }
QFrame#card QLabel, QFrame#card QCheckBox {
    padding: 6px 10px;
    border-radius: 7px;
}
QComboBox, QKeySequenceEdit QLineEdit {
    background: #0b1424;
    border: 1px solid #31435f;
    border-radius: 7px;
    padding: 8px 12px;
}
QComboBox { min-width: 250px; }
QKeySequenceEdit QLineEdit { min-width: 140px; }
QComboBox:disabled, QKeySequenceEdit QLineEdit:disabled { color: #6f7b8d; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox QAbstractItemView { background: #111e32; selection-background-color: #167b79; }
QMenu { background: #0b1424; border: 1px solid #31435f; padding: 4px; }
QMenu::item { background: transparent; color: #e8eef8; padding: 8px 28px; margin: 2px 4px; border-radius: 4px; }
QMenu::item:selected:enabled { background: #174b50; color: #ffffff; }
QMenu::item:disabled { color: #6f7b8d; background: transparent; }
QMenu::item:selected:disabled { color: #6f7b8d; background: transparent; }
QMenu::separator { height: 1px; background: #31435f; margin: 5px 8px; }
QProgressBar {
    background: #111e32;
    border: 1px solid #2c405c;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
}
QProgressBar::chunk { background: #29c7b9; border-radius: 3px; }
QCheckBox { spacing: 9px; }
QToolButton {
    color: #e8eef8; background: transparent; border: 1px solid transparent;
    border-radius: 4px; padding: 5px;
}
QToolButton:hover { background: #21314a; }
QToolButton:disabled { color: #6f7b8d; }
QPushButton {
    background: #21314a;
    border: 1px solid #344965;
    border-radius: 7px;
    padding: 9px 15px;
}
QPushButton:hover { background: #2a3d59; }
QPushButton#secondaryButton { background: #111e32; color: #b8c6da; border-color: #233651; }
QPushButton#secondaryButton:hover { background: #21314a; color: #e8eef8; }
QPushButton:disabled { color: #6f7b8d; background: #152136; }
QPushButton#primaryButton {
    background: #0f9f94;
    border-color: #29c7b9;
    color: #ffffff;
    font-weight: 650;
    padding: 11px 22px;
}
QPushButton#primaryButton:hover { background: #13b3a7; }
QPushButton#primaryButton:disabled { color: #6f7b8d; background: #152136; border-color: #314865; }
QPushButton:focus:enabled, QToolButton:focus:enabled, QComboBox:focus:enabled,
QKeySequenceEdit:focus:enabled, QCheckBox:focus:enabled, QLabel:focus {
    border: 2px solid #5eead4;
}
QSlider::handle:horizontal:focus { border: 2px solid #ffffff; }
QLabel#sentenceTranslation:focus, QFrame#wordPopup QLabel:focus { border: 2px solid #5eead4; }
QSlider::groove:horizontal { height: 6px; background: #314865; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #20c4b7; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; margin: -5px 0; background: #5eead4; border-radius: 8px; }
QSlider::handle:horizontal:disabled, QSlider::sub-page:horizontal:disabled { background: #6f7b8d; }
QLabel#modelReady { color: #63e6be; }
QLabel#modelMissing { color: #f7c96b; }
QLabel#statusLabel { color: #b8c6da; }
QLabel#sentenceTranslation {
    background: #0b1424;
    border: 1px solid #2c405c;
    border-radius: 7px;
    padding: 10px;
}
QLabel#translationBubble {
    background: #07111f;
    color: white;
    border: 1px solid #5eead4;
    border-radius: 6px;
    padding: 7px 10px;
}
"""


def enable_per_monitor_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass


class LensController(QObject):
    global_capture = Signal()

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.settings = load_settings()
        self.setup = SetupWindow(self.settings)
        self.setup.listen_requested.connect(self.start_listening)
        self.setup.capture_requested.connect(lambda: self.begin_capture(from_external_app=False))
        self.setup.window_preferences_changed.connect(self._save_window_preferences)
        self.setup.hotkey_changed.connect(self._save_hotkey)
        self.setup.pause_requested.connect(self.pause_listening)
        self.app.aboutToQuit.connect(self._shutdown)
        self.global_capture.connect(lambda: self.begin_capture(from_external_app=True))
        self._listener = None
        self._desired_hotkey: str | None = None
        self._syncing_listener = False
        self._capture_settings: Settings | None = None
        self._selector: SelectionOverlay | None = None
        self._review: ReviewWindow | None = None
        self._previous_window: int | None = None
        self._busy = False
        self._return_to_settings = False
        self._shutting_down = False
        self._session_id = 0
        self._capture_position = None
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.timeout.connect(self._take_screenshot)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._save_preferences)
        self.setup.preferences_changed.connect(self._queue_preferences)
        self.setup.closed_to_tray.connect(self._closed_to_tray)
        self.setup.visibility_changed.connect(self._settings_visibility_changed)

        icon = app_icon()
        self.app.setWindowIcon(icon)
        self.setup.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Language Lens")
        menu = QMenu()
        capture_action = QAction("Capture now", menu)
        capture_action.setEnabled(False)
        self._capture_action = capture_action
        capture_action.triggered.connect(lambda: self.begin_capture(from_external_app=True))
        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self.show_settings)
        self._listening_action = QAction("Start listening", menu)
        self._listening_action.triggered.connect(self._toggle_tray_listening)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(capture_action)
        menu.addAction(settings_action)
        menu.addAction(self._listening_action)
        help_action = QAction("Help and about", menu)
        help_action.triggered.connect(self.show_help)
        menu.addAction(help_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        menu.aboutToShow.connect(self._refresh_tray_listening)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self.setup.readiness_changed.connect(self._readiness_changed)
        self.setup.availability_changed.connect(self._sync_listener)
        self._refresh_tray_listening()

    def show(self) -> None:
        self.setup.show()
        self.setup.activateWindow()

    def show_settings(self) -> None:
        self.setup.show()
        self.setup.raise_()
        self.setup.activateWindow()

    def show_help(self) -> None:
        self.show_settings()
        self.setup.show_help()

    def _save_window_preferences(self) -> None:
        current = self.setup.current_settings()
        # Resize persistence must not silently apply other unsaved UI choices.
        self.settings.settings_window_size = current.settings_window_size
        self.settings.settings_window_maximized = current.settings_window_maximized
        persist(self.settings, self.setup, notify=False)

    def _queue_preferences(self) -> None:
        if not self._shutting_down:
            self._save_timer.start()

    def _save_preferences(self, *, notify=True) -> None:
        self._save_timer.stop()
        current = self.setup.current_settings()
        if current != self.settings:
            if persist(current, self.setup, notify=notify):
                self.settings = deepcopy(current)

    def _settings_visibility_changed(self) -> None:
        if not self.setup.isVisible():
            self._save_preferences()
        self._sync_listener()

    def _closed_to_tray(self) -> None:
        if not self._shutting_down:
            self.tray.showMessage("Language Lens is still running",
                "Closing 'Settings' leaves Lens in the tray. Reopen 'Settings' there, or choose 'Quit' to close Lens.",
                QSystemTrayIcon.MessageIcon.Information, 5000)

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_settings()

    def start_listening(self, settings: Settings) -> None:
        if not self.setup.hotkey_valid:
            self.show_settings()
            return
        if not self._capture_allowed(settings):
            return
        if not self.setup.availability.listening_enabled:
            return
        self.settings = settings
        persist(settings, self.setup)
        try:
            if self._listener is not None:
                self._listener.stop()
            self._listener = WindowsHotkeyListener(settings.hotkey, self.global_capture.emit)
            self._listener.start()
        except Exception as exc:
            if self._listener is not None:
                self._listener.stop()
            self._listener = None
            self._desired_hotkey = None
            self.setup.set_listening(None)
            self._refresh_tray_listening()
            QMessageBox.critical(self.setup, "Hotkey error", str(exc))
            return
        self._desired_hotkey = settings.hotkey
        self.setup.set_listening(settings.hotkey)
        self._refresh_tray_listening()
        self.setup.hide()
        self.tray.showMessage(
            "Language Lens is ready",
            "Press the configured hotkey anywhere, then drag around some text.",
            QSystemTrayIcon.MessageIcon.Information,
            3500,
        )

    def pause_listening(self) -> None:
        self._desired_hotkey = None
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self.setup.set_listening(None)
        self._refresh_tray_listening()

    def _refresh_tray_listening(self) -> None:
        listening = self._desired_hotkey is not None
        state = self.setup.availability
        self._capture_action.setEnabled(state.capture_enabled and not self._busy and not self._shutting_down)
        self._capture_action.setToolTip(state.reason or "Take a screenshot using the selected capture area.")
        self._listening_action.setText("Pause listening" if listening else "Start listening")
        self._listening_action.setEnabled(listening or (
            state.listening_enabled and not self._busy and not self._shutting_down))
        detail = "shortcut temporarily suspended" if listening and self._listener is None else "listening" if listening else "hotkey inactive"
        self.tray.setToolTip(f"Language Lens · {detail}")

    def _sync_listener(self) -> None:
        if self._syncing_listener:
            return
        self._syncing_listener = True
        try:
            state = self.setup.availability
            if not state.verified:
                self._desired_hotkey = None
            register = (self._desired_hotkey is not None and state.listening_enabled
                        and not self._busy and not self._shutting_down and not self.setup.isVisible())
            if self._listener is not None and not register:
                self._listener.stop()
                self._listener = None
            if self._listener is None and register:
                listener = None
                try:
                    listener = WindowsHotkeyListener(self._desired_hotkey, self.global_capture.emit)
                    listener.start()
                except Exception as exc:
                    if listener is not None:
                        listener.stop()
                    self._desired_hotkey = None
                    record_failure("hotkey-restore", exc)
                    self.show_settings()
                    QMessageBox.warning(self.setup, "Capture hotkey could not resume",
                        "Another application may now be using the shortcut. Choose a different 'Capture hotkey', "
                        "or click 'Start listening' to retry. 'Try a capture now' remains available.")
                else:
                    self._listener = listener
            self.setup.set_listening(self._desired_hotkey,
                                     suspended=self._desired_hotkey is not None and self._listener is None)
            self._refresh_tray_listening()
        finally:
            self._syncing_listener = False

    def _toggle_tray_listening(self) -> None:
        if self._desired_hotkey is not None:
            self.pause_listening()
        elif not self._busy and not self._shutting_down:
            self.start_listening(self.setup.current_settings())

    def begin_capture(self, from_external_app: bool) -> None:
        if self._busy or self._shutting_down:
            return
        if self.setup.availability.voice_busy or self.setup.availability.model_busy:
            return
        if not self._capture_allowed(self.setup.current_settings()):
            return
        self.settings = self.setup.current_settings()
        self._capture_settings = deepcopy(self.settings)
        persist(self.settings, self.setup)
        self.setup.pronunciation.player.stop()
        self._busy = True
        if hasattr(self.setup, "set_capture_busy"):
            self.setup.set_capture_busy(True)
        self._sync_listener()
        self._session_id += 1
        self._return_to_settings = not from_external_app
        try:
            self._previous_window = foreground_window()
            self._capture_position = QCursor.pos()
            if not from_external_app:
                self.setup.hide()
                self._capture_timer.start(180)
            else:
                self._take_screenshot()
        except Exception as exc:
            self._session_finished()
            QMessageBox.critical(self.setup, "Capture failed", str(exc))

    def _take_screenshot(self) -> None:
        if not self._busy or self._shutting_down or self._selector or self._review:
            return
        settings = self._capture_settings or self.settings
        if not self._capture_allowed(settings):
            self._session_finished(return_focus=False)
            return
        session_id = self._session_id
        try:
            capture = capture_desktop(settings.capture_scope, self._capture_position)
            self._selector = SelectionOverlay(capture)
            self._selector.selected.connect(
                lambda capture, selection: self._selection_finished(capture, selection, session_id)
            )
            self._selector.cancelled.connect(
                lambda: self._session_finished(session_id=session_id)
            )
            self._selector.show()
        except Exception as exc:
            self._session_finished(session_id=session_id)
            self.show_settings()
            QMessageBox.critical(self.setup, "Capture failed", str(exc))

    def _selection_finished(self, capture, selection, session_id: int | None = None) -> None:
        if not self._busy or self._shutting_down or self._review is not None:
            return
        if session_id is not None and session_id != self._session_id:
            return
        session_id = self._session_id
        self._selector = None
        try:
            review = ReviewWindow(capture, selection, self._capture_settings or self.settings)
            self._review = review
            review.finished.connect(lambda: self._session_finished(session_id=session_id))
            review.speech_speed_changed.connect(self._save_speech_speed)
            if hasattr(review, "reselect_requested"):
                review.reselect_requested.connect(lambda capture: self._reselect(capture, session_id))
            review.show()
        except Exception as exc:
            self._session_finished()
            QMessageBox.critical(
                self.setup,
                "Could not open capture",
                f"The captured image could not be opened for review.\n\n{exc}",
            )
            return

    def _reselect(self, capture, session_id: int) -> None:
        if not self._busy or self._shutting_down or session_id != self._session_id:
            return
        review, self._review = self._review, None
        if review is not None:
            review.finished.disconnect()
            review.close()
            review.deleteLater()
        try:
            self._selector = SelectionOverlay(capture)
            self._selector.selected.connect(lambda capture, selection: self._selection_finished(capture, selection, session_id))
            self._selector.cancelled.connect(lambda: self._session_finished(session_id=session_id))
            self._selector.show()
        except Exception as exc:
            record_failure("reselect", exc)
            self._session_finished(session_id=session_id)
            self.show_settings()

    def _session_finished(
        self, *, session_id: int | None = None, return_focus: bool = True
    ) -> None:
        if session_id is not None and session_id != self._session_id:
            return
        if not self._busy:
            return
        # Clear state before closing widgets: their close signals can re-enter here.
        self._busy = False
        self._capture_timer.stop()
        selector, review = self._selector, self._review
        previous_window = self._previous_window
        return_to_settings = self._return_to_settings
        self._selector = None
        self._review = None
        self._previous_window = None
        self._capture_position = None
        self._return_to_settings = False
        self._capture_settings = None
        try:
            for window in (selector, review):
                if window is not None:
                    try:
                        window.close()
                        window.deleteLater()
                    except RuntimeError:
                        # A Qt wrapper can outlive its already-deleted native widget.
                        pass
        finally:
            if return_focus and not self._shutting_down:
                if return_to_settings:
                    self.show_settings()
                else:
                    restore_foreground(previous_window)
            if hasattr(self.setup, "set_capture_busy"):
                self.setup.set_capture_busy(False)
            self._sync_listener()

    def _shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._save_preferences(notify=False)
        self._desired_hotkey = None
        self._capture_timer.stop()
        self._session_finished(return_focus=False)
        if hasattr(self.setup, "shutdown"):
            self.setup.shutdown()
        else:
            self.setup.pronunciation.shutdown()
        if self._listener is not None:
            self._listener.stop()
        self.tray.hide()

    def _readiness_changed(self, ready: bool) -> None:
        if not ready:
            self.pause_listening()
        else:
            self._sync_listener()

    def _capture_allowed(self, settings: Settings) -> bool:
        # Recheck the cheap readiness marker at entry: files can be removed or
        # changed outside Lens after the background capability check completed.
        current = self.setup.current_settings()
        if (self.setup.capture_ready
                and (settings.source_language, settings.target_language)
                    == (current.source_language, current.target_language)
                and offline_ready(settings.source_language, settings.target_language)):
            return True
        self.pause_listening()
        self.setup.refresh_model_status()
        self.show_settings()
        return False

    def _save_speech_speed(self, speed: float) -> None:
        self.setup.pronunciation.set_speech_speed(speed)
        self._save_preferences(notify=False)

    def _save_hotkey(self, hotkey: str) -> None:
        self.settings.hotkey = hotkey
        persist(self.settings, self.setup)
        self._refresh_tray_listening()

    def quit(self) -> None:
        persist(self.setup.current_settings(), self.setup)
        self._shutdown()
        self.app.quit()


def main() -> int:
    if sys.platform != "win32":
        print("Language Lens currently supports Windows 10 and 11.", file=sys.stderr)
        return 2
    enable_per_monitor_dpi_awareness()
    app = QApplication(sys.argv)
    app.setApplicationName("Language Lens")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle(LensStyle(app.style().objectName()))
    app.setStyleSheet(STYLESHEET)
    initialize()
    instance = None
    try:
        instance = SingleInstance(app)
        app.aboutToQuit.connect(instance.close)
        if not instance.claim():
            if instance.notified:
                report_startup("ready")
                return 0
            report_startup("error", "Lens is already running but could not reopen 'Settings'. Use the existing tray icon, or close that instance and retry.")
            return 1
        controller = LensController(app)
    except Exception as exc:
        if instance is not None:
            instance.close()
        record_failure("startup", exc)
        message = "Startup failed. Diagnostic files are in '%LOCALAPPDATA%/LanguageLens/logs'. " + recovery_instruction()
        report_startup("error", message)
        if not os.environ.get("LANGUAGE_LENS_STARTUP_FILE"):
            QMessageBox.critical(None, "Language Lens could not start", message)
        return 1
    instance.reopen.connect(controller.show_settings)
    controller.show()
    QTimer.singleShot(0, lambda: report_startup("ready"))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

