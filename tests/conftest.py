import os
import sys
import ctypes
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Native faults still fail tests and produce faulthandler traces; they must not
# open a blocking OS error dialog on the user's desktop during automated runs.
if sys.platform == "win32":
    ctypes.windll.kernel32.SetErrorMode(3)

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
import pytest


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def review_factory(qapp, monkeypatch):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPixmap
    from language_lens.config import Settings
    from language_lens.ui import review
    tasks = []
    monkeypatch.setattr(review, "QThreadPool", SimpleNamespace(
        globalInstance=lambda: SimpleNamespace(start=tasks.append)))
    def create(*, size=(1000, 700), selection=None, settings=None):
        window = review.ReviewWindow(QPixmap(*size), selection or QRect(200, 100, 300, 40),
                                     settings or Settings(speech_enabled=False))
        window.show()
        return window, tasks
    return create


@pytest.fixture(autouse=True)
def dispose_test_widgets():
    app = QApplication.instance()
    before = set(app.topLevelWidgets()) if app else set()
    yield
    app = QApplication.instance()
    if app:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for widget in set(app.topLevelWidgets()) - before:
            # Stop native work before releasing Qt objects. Failed assertions
            # can retain Python frames long past the widget's intended lifetime.
            if hasattr(widget, "shutdown_speech"):
                widget.shutdown_speech()
            if hasattr(widget, "pronunciation"):
                widget.shutdown()
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
