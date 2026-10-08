"""Render the product icon and illustrated workflow; never captures a desktop or downloads models."""
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from language_lens.app import STYLESHEET
from language_lens.config import Settings
from language_lens.domain import OcrLine, WordTranslation
from language_lens.ui.review import ReviewWindow
from language_lens.ui.setup import SetupWindow
from language_lens.ui.style import LensStyle

ROOT = Path(__file__).resolve().parents[1]


def image_copy(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes("RGBA", (image.width(), image.height()), bytes(image.bits()))


def main():
    app = QApplication([])
    app.setStyle(LensStyle(app.style().objectName()))
    app.setStyleSheet(STYLESHEET)
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)
    assets = ROOT / "docs" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    source = ROOT / "src" / "language_lens" / "assets" / "language-lens.svg"
    (assets / "language-lens.svg").write_bytes(source.read_bytes())
    mark = QImage(512, 512, QImage.Format.Format_RGBA8888)
    mark.fill(Qt.GlobalColor.transparent)
    painter = QPainter(mark)
    QSvgRenderer(str(source)).render(painter)
    painter.end()
    mark.save(str(assets / "language-lens.png"))
    icon = Image.frombytes("RGBA", (512, 512), bytes(mark.bits()))
    icon.save(source.with_suffix(".ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # The source content and translations are deliberately supplied demo fixtures.
    width, height = 1280, 760
    page = QPixmap(width, height)
    page.fill(QColor("#182638"))
    painter = QPainter(page)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#22384c"))
    painter.drawRoundedRect(52, 52, 1176, 656, 24, 24)
    painter.setPen(QColor("#5eead4"))
    painter.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
    painter.drawText(86, 100, "READING PRACTICE  /  PORTUGUESE")
    painter.setPen(QColor("#e8eef8"))
    painter.setFont(QFont("Segoe UI", 27, QFont.Weight.DemiBold))
    painter.drawText(86, 169, "A story in a few words")
    painter.setPen(QColor("#bacbda"))
    painter.setFont(QFont("Segoe UI", 14))
    painter.drawText(86, 215, "Explore unfamiliar text without leaving the sentence behind.")
    text = "Estas palavras contam uma história."
    font = QFont("Segoe UI")
    font.setPixelSize(30)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    metrics = QFontMetrics(font)
    text_width = metrics.horizontalAdvance(text)
    painter.drawText(88, 302, text)
    painter.setFont(QFont("Segoe UI", 11))
    painter.setPen(QColor("#bacbda"))
    painter.drawText(86, 663, "Language Lens  ·  Illustrated example")
    painter.end()
    frames = [image_copy(page)]
    selection = QRect(80, 268, text_width + 18, 45)
    selecting = page.copy()
    painter = QPainter(selecting)
    painter.fillRect(selecting.rect(), QColor(0, 0, 0, 55))
    painter.setPen(QColor("#5eead4"))
    painter.drawRect(selection)
    painter.end()
    frames.append(image_copy(selecting))
    translations = {
        "Estas": ("These",), "palavras": ("words",), "contam": ("tell",),
        "uma": ("a",), "história": ("story",),
    }
    pool = SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=lambda _task: None))
    with patch("language_lens.ui.review.QThreadPool", pool):
        window = ReviewWindow(page, selection, Settings(source_language="pt", target_language="en", speech_enabled=False))
        window._ocr_finished([OcrLine(text, .99, ((8, 1), (text_width + 8, 1), (text_width + 8, 39), (8, 39)))])
        window._translation_finished(("These words tell a story.", {word: WordTranslation(values) for word, values in translations.items()}))
        window.show()
        for _ in range(8):
            app.processEvents()
        frames.append(image_copy(window.grab()))
        for name in ("palavras", "história"):
            hit = next(hit for hit in window.canvas._hits if hit.lookup_text == name)
            window.canvas._hovered = hit
            window.canvas._pinned = True
            window.canvas._refresh_bubble()
            app.processEvents()
            frame = window.grab()
            frames.append(image_copy(frame))
            if name == "palavras":
                frame.save(str(assets / "review.png"))
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    frames[0].save(assets / "workflow.gif", save_all=True, append_images=frames[1:],
                   duration=[1000, 800, 1600, 2000, 2000], loop=0, disposal=2, optimize=True)
    with patch("language_lens.ui.setup.ServiceJob.start", lambda *_args, **_kwargs: None):
        window = SetupWindow(Settings(source_language="pt", target_language="en", speech_enabled=False))
        window._status_timer.stop()
        window._available_geometry = lambda: QRect(0, 0, 1440, 1200)
        window._apply_model_status({"ready": False, "prepared": False, "route": ["pt", "en"]})
        window.show()
        for _ in range(8):
            app.processEvents()
        window.grab().save(str(assets / "settings.png"))
        window.show_help()
        app.processEvents()
        window._help_dialog.grab().save(str(assets / "help.png"))
        window._help_dialog.close()
        window.shutdown()
        window.close()
    print(assets)


if __name__ == "__main__":
    main()
