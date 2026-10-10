"""Offline user guides and version information, available from Settings and tray."""
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices, QImage, QTextCursor, QTextOption
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QPushButton, QTextBrowser, QVBoxLayout,
)

from language_lens import __version__
from language_lens.i18n import tr, translate_ui
from language_lens.services.diagnostics import open_folder
from language_lens.ui.identity import app_icon

REPOSITORY = "https://github.com/AvDalfsen/LanguageLens"
TOPICS = (
    ("Getting started", "getting-started.md"),
    ("User guide", "user-guide.md"),
    ("Supported languages", "languages.md"),
    ("Pronunciation", "pronunciation.md"),
    ("Troubleshooting", "troubleshooting.md"),
    ("Privacy and local files", "privacy.md"),
)


def documentation_root() -> Path:
    package = Path(__file__).resolve().parents[1]
    bundled = package / "help"
    return bundled if (bundled / "docs").is_dir() else package.parents[1]


class HelpDialog(QDialog):
    def __init__(self, parent=None, *, root: Path | None = None):
        super().__init__(parent)
        self.root = (root or documentation_root()).resolve()
        self.setWindowTitle(tr("Help and about — Language Lens"))
        self.setWindowIcon(app_icon())
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(800, 680)
        self.setMinimumSize(400, 320)
        if parent and parent.screen():
            available = parent.screen().availableGeometry()
            self.resize(min(800, available.width()), min(680, available.height()))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        heading = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(40, 40))
        heading.addWidget(mark)
        title = QLabel(f"Language Lens {__version__}")
        title.setObjectName("title")
        heading.addWidget(title)
        heading.addStretch()
        layout.addLayout(heading)
        self.topics = QComboBox()
        self.topics.setAccessibleName(tr("Help topic"))
        for title, name in TOPICS:
            self.topics.addItem(tr(title), name)
        layout.addWidget(self.topics)
        self.browser = QTextBrowser()
        self.browser.setAccessibleName(tr("User guide"))
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        option = self.browser.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.browser.document().setDefaultTextOption(option)
        self.browser.setStyleSheet("QTextBrowser { background: #111e32; border: 1px solid #31435f; padding: 12px; }")
        self.browser.document().setDefaultStyleSheet("a { color: #5eead4; }")
        self.browser.anchorClicked.connect(self._open_link)
        layout.addWidget(self.browser, 1)
        row = QHBoxLayout()
        diagnostics = QPushButton(tr("Open diagnostics folder"))
        diagnostics.clicked.connect(open_folder)
        row.addWidget(diagnostics)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        layout.addLayout(row)
        self.topics.currentIndexChanged.connect(self._topic_changed)
        self._topic_changed()
        translate_ui(self)

    def _topic_changed(self, *_args):
        self._load(self.root / "docs" / self.topics.currentData())

    def _load(self, path: Path):
        path = path.resolve()
        if not path.is_relative_to(self.root):
            return
        self._page = path
        self.browser.document().setBaseUrl(QUrl.fromLocalFile(str(path)))
        try:
            content = path.read_text(encoding="utf-8-sig")
        except OSError:
            self.browser.setHtml(
                f'<p>The guide is available <a href="{REPOSITORY}/blob/main/{path.relative_to(self.root).as_posix()}">online</a>.</p>'
                "<p>Capture, translation, and speech run locally after setup.</p>"
            )
        else:
            if path.suffix.lower() == ".md":
                self.browser.setMarkdown(content)
            else:
                self.browser.setPlainText(content)
        self._format_document()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "browser"):
            self._format_document()

    def _format_document(self):
        document = self.browser.document()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid():
                    original = fragment.charFormat()
                    cursor = QTextCursor(document)
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.MoveMode.KeepAnchor)
                    if original.isImageFormat():
                        image_format = original.toImageFormat()
                        url = document.baseUrl().resolved(QUrl(image_format.name()))
                        if url.isLocalFile():
                            image_path = Path(url.toLocalFile()).resolve()
                            if image_path.is_relative_to(self.root):
                                image = QImage(str(image_path))
                                if not image.isNull():
                                    width = min(image.width(), max(160, self.browser.viewport().width() - 40))
                                    image_format.setWidth(width)
                                    image_format.setHeight(width * image.height() / image.width())
                                    cursor.setCharFormat(image_format)
                    elif original.isAnchor():
                        original.setForeground(QColor("#5eead4"))
                        cursor.setCharFormat(original)
                iterator += 1
            block = block.next()

    def _open_link(self, url: QUrl):
        resolved = self.browser.document().baseUrl().resolved(url)
        if resolved.isLocalFile():
            path = Path(resolved.toLocalFile()).resolve()
            if path.is_relative_to(self.root) and (path.suffix.lower() == ".md" or path.name == "LICENSE"):
                self._load(path)
                if resolved.fragment():
                    self.browser.scrollToAnchor(resolved.fragment())
                return
            if path.is_relative_to(self.root) and path.is_file():
                QDesktopServices.openUrl(resolved)
        elif resolved.scheme() in {"https", "http"}:
            QDesktopServices.openUrl(resolved)
