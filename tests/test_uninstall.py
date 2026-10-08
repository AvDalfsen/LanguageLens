import base64
import json
import os
from pathlib import Path
import subprocess

import pytest

from language_lens import uninstall


def release_folder(tmp_path):
    root = tmp_path / "LanguageLens"
    root.mkdir()
    (root / "_internal").mkdir()
    (root / uninstall.MARKER).write_text(
        json.dumps({"product": uninstall.PRODUCT, "layout": 1}), encoding="utf-8")
    for name in ("LanguageLens.exe", "LanguageLensWorker.exe", "LanguageLensUninstall.exe"):
        (root / name).write_bytes(b"test")
    return root


def test_release_root_requires_marker_and_complete_fixed_layout(tmp_path):
    root = release_folder(tmp_path)
    assert uninstall.validate_install_root(root / "LanguageLensUninstall.exe") == root
    (root / "LanguageLens.exe").unlink()
    with pytest.raises(ValueError, match="complete"):
        uninstall.validate_install_root(root / "LanguageLensUninstall.exe")
    (root / "LanguageLens.exe").write_bytes(b"test")
    (root / uninstall.MARKER).write_text('{"product":"another app","layout":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="marker"):
        uninstall.validate_install_root(root / "LanguageLensUninstall.exe")


def test_cleanup_roots_are_fixed_children(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path / "local"),
           "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_CACHE_HOME": str(tmp_path / "cache"),
           "XDG_CONFIG_HOME": str(tmp_path / "config")}
    assert uninstall.app_data_roots(env) == [
        tmp_path / "local/LanguageLens", tmp_path / "local/GameLanguageLens"]
    assert uninstall.shared_argos_roots(env, tmp_path / "home") == [
        tmp_path / "data/argos-translate", tmp_path / "cache/argos-translate",
        tmp_path / "config/argos-translate"]


def test_cleanup_command_encodes_paths_as_data(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemRoot", os.environ["SystemRoot"])
    hostile = tmp_path / "folder with spaces & $(never-execute)"
    powershell, arguments = uninstall.cleanup_command([hostile], 2147483647)
    assert powershell.is_file()
    assert arguments[-2] == "-EncodedCommand"
    script = base64.b64decode(arguments[-1]).decode("utf-16le")
    assert str(hostile) not in script
    assert "FromBase64String" in script and "Remove-Item -LiteralPath" in script


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstaller helper")
def test_cleanup_helper_removes_only_requested_test_roots(tmp_path):
    parent = tmp_path / "keep-parent"
    first, second = parent / "first", parent / "second & safe"
    first.mkdir(parents=True)
    second.mkdir()
    (first / "model.bin").write_bytes(b"model")
    (second / "settings.json").write_text("{}", encoding="utf-8")
    powershell, arguments = uninstall.cleanup_command([first, second], 2147483647)
    result = subprocess.run([str(powershell), *arguments], cwd=tmp_path,
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert parent.is_dir()
    assert not first.exists() and not second.exists()


def test_running_check_uses_language_lens_instance_lock(tmp_path, monkeypatch):
    from filelock import FileLock
    monkeypatch.setattr(uninstall, "app_data_roots", lambda: [tmp_path, tmp_path / "legacy"])
    lock = FileLock(str(tmp_path / "instance.lock"))
    with lock:
        assert uninstall.application_running(tmp_path)
    assert not uninstall.application_running(tmp_path)


def wait_for_cleanup(status, timeout=15):
    import time
    result = status / "result.json"
    deadline = time.monotonic() + timeout
    while not result.is_file() and time.monotonic() < deadline:
        time.sleep(.05)
    assert result.is_file(), (status / "helper.log").read_text(errors="replace")
    return json.loads(result.read_text("utf-8"))


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstaller helper")
def test_actual_hidden_launcher_removes_files_and_acknowledges_start(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    target = tmp_path / "portable & $(never-execute)"
    target.mkdir()
    (target / "model.dat").write_bytes(b"test")
    keep = tmp_path / "unrelated.dat"
    keep.write_bytes(b"keep")
    status = uninstall.schedule_cleanup([target], pid=2147483647)
    assert (status / "started").is_file()
    assert wait_for_cleanup(status)["ok"]
    assert not target.exists()
    assert keep.read_bytes() == b"keep"


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstaller helper")
def test_cleanup_waits_for_launcher_exit_and_survives_it(tmp_path):
    import sys
    import time
    target = tmp_path / "portable"
    target.mkdir()
    (target / "LanguageLensUninstall.exe").write_bytes(b"fixture")
    code = (
        "import json, pathlib, sys, tempfile, time; "
        "from language_lens import uninstall; "
        "tempfile.tempdir = sys.argv[2]; "
        "status = uninstall.schedule_cleanup([pathlib.Path(sys.argv[1])]); "
        "print(json.dumps(str(status)), flush=True); "
        "time.sleep(.5)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", code, str(target), str(tmp_path)], cwd=tmp_path,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        status = Path(json.loads(parent.stdout.readline()))
        assert target.is_dir(), "The helper must wait for the uninstaller to release its files"
        parent.wait(timeout=10)
        assert parent.returncode == 0, parent.stderr.read()
        assert wait_for_cleanup(status)["ok"]
        assert not target.exists()
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstaller helper")
def test_cleanup_retries_until_a_temporary_file_lock_is_released(tmp_path, monkeypatch):
    import tempfile
    import time
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    target = tmp_path / "portable"
    target.mkdir()
    model = target / "model.dat"
    model.write_bytes(b"locked")
    with model.open("rb"):
        status = uninstall.schedule_cleanup([target], pid=2147483647)
        time.sleep(.5)
        assert model.exists()
    assert wait_for_cleanup(status)["ok"]
    assert not target.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstaller helper")
def test_cleanup_records_files_that_remain_locked(tmp_path):
    target = tmp_path / "locked-models"
    target.mkdir()
    model = target / "model.dat"
    model.write_bytes(b"locked")
    status = tmp_path / "status"
    status.mkdir()
    with model.open("rb"):
        powershell, arguments = uninstall.cleanup_command(
            [target], 2147483647, status_dir=status)
        result = subprocess.run(
            [str(powershell), *arguments], cwd=tmp_path, capture_output=True,
            timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode != 0
        report = json.loads((status / "result.json").read_text("utf-8"))
        assert not report["ok"]
        assert report["failures"][0]["path"] == str(target)
        assert report["failures"][0]["error"]
        assert model.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstaller helper")
def test_a_zero_exit_without_starting_is_reported_as_a_failure(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    powershell, _ = uninstall.cleanup_command([tmp_path / "unused"], 2147483647)
    monkeypatch.setattr(uninstall, "cleanup_command",
                        lambda *_args, **_kwargs: (powershell, ["-NoProfile", "-Command", "exit 0"]))
    with pytest.raises(OSError, match="exited before starting"):
        uninstall.schedule_cleanup([tmp_path / "unused"], pid=2147483647)


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstaller helper")
def test_packaged_cleanup_probe_exercises_deletion(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    uninstall.verify_cleanup()


@pytest.mark.parametrize("pid", [0, -1, "1;exit"])
def test_cleanup_rejects_invalid_process_ids(tmp_path, pid):
    with pytest.raises(ValueError, match="process ID"):
        uninstall.cleanup_command([tmp_path / "target"], pid)


def test_cleanup_rejects_drive_and_home_roots():
    for root in (Path(Path.home().anchor), Path.home()):
        with pytest.raises(ValueError, match="not safe"):
            uninstall.cleanup_command([root], 2147483647)
