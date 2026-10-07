import io
from types import SimpleNamespace
from urllib.error import URLError
import zipfile

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from language_lens.config import Settings
from language_lens.services import model_download, translation
from language_lens.services.model_download import DownloadProgress, download_model
from language_lens.ui import setup


def archive_bytes():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("model/metadata.json", '{"from_code":"nl","to_code":"en"}')
        archive.writestr("model/data", b"data" * 4096)
    return output.getvalue()


class Response(io.BytesIO):
    def __init__(self, data, length=None, clock=None):
        super().__init__(data)
        self.headers = {} if length is None else {"Content-Length": str(length)}
        self.clock = clock

    def read1(self, size):
        if self.clock is not None:
            self.clock[0] += .2
        return super().read(min(size, 1024))


def package_stub(tmp_path):
    package = SimpleNamespace(settings=SimpleNamespace(downloads_dir=tmp_path),
                              argospm_package_name=lambda _: "translate-nl_en")
    model = SimpleNamespace(links=["https://example.test/model.argosmodel"])
    return model, package


def test_stream_reports_real_bytes_before_completion_and_reuses_valid_cache(tmp_path, monkeypatch):
    data = archive_bytes()
    model, package = package_stub(tmp_path)
    clock = [0.0]
    requests, events, stages = [], [], []
    def fetch(request, timeout):
        requests.append((request.full_url, timeout))
        return Response(data, len(data), clock)
    monkeypatch.setattr(model_download, "urlopen", fetch)
    monkeypatch.setattr(model_download, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    path = download_model(model, package, "Dutch → English", stages.append, events.append)
    assert path.read_bytes() == data
    assert requests == [(model.links[0], 30)]
    assert events[0].received == 0 and events[-1].received == len(data)
    assert all(event.total == len(data) for event in events)
    assert any(0 < event.received < len(data) for event in events)
    assert "Checking downloaded" in stages[-1]
    assert not list(tmp_path.glob("*.part"))
    assert download_model(model, package, "Dutch → English", stages.append) == path
    assert len(requests) == 1
    assert "Checking cached" in stages[-1]


@pytest.mark.parametrize("length", [None, "not-a-number", 0])
def test_unknown_total_still_reports_received_bytes(tmp_path, monkeypatch, length):
    data = archive_bytes()
    model, package = package_stub(tmp_path)
    events = []
    monkeypatch.setattr(model_download, "urlopen", lambda *a, **kw: Response(data, length))
    download_model(model, package, "test", lambda _: None, events.append)
    assert events[-1].received == len(data)
    assert all(event.total is None for event in events)


def test_truncated_transfer_does_not_publish_partial_or_overwrite_cache(tmp_path, monkeypatch):
    data = archive_bytes()
    model, package = package_stub(tmp_path)
    destination = tmp_path / "translate-nl_en.argosmodel"
    destination.write_bytes(b"previous broken download")
    monkeypatch.setattr(model_download, "urlopen", lambda *a, **kw: Response(data[:100], len(data)))
    with pytest.raises(RuntimeError, match="Incomplete model download"):
        download_model(model, package, "test", lambda _: None)
    assert destination.read_bytes() == b"previous broken download"
    assert not list(tmp_path.glob("*.part"))
    monkeypatch.setattr(model_download, "urlopen", lambda *a, **kw: Response(data, len(data)))
    assert download_model(model, package, "test", lambda _: None).read_bytes() == data


def test_failed_mirror_retries_visibly_then_uses_alternative(tmp_path, monkeypatch):
    data = archive_bytes()
    model, package = package_stub(tmp_path)
    model.links = ["https://bad.test/model", "https://good.test/model"]
    requests, stages = [], []
    def fetch(request, timeout):
        requests.append(request.full_url)
        if "bad.test" in request.full_url:
            raise URLError("Connection timed out")
        return Response(data, len(data))
    monkeypatch.setattr(model_download, "urlopen", fetch)
    download_model(model, package, "test", stages.append)
    assert requests == [model.links[0], model.links[0], model.links[1]]
    assert any("attempt 2/4" in message for message in stages)
    assert any("attempt 3/4" in message for message in stages)


def test_invalid_archive_with_matching_size_is_not_cached(tmp_path, monkeypatch):
    model, package = package_stub(tmp_path)
    monkeypatch.setattr(model_download, "urlopen", lambda *a, **kw: Response(b"server error", 12))
    with pytest.raises(RuntimeError, match="incomplete or damaged"):
        download_model(model, package, "test", lambda _: None)
    assert not list(tmp_path.iterdir())


def test_english_pivot_downloads_are_labelled_separately(monkeypatch):
    first = SimpleNamespace(from_code="nl", from_name="Dutch", to_code="en", to_name="English")
    second = SimpleNamespace(from_code="en", from_name="English", to_code="pt", to_name="Portuguese")
    installed, labels = [], []
    package = SimpleNamespace(update_package_index=lambda: None, get_available_packages=lambda: [first, second],
                              install_from_path=installed.append)
    backend = SimpleNamespace(get_installed_languages=lambda: [])
    monkeypatch.setattr(translation.ArgosTranslator, "_modules", staticmethod(lambda: (package, backend)))
    def fetch(model, _package, label, report, progress):
        labels.append(label)
        progress(DownloadProgress(100, 200))
        return model.from_code + "_" + model.to_code
    monkeypatch.setattr(translation, "download_model", fetch)
    events, phases = [], []
    translation.ArgosTranslator().install_pair("nl", "pt", phases.append, events.append)
    assert installed == ["nl_en", "en_pt"]
    assert "model 1 of 2" in labels[0] and "model 2 of 2" in labels[1]
    assert len(events) == 2
    assert sum(message.startswith("Installing") for message in phases) == 2


@pytest.fixture
def progress_window(qapp, monkeypatch):
    clock = [100.0]
    tasks = []
    monkeypatch.setattr(setup, "monotonic", lambda: clock[0])
    monkeypatch.setattr(setup.ServiceJob, "start", lambda self, *args, **kwargs: tasks.append(self))
    window = setup.SetupWindow(Settings())
    window.prepare_button.click()
    job = tasks[0]
    task = SimpleNamespace(signals=SimpleNamespace(
        progress=SimpleNamespace(emit=lambda value: job.event.emit({"progress": value})),
        download_progress=SimpleNamespace(emit=lambda value: window._download_progress_changed(value)),
        finished=job.finished, error=job.failed))
    yield window, clock, task
    window._stop_model_progress()
    window.pronunciation.shutdown()
    window.close()
    # Destroy native widgets while the QApplication is still alive, rather
    # than leaving signal/fixture references for pytest's final garbage sweep.
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_capture_area_choices_are_exposed_and_saved(progress_window):
    window, _, _ = progress_window
    assert window.capture_scope.currentData() == "all"
    window.capture_scope.setCurrentIndex(window.capture_scope.findData("current"))
    assert window.current_settings().capture_scope == "current"
    window.capture_scope.setCurrentIndex(window.capture_scope.findData("all"))
    assert window.current_settings().capture_scope == "all"


def test_ui_shows_percent_speed_eta_and_stalled_connection(progress_window):
    window, clock, task = progress_window
    task.signals.progress.emit("Downloading Dutch → English…")
    task.signals.download_progress.emit(DownloadProgress(0, 10_000_000, 100.0))
    clock[0] = 102.0
    task.signals.download_progress.emit(DownloadProgress(4_000_000, 10_000_000, 102.0))
    assert window.model_progress.maximum() == 1000
    assert window.model_progress.value() == 400
    details = window.model_details.text()
    assert "40.0%" in details and "4.0 MB / 10.0 MB" in details
    assert "2.0 MB/s" in details and "~3 s remaining" in details
    for timestamp in (103, 104, 105, 106):
        clock[0] = timestamp
        window._update_download_metrics()
    assert "0 B/s" in window.model_details.text()
    assert "Waiting for data (4 s)" in window.model_details.text()
    assert window.model_progress.value() == 400
    task.signals.progress.emit("Installing Dutch → English…")
    clock[0] = 108
    window._update_download_metrics()
    assert "/s" not in window.model_details.text()
    assert "2 s elapsed" in window.model_details.text()
    task.signals.finished.emit()
    assert window.model_details.isHidden()
    assert not window._progress_timer.isActive()


def test_unknown_size_and_retry_do_not_show_false_percentages(progress_window):
    window, clock, task = progress_window
    task.signals.download_progress.emit(DownloadProgress(0, None, 100))
    clock[0] = 101
    task.signals.download_progress.emit(DownloadProgress(100_000, None, 101))
    assert "100.0 KB" in window.model_details.text()
    assert "100.0 KB/s" in window.model_details.text()
    assert "%" not in window.model_details.text()
    assert window.model_progress.maximum() == 0
    task.signals.progress.emit("Downloading Dutch → English (attempt 2/2)…")
    task.signals.download_progress.emit(DownloadProgress(0, 200_000, 101))
    assert window.model_progress.value() == 0
    task.signals.error.emit("Connection timed out")
    assert not window._progress_timer.isActive()
    assert window.prepare_button.isEnabled()
    window.prepare_button.click()
    assert window.model_progress.maximum() == 0
    assert window._download_snapshot is None
