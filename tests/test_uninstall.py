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
