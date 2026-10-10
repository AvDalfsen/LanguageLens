"""Offscreen UI render for developer review; never captures the user's desktop."""
from pathlib import Path
import os
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu
from language_lens.app import STYLESHEET
from language_lens.config import Settings
from language_lens.domain import OcrLine, WordTranslation
from language_lens.ui.setup import SetupWindow
from language_lens.ui.style import LensStyle
from language_lens.ui.review import ReviewWindow


def main():
    app = QApplication([])
    app.setStyle(LensStyle(app.style().objectName()))
    app.setStyleSheet(STYLESHEET)
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
    root = Path(__file__).resolve().parents[1] / "artifacts" / "ui-review"
    root.mkdir(parents=True, exist_ok=True)
    for ready in (False, True):
        menu = QMenu()
        menu.addAction("Capture now").setEnabled(ready)
        settings_action = menu.addAction("Settings")
        menu.addAction("Start listening").setEnabled(ready)
        menu.addSeparator()
        menu.addAction("Quit")
        menu.show()
        menu.setActiveAction(settings_action)
        app.processEvents()
        assert menu.grab().save(str(root / f"tray-{'ready' if ready else 'unverified'}.png"))
        menu.close()
        menu.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    for width, height in ((1920, 1080), (640, 480)):
        window = SetupWindow(Settings(source_language="ja", target_language="en"))
        window._status_timer.stop()
        window._apply_model_status({"ready": True, "prepared": True, "route": ["ja", "en"]})
        window._available_geometry = lambda width=width, height=height: QRect(0, 0, width, height)
        window.show()
        for _ in range(8):
            app.processEvents()
        assert window.grab().save(str(root / f"settings-{width}.png"))
        window.maintenance.toggle.click()
        window.technical_details.toggle.click()
        for _ in range(8):
            app.processEvents()
        assert window.grab().save(str(root / f"settings-details-{width}.png"))
        window.maintenance.toggle.click()
        window.technical_details.toggle.click()
        window.set_listening("<f8>")
        for _ in range(8):
            app.processEvents()
        assert window.grab().save(str(root / f"settings-listening-{width}.png"))
        window.set_listening(None)
        window.source.setCurrentIndex(window.source.findData("nl"))
        window.target.setCurrentIndex(window.target.findData("fr"))
        window._status_timer.stop()
        window._apply_model_status({"ready": False, "prepared": False, "route": []})
        for _ in range(8):
            app.processEvents()
        assert window.grab().save(str(root / f"settings-missing-{width}.png"))
        window.shutdown()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    for width, height in ((1280, 720), (640, 480), (640, 360), (320, 480)):
        image = QPixmap(width, height)
        image.fill(QColor("#252a2e"))
        painter = QPainter(image)
        painter.setPen(QColor("white"))
        font = QFont("Segoe UI")
        font.setPixelSize(28)
        painter.setFont(font)
        text = "Read and learn a language"
        painter.drawText(40, 95, text)
        painter.end()
        with patch("language_lens.ui.review.TaskPool", SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=lambda task: None))):
            window = ReviewWindow(image, QRect(35, 65, min(560, width - 70), 45), Settings(source_language="en", target_language="nl", speech_enabled=False))
            window._ocr_finished([OcrLine(text, .99, ((5, 0), (480, 0), (480, 35), (5, 35)))])
            window._translation_finished(("Lees en leer een taal. " * 80, {"Read": WordTranslation(("Lees", "gelezen"))}))
            window.show()
            for _ in range(8):
                app.processEvents()
            window.canvas._hovered = window.canvas._hits[0]
            window.canvas._pinned = True
            window.canvas._refresh_bubble()
            assert window.grab().save(str(root / f"review-{width}-{height}.png"))
            window.canvas.dismiss_word()
            window.recognized_section.toggle.click()
            for _ in range(8):
                app.processEvents()
            assert window.grab().save(str(root / f"review-expanded-{width}-{height}.png"))
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    print(root)


if __name__ == "__main__":
    main()
