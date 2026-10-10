from types import MethodType, SimpleNamespace
from copy import deepcopy

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtTest import QTest
import pytest

from language_lens.config import Settings
from language_lens.services.capture import DesktopCapture
import language_lens.app as app_module
from language_lens.app import LensController
from language_lens.services.availability import Availability


class FakeReview(QObject):
    finished = Signal()
    speech_speed_changed = Signal(float)

    def __init__(self, pixmap, selection, settings):
        super().__init__()
        self.was_shown = False
        self.close_count = 0

    def show(self):
        self.was_shown = True

    def close(self):
        self.close_count += 1
        self.finished.emit()


def controller_stub(return_to_settings=True):
    class ControllerStub(SimpleNamespace):
        """Weak-referenceable like the real QObject signal receiver."""
    class SetupStub(SimpleNamespace):
        @property
        def availability(self):
            return Availability(self.capture_ready, controller._busy,
                getattr(self, "_installing", False), False, controller._shutting_down, self.hotkey_valid)
    controller = ControllerStub(
        _busy=True,
        _selector=None,
        _review=None,
        _previous_window=None,
        _return_to_settings=return_to_settings,
        _session_id=1,
        _capture_position=None,
        _shutting_down=False,
        _capture_timer=QTimer(),
        _listener=None,
        _desired_hotkey=None,
        _syncing_listener=False,
        _capture_settings=None,
        _save_timer=QTimer(),
        _capture_action=QAction(),
        _listening_action=QAction(),
        global_capture=SimpleNamespace(emit=lambda: None),
        settings=Settings(),
        setup=SetupStub(
            capture_ready=True,
            hotkey_valid=True,
            refresh_model_status=lambda: None,
            set_listening=lambda _hotkey, **_kwargs: None,
            isVisible=lambda: False,
            current_settings=Settings,
            hide=lambda: None,
            pronunciation=SimpleNamespace(
                player=SimpleNamespace(stop=lambda: None), shutdown=lambda: None,
            ),
        ),
        tray=SimpleNamespace(hide=lambda: None, setToolTip=lambda _text: None, showMessage=lambda *_args: None),
        settings_were_shown=False,
    )
    for name in ("begin_capture", "_take_screenshot", "_selection_finished",
                 "_session_finished", "_shutdown", "_reselect", "_capture_allowed",
                 "pause_listening", "start_listening", "_save_speech_speed",
                 "_refresh_tray_listening", "_toggle_tray_listening", "_sync_listener", "_save_preferences"):
        setattr(controller, name, MethodType(getattr(LensController, name), controller))
    controller._capture_timer.setSingleShot(True)
    controller._capture_timer.timeout.connect(controller._take_screenshot)
    controller.show_settings = lambda: setattr(controller, "settings_were_shown", True)
    return controller


def test_tray_listening_action_tracks_start_pause_restart_and_readiness(monkeypatch, qapp):
    controller = controller_stub()
    controller._busy = False
    controller.setup.capture_ready = False
    controller._capture_action = QAction()
    listeners = []
    class Listener:
        def __init__(self, hotkey, _callback):
            self.hotkey, self.started, self.stopped = hotkey, False, False
            listeners.append(self)
        def start(self):
            self.started = True
        def stop(self):
            self.stopped = True
    monkeypatch.setattr(app_module, "WindowsHotkeyListener", Listener)
    monkeypatch.setattr(app_module, "persist", lambda *_args: True)
    controller._listening_action.triggered.connect(controller._toggle_tray_listening)
    controller._refresh_tray_listening()
    assert controller._listening_action.text() == "Start listening"
    assert not controller._listening_action.isEnabled()
    controller._listening_action.trigger()
    assert not listeners
    controller.setup.capture_ready = True
    LensController._readiness_changed(controller, True)
    assert controller._listening_action.isEnabled()
    controller._listening_action.trigger()
    assert listeners[0].started and controller._listening_action.text() == "Pause listening"
    controller._listening_action.trigger()
    assert listeners[0].stopped and controller._listener is None
    assert controller._listening_action.text() == "Start listening"
    controller._listening_action.trigger()
    assert listeners[-1].started
    controller.setup.capture_ready = False
    LensController._readiness_changed(controller, False)
    assert listeners[-1].stopped and controller._listener is None
    assert controller._listening_action.text() == "Start listening"
    assert not controller._listening_action.isEnabled()


def test_tray_listening_action_stays_inactive_after_registration_failure(monkeypatch, qapp):
    controller = controller_stub()
    controller._busy = False
    stopped, errors = [], []
    class Listener:
        def __init__(self, *_args):
            pass
        def start(self):
            raise RuntimeError("Hotkey in use")
        def stop(self):
            stopped.append(True)
    monkeypatch.setattr(app_module, "WindowsHotkeyListener", Listener)
    monkeypatch.setattr(app_module, "persist", lambda *_args: True)
    monkeypatch.setattr(app_module.QMessageBox, "critical", lambda *_args: errors.append(True))
    controller.start_listening(Settings())
    assert stopped == [True] and errors == [True] and controller._listener is None
    assert controller._listening_action.text() == "Start listening"
    assert controller._listening_action.isEnabled()


def test_tray_start_is_disabled_during_capture_but_pause_remains_available(qapp):
    controller = controller_stub()
    controller._refresh_tray_listening()
    assert not controller._listening_action.isEnabled()
    controller._listener = SimpleNamespace(stop=lambda: None)
    controller._desired_hotkey = "<f8>"
    controller._refresh_tray_listening()
    assert controller._listening_action.text() == "Pause listening"
    assert controller._listening_action.isEnabled()


@pytest.fixture(autouse=True)
def verified_capture_files(monkeypatch):
    monkeypatch.setattr(app_module, "save_settings", lambda _settings: None)
    monkeypatch.setattr(app_module, "offline_ready", lambda *_args: True)


@pytest.mark.parametrize("entry", ["capture", "listen", "timer"])
@pytest.mark.parametrize("ui_ready,marker_ready", [(False, False), (False, True), (True, False)])
def test_all_capture_entries_reject_unverified_files(monkeypatch, qapp, entry, ui_ready, marker_ready):
    controller = controller_stub()
    controller._busy = entry == "timer"
    controller.setup.capture_ready = ui_ready
    stopped, captures, registered = [], [], []
    controller._listener = SimpleNamespace(stop=lambda: stopped.append(True))
    monkeypatch.setattr(app_module, "offline_ready", lambda *_args: marker_ready)
    monkeypatch.setattr(app_module, "capture_desktop", lambda *_args: captures.append(True))
    monkeypatch.setattr(app_module, "WindowsHotkeyListener", lambda *_args: registered.append(True))
    if entry == "capture":
        controller.begin_capture(True)
    elif entry == "listen":
        LensController.start_listening(controller, Settings())
    else:
        controller._take_screenshot()
    assert not captures and not registered
    assert stopped == [True] and controller._listener is None
    assert controller.settings_were_shown and not controller._busy


def test_readiness_loss_disables_tray_capture_and_unregisters_hotkey(qapp):
    controller = controller_stub()
    stopped, enabled = [], []
    controller._listener = SimpleNamespace(stop=lambda: stopped.append(True))
    controller._capture_action = SimpleNamespace(setEnabled=enabled.append, setToolTip=lambda _text: None)
    controller._busy = False
    controller.setup.capture_ready = False
    LensController._readiness_changed(controller, False)
    assert stopped == [True] and controller._listener is None and enabled == [False]
    controller.setup.capture_ready = True
    LensController._readiness_changed(controller, True)
    assert enabled == [False, True] and controller._listener is None  # explicit restart


def test_capture_completion_does_not_pause_verified_listener(qapp):
    controller = controller_stub()
    controller.setup.set_capture_busy = lambda _value: None
    controller.setup.refresh_model_status = lambda: pytest.fail("An unchanged capture must not invalidate readiness")
    listener = controller._listener = SimpleNamespace(stop=lambda: pytest.fail("Unexpected pause"))
    controller._desired_hotkey = "<f8>"
    controller._session_finished(return_focus=False)
    assert controller._listener is listener


def test_review_speed_preference_updates_only_speed(monkeypatch, qapp):
    controller = controller_stub()
    updated, saved = [], []
    controller.setup.pronunciation.set_speech_speed = updated.append
    controller.setup.current_settings = lambda: Settings(speech_speed=.65)
    monkeypatch.setattr(app_module, "save_settings", lambda settings: saved.append(deepcopy(settings)))
    before = deepcopy(controller.settings)
    LensController._save_speech_speed(controller, .65)
    assert updated == [.65] and len(saved) == 1
    before.speech_speed = .65
    assert saved[0] == before


def test_hotkey_preference_saves_immediately_without_applying_other_options(monkeypatch, qapp):
    controller = controller_stub()
    saved = []
    monkeypatch.setattr(app_module, "save_settings", lambda settings: saved.append(deepcopy(settings)))
    controller.setup.current_settings = lambda: Settings(source_language="ja", hotkey="<alt>+q")
    before = deepcopy(controller.settings)
    LensController._save_hotkey(controller, "<alt>+q")
    before.hotkey = "<alt>+q"
    assert saved == [before]


def test_invalid_shortcut_disables_tray_start_and_cannot_register(monkeypatch, qapp):
    controller = controller_stub()
    controller._busy = False
    controller.setup.hotkey_valid = False
    monkeypatch.setattr(app_module, "WindowsHotkeyListener", lambda *_args: pytest.fail("Invalid shortcut registered"))
    controller._refresh_tray_listening()
    assert not controller._listening_action.isEnabled()
    controller.start_listening(Settings())
    assert controller._listener is None and controller.settings_were_shown


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


def test_window_preferences_save_does_not_apply_other_pending_options(monkeypatch, qapp):
    saved = []
    monkeypatch.setattr(app_module, "save_settings", lambda settings: saved.append(deepcopy(settings)))
    controller = controller_stub()
    controller.setup.current_settings = lambda: Settings(
        source_language="ja", target_language="es", hotkey="<f8>",
        settings_window_size=[900, 600], settings_window_maximized=True,
    )
    original = deepcopy(controller.settings)
    LensController._save_window_preferences(controller)
    assert len(saved) == 1
    assert saved[0].source_language == original.source_language
    assert saved[0].target_language == original.target_language
    assert saved[0].hotkey == original.hotkey
    assert saved[0].settings_window_size == [900, 600]
    assert saved[0].settings_window_maximized


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
    assert controller._previous_window is None
    controller._session_finished()
    assert restored == [1234]


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


def capture_stub(qapp):
    return DesktopCapture(QPixmap(800, 600), QRect(0, 0, 800, 600))


def test_selector_window_close_allows_another_capture(monkeypatch, qapp):
    monkeypatch.setattr(app_module, "capture_desktop", lambda *args: capture_stub(qapp))
    monkeypatch.setattr(app_module, "save_settings", lambda settings: None)
    monkeypatch.setattr(app_module, "foreground_window", lambda: None)
    controller = controller_stub()
    controller._take_screenshot()
    selector = controller._selector
    selector.close()

    assert not controller._busy
    assert controller._selector is None
    assert controller.settings_were_shown
    # Calling capture twice while active must not create two overlays.
    controller.begin_capture(True)
    next_selector = controller._selector
    controller.begin_capture(True)
    assert controller._selector is next_selector
    assert next_selector is not selector
    next_selector.close()
    assert not controller._busy


@pytest.mark.parametrize("failure_stage", ["capture", "selector_init", "selector_show", "review_show"])
def test_capture_failures_share_cleanup(monkeypatch, qapp, failure_stage):
    def fail(*args):
        raise RuntimeError("test failure")

    monkeypatch.setattr(app_module, "capture_desktop", lambda *args: capture_stub(qapp))
    monkeypatch.setattr(app_module.QMessageBox, "critical", lambda *args: None)
    controller = controller_stub()
    if failure_stage == "capture":
        monkeypatch.setattr(app_module, "capture_desktop", fail)
    elif failure_stage == "selector_init":
        monkeypatch.setattr(app_module, "SelectionOverlay", fail)
    elif failure_stage == "selector_show":
        monkeypatch.setattr(app_module.SelectionOverlay, "show", fail)
    else:
        monkeypatch.setattr(app_module, "ReviewWindow", FakeReview)
        monkeypatch.setattr(FakeReview, "show", fail)
        controller._selection_finished(QPixmap(800, 600), QRect(0, 0, 100, 40))
    if failure_stage != "review_show":
        controller._take_screenshot()
    assert not controller._busy
    assert controller._selector is None
    assert controller._review is None
    assert controller._previous_window is None
    assert controller.settings_were_shown


def test_stale_session_callbacks_cannot_close_or_replace_new_capture(monkeypatch, qapp):
    monkeypatch.setattr(app_module, "capture_desktop", lambda *args: capture_stub(qapp))
    monkeypatch.setattr(app_module, "save_settings", lambda settings: None)
    monkeypatch.setattr(app_module, "foreground_window", lambda: None)
    controller = controller_stub()
    controller._take_screenshot()
    old_selector = controller._selector
    old_selector.close()
    controller.begin_capture(True)
    new_selector = controller._selector

    old_selector.cancelled.emit()
    old_selector.selected.emit(QPixmap(800, 600), QRect(0, 0, 100, 40))
    assert controller._busy
    assert controller._selector is new_selector
    assert controller._review is None
    new_selector.close()


def test_shutdown_cancels_pending_capture_without_restoring_focus(monkeypatch, qapp):
    captures, restored, stopped = [], [], []
    monkeypatch.setattr(app_module, "capture_desktop", lambda *args: captures.append(True))
    monkeypatch.setattr(app_module, "restore_foreground", lambda window: restored.append(window))
    controller = controller_stub()
    controller._listener = SimpleNamespace(stop=lambda: stopped.append(True))
    controller._capture_timer.start(1)
    controller._shutdown()
    controller._shutdown()
    QTest.qWait(25)
    controller._take_screenshot()
    controller.begin_capture(True)

    assert not captures
    assert not restored
    assert stopped == [True]
    assert not controller._busy
    assert not controller.settings_were_shown


def test_cancel_cancels_pending_capture_timer(monkeypatch, qapp):
    captures = []
    monkeypatch.setattr(app_module, "capture_desktop", lambda *args: captures.append(True))
    controller = controller_stub()
    controller._capture_timer.start(1)
    controller._session_finished()
    QTest.qWait(25)
    controller._take_screenshot()
    assert not captures
    assert not controller._capture_timer.isActive()


def test_duplicate_selection_cannot_replace_active_review(monkeypatch, qapp):
    monkeypatch.setattr(app_module, "ReviewWindow", FakeReview)
    controller = controller_stub()
    pixmap, region = QPixmap(800, 600), QRect(0, 0, 100, 40)
    controller._selection_finished(pixmap, region)
    review = controller._review
    controller._selection_finished(pixmap, region)
    assert controller._review is review
    controller._session_finished()


def test_real_selector_review_close_and_second_capture(monkeypatch, qapp):
    from language_lens.ui import review as review_module

    monkeypatch.setattr(app_module, "capture_desktop", lambda *args: capture_stub(qapp))
    monkeypatch.setattr(app_module, "save_settings", lambda settings: None)
    monkeypatch.setattr(app_module, "foreground_window", lambda: None)
    monkeypatch.setattr(review_module, "TaskPool", SimpleNamespace(
        globalInstance=lambda: SimpleNamespace(start=lambda task: None),
    ))
    controller = controller_stub()
    controller.settings = Settings(speech_enabled=False)
    controller._take_screenshot()
    selector = controller._selector
    QTest.mousePress(selector, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    QTest.mouseRelease(selector, Qt.MouseButton.LeftButton, pos=QPoint(200, 100))
    assert controller._selector is None
    assert controller._review is not None
    assert controller._busy
    review = controller._review
    finished = []
    review.finished.connect(lambda: finished.append(True))
    review.close()
    review.close()
    assert finished == [True]
    assert review._translation_cancelled.is_set()
    assert not controller._busy
    assert controller._review is None
    controller.begin_capture(True)
    assert controller._selector is not None
    controller._selector.close()
    assert not controller._busy
    review.deleteLater()


def test_capture_scope_and_pointer_are_snapshotted_before_delay(monkeypatch, qapp):
    calls = []
    pointer = [QPoint(50, 100)]
    monkeypatch.setattr(app_module.QCursor, "pos", lambda: QPoint(pointer[0]))
    monkeypatch.setattr(app_module, "save_settings", lambda settings: None)
    monkeypatch.setattr(app_module, "foreground_window", lambda: None)

    def capture(scope, position):
        calls.append((scope, QPoint(position)))
        return capture_stub(qapp)

    monkeypatch.setattr(app_module, "capture_desktop", capture)
    controller = controller_stub()
    controller._busy = False
    controller.setup.current_settings = lambda: Settings(capture_scope="current")
    controller.begin_capture(False)
    assert not calls
    pointer[0] = QPoint(2000, 500)
    controller._capture_timer.start(1)
    QTest.qWait(25)
    assert calls == [("current", QPoint(50, 100))]
    controller._selector.close()


def test_reselection_uses_same_capture_without_ending_session(monkeypatch, qapp):
    from language_lens.ui import review as review_module
    captures = []
    frozen = capture_stub(qapp)
    monkeypatch.setattr(app_module, "capture_desktop", lambda *_args: captures.append(True) or frozen)
    monkeypatch.setattr(review_module, "TaskPool", SimpleNamespace(
        globalInstance=lambda: SimpleNamespace(start=lambda task: None)))
    controller = controller_stub()
    controller.settings = Settings(speech_enabled=False)
    controller._previous_window = 1234
    controller._take_screenshot()
    selector = controller._selector
    selector.selected.emit(frozen, QRect(40, 40, 180, 60))
    first = controller._review
    first.reselect_requested.emit(frozen)
    assert first._closed and controller._review is None and controller._selector is not None
    assert controller._busy and controller._previous_window == 1234 and captures == [True]
    controller._selector.selected.emit(frozen, QRect(70, 80, 150, 80))
    assert controller._review is not first and controller._review.canvas.capture is frozen
    controller._session_finished()


def test_capture_during_model_work_is_disabled_and_rejected(monkeypatch, qapp):
    controller = controller_stub()
    controller._busy = False
    controller.setup._installing = True
    messages = []
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda _parent, title, text: messages.append((title, text)))
    controller.begin_capture(True)
    controller._refresh_tray_listening()
    assert not controller._busy and not messages
    assert not controller._capture_action.isEnabled()
    assert "local model task" in controller._capture_action.toolTip()


@pytest.mark.parametrize("stage", ["selector", "review"])
def test_shutdown_closes_active_capture_once(monkeypatch, qapp, stage):
    restored = []
    monkeypatch.setattr(app_module, "capture_desktop", lambda *args: capture_stub(qapp))
    monkeypatch.setattr(app_module, "restore_foreground", lambda window: restored.append(window))
    monkeypatch.setattr(app_module, "ReviewWindow", FakeReview)
    controller = controller_stub(return_to_settings=False)
    if stage == "selector":
        controller._take_screenshot()
        window = controller._selector
    else:
        controller._selection_finished(QPixmap(800, 600), QRect(0, 0, 100, 40))
        window = controller._review
    controller._shutdown()
    controller._shutdown()
    assert not controller._busy
    assert controller._selector is None
    assert controller._review is None
    assert not restored
    if stage == "selector":
        assert not window.isVisible()
    else:
        assert window.close_count == 1
