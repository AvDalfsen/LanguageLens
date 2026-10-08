from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QLabel

from language_lens import __version__
from language_lens.ui.help import HelpDialog, documentation_root
from language_lens.ui.identity import app_icon


def test_help_is_available_offline_and_links_stay_in_documentation(qapp, tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "getting-started.md").write_text("# Start\n\n[Fix a problem](troubleshooting.md)", encoding="utf-8")
    (docs / "troubleshooting.md").write_text("# Troubleshooting\n\nTry checking local files.", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT licence", encoding="utf-8")
    opened = []
    monkeypatch.setattr("language_lens.ui.help.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    window = HelpDialog(root=tmp_path)
    assert "Start" in window.browser.toPlainText()
    assert any(__version__ in label.text() for label in window.findChildren(QLabel))
    window._open_link(QUrl("troubleshooting.md"))
    assert "Try checking local files." in window.browser.toPlainText() and not opened
    window._open_link(QUrl("../LICENSE"))
    assert window.browser.toPlainText() == "MIT licence"
    previous = window.browser.toPlainText()
    window._open_link(QUrl.fromLocalFile(str(tmp_path.parent / "outside.md")))
    assert window.browser.toPlainText() == previous and not opened
    window._open_link(QUrl("https://github.com/AvDalfsen/LanguageLens/issues"))
    assert opened == ["https://github.com/AvDalfsen/LanguageLens/issues"]
    window.topics.setCurrentIndex(2)
    assert "https://github.com/AvDalfsen/LanguageLens/blob/main/docs/languages.md" in window.browser.toHtml()
    window.close()


def test_source_guides_and_icon_are_present(qapp):
    root = documentation_root()
    assert (root / "docs" / "getting-started.md").is_file()
    assert not app_icon().isNull()
    assert not app_icon().pixmap(16, 16).isNull()
