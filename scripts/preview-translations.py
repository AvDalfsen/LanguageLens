"""Render all UI locales offscreen, using synthetic data and no downloads."""
from pathlib import Path
import os
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QEvent, QRect
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QPushButton
from language_lens.app import STYLESHEET
from language_lens.config import Settings
from language_lens.domain import OcrLine, WordTranslation
from language_lens.i18n import UI_LANGUAGES, set_language, tr
from language_lens.ui.setup import SetupWindow
from language_lens.ui.review import ReviewWindow
from language_lens.ui.help import HelpDialog


def main():
    app = QApplication.instance() or QApplication([])
    # The offscreen plugin does not discover Windows system fonts itself.
    font_root = Path("C:/Windows/Fonts")
    for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "tahoma.ttf",
                 "Nirmala.ttf", "msyh.ttc", "msgothic.ttc", "malgun.ttf"):
        file = font_root / font
        if file.is_file():
            assert QFontDatabase.addApplicationFont(str(file)) >= 0, file
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)
    root = Path(__file__).resolve().parents[1] / "artifacts/localization-audit/previews"
    root.mkdir(parents=True, exist_ok=True)
    clipped = []
    with patch("language_lens.ui.setup.ServiceJob.start", lambda *args: None), patch(
            "language_lens.ui.review.QThreadPool", SimpleNamespace(
                globalInstance=lambda: SimpleNamespace(start=lambda *args: None))):
        for name, code in UI_LANGUAGES:
            window = SetupWindow(Settings(ui_language=code, source_language="ja", target_language="nl"))
            window._status_timer.stop()
            window._apply_model_status({"ready": True, "prepared": True, "route": ["ja", "en", "nl"]})
            for width, height in ((960, 1000), (640, 480)):
                window._available_geometry = lambda: QRect(0, 0, width, height)
                window.show()
                window.resize(width, height)
                for _ in range(8): app.processEvents()
                assert window.grab().save(str(root / f"settings-{code}-{width}.png"))
                for button in window.findChildren(QPushButton):
                    if button.isVisible() and button.fontMetrics().horizontalAdvance(button.text()) > button.width() - 12:
                        clipped.append((code, width, button.text(), button.width()))
            help_dialog = HelpDialog(window)
            help_dialog.show()
            app.processEvents()
            assert help_dialog.grab().save(str(root / f"help-{code}.png"))
            help_dialog.close()
            image = QPixmap(1000, 700)
            image.fill(QColor("#252a2e"))
            painter = QPainter(image)
            painter.setPen(QColor("white"))
            painter.drawText(150, 130, "Read and learn a language")
            painter.end()
            review = ReviewWindow(image, QRect(145, 110, 400, 30), Settings(speech_enabled=False))
            review._ocr_finished([OcrLine("Read and learn a language", .99,
                ((0, 0), (400, 0), (400, 30), (0, 30)))])
            review._translation_finished(("Lees en leer een taal.", {"Read": WordTranslation(("Lees", "gelezen"))}))
            review.show()
            for _ in range(8): app.processEvents()
            review.canvas._hovered = review.canvas._hits[0]
            review.canvas._pinned = True
            review.canvas._refresh_bubble()
            app.processEvents()
            assert review.grab().save(str(root / f"review-{code}.png"))
            review.shutdown_speech()
            review.close()
            window.shutdown()
            window.close()
            for widget in (help_dialog, review, window): widget.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    set_language("en")
    sheet = QPixmap(5 * 320, 5 * 370)
    sheet.fill(QColor("#111827"))
    painter = QPainter(sheet)
    painter.setPen(QColor("white"))
    for index, (name, code) in enumerate(UI_LANGUAGES):
        x, y = (index % 5) * 320, (index // 5) * 370
        painter.drawText(x + 8, y + 20, f"{code} — {name}")
        shot = QPixmap(str(root / f"settings-{code}-960.png"))
        painter.drawPixmap(x, y + 25, shot.scaled(320, 340))
    painter.end()
    assert sheet.save(str(root / "contact-sheet.png"))
    print(f"Rendered {len(UI_LANGUAGES)} locales: 50 settings views, 25 help dialogs, 25 review overlays.")
    print("Potential clipped buttons:", clipped)
    print(root.resolve())


if __name__ == "__main__": main()
