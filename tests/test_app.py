from types import SimpleNamespace

from PySide6.QtCore import QObject, QRect, Signal
from PySide6.QtGui import QPixmap

from language_lens.config import Settings
import language_lens.app as app_module
from language_lens.app import LensController


class FakeReview(QObject):
    finished = Signal()

    def __init__(self, pixmap, selection, settings):
        super().__init__()
        self.was_shown = False

    def show(self):
        self.was_shown = True


def controller_stub(return_to_settings=True):
    controller = SimpleNamespace(
        _busy=True,
        _selector=object(),
        _review=None,
        _previous_window=None,
        _escape_sent=False,
        _return_to_settings=return_to_settings,
        settings=Settings(),
        setup=object(),
        settings_were_shown=False,
    )
    controller._session_finished = lambda: LensController._session_finished(controller)
    controller.show_settings = lambda: setattr(controller, "settings_were_shown", True)
    return controller


def test_review_close_resets_capture_for_a_second_try(monkeypatch, qapp):
    monkeypatch.setattr(app_module, "ReviewWindow", FakeReview)
    monkeypatch.setattr(app_module, "restore_foreground", lambda window: False)
    controller = controller_stub()
    pixmap = QPixmap(800, 600)
    selection = QRect(100, 120, 300, 80)

    LensController._selection_finished(controller, pixmap, selection)
    first_review = controller._review

    assert first_review.was_shown
    first_review.finished.emit()
    assert not controller._busy
    assert controller.settings_were_shown

    controller._busy = True
    LensController._selection_finished(controller, pixmap, selection)

    assert controller._review is not None
    assert controller._review is not first_review
    assert controller._review.was_shown


def test_game_capture_restores_the_previous_window(monkeypatch, qapp):
    restored = []
    monkeypatch.setattr(
        app_module, "restore_foreground", lambda window: restored.append(window) or True
    )
    controller = controller_stub(return_to_settings=False)
    controller._previous_window = 1234

    LensController._session_finished(controller)

    assert restored == [1234]
    assert not controller.settings_were_shown


def test_review_creation_failure_resets_capture(monkeypatch, qapp):
    def fail_to_create_review(*args):
        raise RuntimeError("test failure")

    errors = []
    monkeypatch.setattr(app_module, "ReviewWindow", fail_to_create_review)
    monkeypatch.setattr(app_module, "restore_foreground", lambda window: False)
    monkeypatch.setattr(
        app_module.QMessageBox,
        "critical",
        lambda parent, title, message: errors.append((title, message)),
    )
    controller = controller_stub()

    LensController._selection_finished(
        controller, QPixmap(800, 600), QRect(100, 120, 300, 80)
    )

    assert not controller._busy
    assert controller.settings_were_shown
    assert errors == [
        (
            "Could not open capture",
            "The captured image could not be opened for review.\n\ntest failure",
        )
    ]
