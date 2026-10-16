"""Behavior regressions for the audit of af23d03."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QMessageBox

from language_lens import uninstall
from language_lens.config import Settings
from language_lens.services import model_management, speech, voices
from language_lens.ui import setup
from test_uninstall import release_folder


def test_legacy_release_without_ownership_inventory_refuses_uninstall(tmp_path):
    root = release_folder(tmp_path)
    (root / uninstall.INVENTORY).unlink()
    unrelated = root / "user-document.txt"
    unrelated.write_bytes(b"keep")
    with pytest.raises(ValueError, match="inventory"):
        uninstall.validate_install_root(root / "LanguageLensUninstall.exe")
    assert unrelated.read_bytes() == b"keep"


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstall helper")
def test_release_uninstall_preserves_unrelated_and_late_added_files(tmp_path):
    root = release_folder(tmp_path)
    unrelated = root / "user-document.txt"
    unrelated.write_bytes(b"keep")
    nested = root / "_internal/unrelated-notes.txt"
    nested.write_bytes(b"nested keep")
    powershell, arguments = uninstall.cleanup_command([], 2147483647, release_root=root)
    late = root / "added-after-planning.txt"
    late.write_bytes(b"late keep")
    result = subprocess.run([str(powershell), *arguments], cwd=tmp_path, capture_output=True,
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    assert all(path.is_file() for path in (unrelated, nested, late))
    assert unrelated.read_bytes() == b"keep" and nested.read_bytes() == b"nested keep"
    assert late.read_bytes() == b"late keep"
    assert not any((root / name).exists() for name in uninstall.EXECUTABLES)
    assert not (root / uninstall.INVENTORY).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstall helper")
def test_release_uninstall_removes_an_empty_dedicated_folder(tmp_path):
    root = release_folder(tmp_path)
    powershell, arguments = uninstall.cleanup_command([], 2147483647, release_root=root)
    result = subprocess.run([str(powershell), *arguments], cwd=tmp_path, capture_output=True,
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    assert not root.exists()


@pytest.mark.parametrize("unsafe", ["../outside.txt", "/outside.txt", "C:/outside.txt", "folder/../outside", "folder\\outside", "folder:stream", "folder./file", None])
def test_inventory_paths_cannot_escape_release_root(tmp_path, unsafe):
    root = release_folder(tmp_path)
    inventory = root / uninstall.INVENTORY
    record = json.loads(inventory.read_text("utf-8"))
    record["files"].append(unsafe)
    inventory.write_text(json.dumps(record), "utf-8")
    with pytest.raises(ValueError, match="unsafe"):
        uninstall.cleanup_command([], 2147483647, release_root=root)
    assert (root / "LanguageLens.exe").is_file()


def test_recursive_data_cleanup_cannot_include_the_release(tmp_path):
    root = release_folder(tmp_path)
    with pytest.raises(ValueError, match="must not contain"):
        uninstall.cleanup_command([tmp_path], 2147483647, release_root=root)


@pytest.mark.skipif(os.name != "nt", reason="Windows uninstall helper")
def test_full_release_inventory_uses_file_handoff_within_windows_command_limit(tmp_path):
    root = release_folder(tmp_path)
    for index in range(120):
        (root / "_internal" / (f"runtime-{index}-" + "long-name-" * 8 + ".dll")).write_bytes(b"fixture")
    uninstall.write_install_inventory(root)
    status = tmp_path / "status"
    status.mkdir()
    powershell, arguments = uninstall.cleanup_command([], 2147483647, release_root=root, status_dir=status)
    assert len(subprocess.list2cmdline([str(powershell), *arguments])) < 32767
    assert len(json.loads((status / "cleanup.json").read_text("utf-8"))["release"]["files"]) >= 125
    result = subprocess.run([str(powershell), *arguments], cwd=tmp_path, capture_output=True,
                            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    assert not root.exists()


@pytest.mark.parametrize("distribution,version", [("argostranslate", "1.10.0"), ("minisbd", "0.9.4"), ("minisbd", "missing"), ("argostranslate", "1.11.0")])
def test_actual_launcher_health_rejects_incompatible_sentence_dependencies(tmp_path, distribution, version):
    script = Path(__file__).parents[1] / "scripts/environment.ps1"
    health = re.search(r'\$Health = "([^"]+)"', script.read_text("utf-8"))[1]
    code = '''
import importlib.metadata as metadata, sys
actual = metadata.version
def simulated(name):
    if name == sys.argv[2]:
        if sys.argv[3] == 'missing':
            raise metadata.PackageNotFoundError(name)
        return sys.argv[3]
    return actual(name)
metadata.version = simulated
exec(sys.argv[1])
assert not any(name in sys.modules for name in ('argostranslate.translate', 'stanza', 'torch', 'spacy'))
'''
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), XDG_DATA_HOME=str(tmp_path / "data"),
               XDG_CONFIG_HOME=str(tmp_path / "config"), XDG_CACHE_HOME=str(tmp_path / "cache"))
    result = subprocess.run([sys.executable, "-I", "-c", code, health, distribution, version],
                            capture_output=True, env=env, timeout=45)
    assert (result.returncode == 0) == (version == "1.11.0"), result.stderr


@pytest.mark.parametrize("japanese", [False, True])
def test_missing_speech_runtime_reports_recovery_without_launching_worker(qapp, tmp_path, monkeypatch, japanese):
    monkeypatch.setattr(speech, "runtime_ready", lambda: False)
    player = speech.SpeechPlayer(root=tmp_path)
    calls, changes = [], []
    monkeypatch.setattr(player.job, "start", lambda *args, **kwargs: calls.append(args))
    player.changed.connect(lambda state, detail: changes.append((state, detail)))
    voice = next(voice for voice in voices.VOICES if (voice.phoneme_type == "japanese") == japanese)
    try:
        player.speak("Hello", voice)
        assert player.state == "error" and not calls
        assert changes[-1][0] == "error"
        assert ("Japanese pronunciation pack" if japanese else "Start Language Lens.bat") in changes[-1][1]
    finally:
        player.shutdown()


def worker(tmp_path, command, **payload):
    root = tmp_path / "packages"
    scratch = tmp_path / "scratch"
    scratch.mkdir(exist_ok=True)
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), XDG_DATA_HOME=str(tmp_path / "data"),
               XDG_CONFIG_HOME=str(tmp_path / "config"), XDG_CACHE_HOME=str(tmp_path / "cache"),
               ARGOS_PACKAGES_DIR=str(root))
    request = json.dumps({"settings": asdict(Settings(source_language="en", target_language="nl")), **payload}).encode()
    result = subprocess.run([sys.executable, "-m", "language_lens.services.task_worker", command,
                             "--scratch", str(scratch)], input=request, capture_output=True, env=env, timeout=45)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith(b"{")]
    return result, events


def test_real_worker_recovers_corrupt_metadata_without_removing_healthy_packages(tmp_path):
    root = tmp_path / "packages"
    broken, healthy = root / "damaged-model", root / "healthy-en-nl"
    broken.mkdir(parents=True)
    healthy.mkdir()
    (broken / "metadata.json").write_text("{", "utf-8")
    (broken / "model.bin").write_bytes(b"preserved damaged model")
    healthy_metadata = json.dumps({"from_code": "en", "to_code": "nl", "package_version": "1.0"})
    (healthy / "metadata.json").write_text(healthy_metadata, "utf-8")
    result, events = worker(tmp_path, "status")
    assert result.returncode == 0, events
    status = next(event["result"] for event in events if "result" in event)
    assert status["damaged_models"] == [{"root": str(root), "name": broken.name}]
    assert broken.is_dir() and healthy.is_dir()  # Inspection itself changes no packages.
    result, events = worker(tmp_path, "quarantine", damaged_models=status["damaged_models"])
    assert result.returncode == 0, events
    assert not broken.exists()
    backups = list((tmp_path / "language-lens-removed-models").iterdir())
    assert len(backups) == 1 and (backups[0] / "metadata.json").read_text("utf-8") == "{"
    assert (backups[0] / "model.bin").read_bytes() == b"preserved damaged model"
    assert (healthy / "metadata.json").read_text("utf-8") == healthy_metadata
    result, events = worker(tmp_path, "status")
    assert result.returncode == 0, events
    status = next(event["result"] for event in events if "result" in event)
    # The healthy Argos package remains installed; the independently downloaded
    # T5 full-text model is still missing from this empty test profile.
    assert not status["ready"] and not status.get("damaged_models")


def package_fixture(root):
    return SimpleNamespace(settings=SimpleNamespace(package_dirs=[root]),
                           AvailablePackage=lambda metadata: SimpleNamespace(**metadata))


def test_missing_metadata_and_invalid_identity_are_diagnosed(tmp_path):
    missing, invalid = tmp_path / "missing", tmp_path / "invalid"
    missing.mkdir()
    invalid.mkdir()
    (invalid / "metadata.json").write_text('{"from_code":null,"to_code":"nl"}', "utf-8")
    assert {entry["name"] for entry in model_management.damaged_metadata(package_fixture(tmp_path))} == {"missing", "invalid"}


def test_metadata_permission_failures_do_not_offer_quarantine(tmp_path, monkeypatch):
    (tmp_path / "model").mkdir()
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        model_management.damaged_metadata(package_fixture(tmp_path))


def test_recovery_refuses_stale_or_outside_selections_before_moving_any_model(tmp_path):
    root, outside = tmp_path / "packages", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    broken, repaired = root / "broken", root / "repaired"
    broken.mkdir()
    repaired.mkdir()
    (broken / "metadata.json").write_text("{", "utf-8")
    (repaired / "metadata.json").write_text('{"from_code":"en","to_code":"nl"}', "utf-8")
    package = package_fixture(root)
    with pytest.raises(ValueError, match="selection changed"):
        model_management.quarantine_damaged(package, [{"root": str(root), "name": path.name} for path in (broken, repaired)], lambda _: None)
    with pytest.raises(ValueError, match="outside"):
        model_management.quarantine_damaged(package, [{"root": str(outside), "name": "unknown"}], lambda _: None)
    assert broken.is_dir() and repaired.is_dir() and not (tmp_path / "language-lens-removed-models").exists()


def test_settings_offers_explicit_backup_only_for_diagnosed_damage(qapp, monkeypatch):
    monkeypatch.setattr(setup.SetupWindow, "refresh_model_status", lambda _self: None)
    window = setup.SetupWindow(Settings(source_language="en", target_language="nl"))
    diagnosed = [{"root": "C:/fixture/packages", "name": "damaged-model"}]
    calls = []
    monkeypatch.setattr(window.model_job, "start", lambda *args: calls.append(args))
    try:
        window._apply_model_status({"ready": False, "prepared": False, "route": [], "damaged_models": diagnosed})
        assert window.quarantine_button.isEnabled() and not window.quarantine_button.isHidden()
        assert window.maintenance.toggle.isChecked()
        assert not window.repair_button.isEnabled() and not window.remove_button.isEnabled()
        window.set_capture_busy(True)
        assert not window.quarantine_button.isEnabled()
        window.set_capture_busy(False)
        monkeypatch.setattr(setup, "question", lambda *_args: QMessageBox.StandardButton.No)
        window.quarantine_button.click()
        assert not calls
        monkeypatch.setattr(setup, "question", lambda *_args: QMessageBox.StandardButton.Yes)
        window.quarantine_button.click()
        assert calls[-1][0] == "quarantine" and calls[-1][1]["damaged_models"] == diagnosed
        window._installing = False
        window._status_failed("Unknown transient inspection error")
        assert window.quarantine_button.isHidden() and not window._damaged_models
    finally:
        window.shutdown()


def test_legacy_checkpoint_guard_blocks_unsafe_fallback_but_loads_plain_weights(tmp_path):
    code = '''
import io, os, pickle, sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from stanza_safety import require_safe_checkpoint_loading
os.environ['TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD'] = '1'
require_safe_checkpoint_loading()
import torch
assert 'TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD' not in os.environ
unsafe = io.BytesIO()
torch.save(SimpleNamespace(value='benign unsupported object'), unsafe)
unsafe.seek(0)
try:
    torch.load(unsafe, weights_only=False)
except pickle.UnpicklingError:
    pass
else:
    raise AssertionError('The explicit unsafe fallback was not blocked')
safe = io.BytesIO()
torch.save({'weights': torch.ones(2)}, safe)
safe.seek(0)
assert torch.equal(torch.load(safe, weights_only=False)['weights'], torch.ones(2))
'''
    result = subprocess.run([sys.executable, "-c", code, str(Path(__file__).parents[1] / "scripts")],
                            cwd=tmp_path, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stderr


def test_legacy_checkpoint_guard_refuses_unsupported_torch_without_importing_it():
    code = '''
import sys
sys.path.insert(0, sys.argv[1])
import stanza_safety
stanza_safety.version = lambda _: '2.5.1'
try:
    stanza_safety.require_safe_checkpoint_loading()
except RuntimeError:
    pass
else:
    raise AssertionError('Old Torch must not use an unimplemented safety override')
assert 'torch' not in sys.modules
'''
    result = subprocess.run([sys.executable, "-c", code, str(Path(__file__).parents[1] / "scripts")],
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_model_downloads_refuse_http_and_https_downgrade_before_connecting(tmp_path, monkeypatch):
    from urllib.request import Request
    from language_lens.services import model_download
    calls = []
    monkeypatch.setattr(model_download, "build_opener", lambda *_args: calls.append(True))
    with pytest.raises(ValueError, match="HTTPS"):
        model_download.urlopen(Request("http://example.test/model"), timeout=30)
    assert not calls
    model = SimpleNamespace(links=["http://example.test/model"])
    with pytest.raises(ValueError, match="HTTPS"):
        model_download.download_model(model, None, "fixture", lambda _: None)
    redirect = model_download._HttpsRedirects()
    with pytest.raises(ValueError, match="insecure"):
        redirect.redirect_request(Request("https://example.test/model"), None, 302, "Found", {}, "http://example.test/model")
    safe = redirect.redirect_request(Request("https://example.test/model"), None, 302, "Found", {}, "https://mirror.test/model")
    assert safe.full_url == "https://mirror.test/model"
