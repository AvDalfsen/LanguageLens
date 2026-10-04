import hashlib
import json
import subprocess
import sys
from unittest.mock import Mock

from prototypes.pronunciation import run


def test_download_verification_catches_same_size_corruption(tmp_path):
    path = tmp_path / "fixture"
    path.write_bytes(b"right")
    expected = [5, hashlib.md5(b"right", usedforsecurity=False).hexdigest()]
    assert run.valid_file(path, expected)
    path.write_bytes(b"wrong")
    assert not run.valid_file(path, expected)


def test_supervisor_handles_native_crash_and_continues_other_locales(monkeypatch, tmp_path):
    monkeypatch.setattr(run.platform, "platform", lambda: "test-os")
    invoke = Mock(side_effect=[
        subprocess.CompletedProcess([], -1, "", "native error"),
        subprocess.CompletedProcess([], 0, json.dumps({"locale": "pt-PT", "cases": []}), ""),
    ])
    monkeypatch.setattr(run.subprocess, "run", invoke)
    report = run.run_supervised(["en-US", "pt-PT"], tmp_path, None, None, 10)
    assert len(report["errors"]) == 1
    assert report["locales"][0]["locale"] == "pt-PT"


def test_supervisor_passes_text_as_data_and_applies_real_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(run.platform, "platform", lambda: "test-os")
    original = subprocess.run

    def slow_worker(command, **kwargs):
        assert command[command.index("--text") + 1] == "<voice> [[hello]] & $anything"
        assert "shell" not in kwargs
        return original([sys.executable, "-c", "import time; time.sleep(20)"], **kwargs)

    monkeypatch.setattr(run.subprocess, "run", slow_worker)
    report = run.run_supervised(["en-US"], tmp_path, "<voice> [[hello]] & $anything", None, 0.2)
    assert not report["locales"]
    assert "terminated" in report["errors"][0]


def test_render_report_escapes_worker_errors(tmp_path):
    report = {"locales": [], "errors": ["<script>alert('bad')</script>"]}
    run.write_report(report, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "&lt;script&gt;" in html
