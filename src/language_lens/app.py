from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from language_lens.config import Settings, load_settings, save_settings
from language_lens.services.capture import capture_desktop
from language_lens.services.hotkey import WindowsHotkeyListener
from language_lens.services.windows import foreground_window, press_escape, restore_foreground
from language_lens.ui.review import ReviewWindow
from language_lens.ui.selection import SelectionOverlay
from language_lens.ui.setup import SetupWindow


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
QComboBox {
    background: #0b1424;
    border: 1px solid #31435f;
    border-radius: 7px;
    padding: 8px 12px;
    min-width: 250px;
}
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox QAbstractItemView { background: #111e32; selection-background-color: #167b79; }
QProgressBar {
    background: #111e32;
    border: 1px solid #2c405c;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
}
QProgressBar::chunk { background: #29c7b9; border-radius: 3px; }
QCheckBox { spacing: 9px; }
QPushButton {
    background: #21314a;
    border: 1px solid #344965;
    border-radius: 7px;
    padding: 9px 15px;
}
QPushButton:hover { background: #2a3d59; }
QPushButton:disabled { color: #6f7b8d; background: #152136; }
QPushButton#primaryButton {
    background: #0f9f94;
    border-color: #29c7b9;
    color: #ffffff;
    font-weight: 650;
    padding: 11px 22px;
}
QPushButton#primaryButton:hover { background: #13b3a7; }
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
        self.app.aboutToQuit.connect(self._shutdown_speech)
        self.global_capture.connect(lambda: self.begin_capture(from_external_app=True))
        self._listener = None
        self._selector: SelectionOverlay | None = None
        self._review: ReviewWindow | None = None
        self._previous_window: int | None = None
        self._busy = False
        self._escape_sent = False
        self._return_to_settings = False

        icon = self.setup.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setup.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Language Lens")
        menu = QMenu()
        capture_action = QAction("Capture now", menu)
        capture_action.triggered.connect(lambda: self.begin_capture(from_external_app=True))
        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self.show_settings)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(capture_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def show(self) -> None:
        self.setup.show()
        self.setup.activateWindow()

    def show_settings(self) -> None:
        self.setup.show()
        self.setup.raise_()
        self.setup.activateWindow()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_settings()

    def start_listening(self, settings: Settings) -> None:
        self.settings = settings
        save_settings(settings)
        try:
            if self._listener is not None:
                self._listener.stop()
            self._listener = WindowsHotkeyListener(settings.hotkey, self.global_capture.emit)
            self._listener.start()
        except Exception as exc:
            QMessageBox.critical(self.setup, "Hotkey error", str(exc))
            return
        self.setup.hide()
        self.tray.showMessage(
            "Language Lens is ready",
            "Press the configured hotkey anywhere, then drag around some text.",
            QSystemTrayIcon.MessageIcon.Information,
            3500,
        )

    def begin_capture(self, from_external_app: bool) -> None:
        if self._busy:
            return
        self.settings = self.setup.current_settings()
        save_settings(self.settings)
        self.setup.pronunciation.player.stop()
        self._busy = True
        self._return_to_settings = not from_external_app
        self._previous_window = foreground_window()
        self._escape_sent = bool(from_external_app and self.settings.send_escape)
        if not from_external_app:
            self.setup.hide()
            QTimer.singleShot(180, self._take_screenshot)
        else:
            self._take_screenshot()

    def _take_screenshot(self) -> None:
        try:
            # The frame is frozen before Escape so a pause menu cannot cover the text.
            capture = capture_desktop()
        except Exception as exc:
            self._busy = False
            self.show_settings()
            QMessageBox.critical(self.setup, "Capture failed", str(exc))
            return

        if self._escape_sent:
            press_escape()
        self._selector = SelectionOverlay(capture)
        self._selector.selected.connect(self._selection_finished)
        self._selector.cancelled.connect(self._session_finished)
        self._selector.show()

    def _selection_finished(self, pixmap, selection) -> None:
        self._selector = None
        try:
            review = ReviewWindow(pixmap, selection, self.settings)
        except Exception as exc:
            self._session_finished()
            QMessageBox.critical(
                self.setup,
                "Could not open capture",
                f"The captured image could not be opened for review.\n\n{exc}",
            )
            return
        self._review = review
        review.finished.connect(self._session_finished)
        review.show()

    def _session_finished(self) -> None:
        if not self._busy:
            return
        self._busy = False
        self._selector = None
        self._review = None
        if self._return_to_settings:
            self.show_settings()
            restored = False
        else:
            restored = restore_foreground(self._previous_window)
        if self._escape_sent and restored:
            QTimer.singleShot(180, press_escape)
        self._escape_sent = False
        self._return_to_settings = False

    def _shutdown_speech(self) -> None:
        self.setup.pronunciation.shutdown()
        if self._review is not None:
            self._review.shutdown_speech()

    def quit(self) -> None:
        save_settings(self.setup.current_settings())
        self._shutdown_speech()
        if self._listener is not None:
            self._listener.stop()
        self.tray.hide()
        self.app.quit()


def main() -> int:
    if sys.platform != "win32":
        print("Language Lens currently supports Windows 10 and 11.", file=sys.stderr)
        return 2
    enable_per_monitor_dpi_awareness()
    app = QApplication(sys.argv)
    app.setApplicationName("Language Lens")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLESHEET)
    controller = LensController(app)
    controller.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

