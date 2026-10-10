import hashlib
import io
import json
import os
import tarfile
import zipfile

import pytest

from language_lens.services import language_packs as packs
from language_lens.services.errors import KnownTaskError


@pytest.fixture
def pack_store(tmp_path, monkeypatch):
    monkeypatch.setattr(packs, "packs_root", lambda: tmp_path / "packs")
    monkeypatch.setattr(packs, "frozen", lambda: True)
    monkeypatch.setattr(packs, "_activated", {})
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("janome/__init__.py", "VALUE = 42\n")
        archive.writestr("Janome.dist-info/LICENSE", "Fixture licence\n")
    payload = content.getvalue()
    item = {"distribution": "janome", "version": "0.5.0", "url": "https://invalid.test/pack.whl",
            "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "format": "wheel"}
    catalog = {"packs": {"ja-text": {"name": "Japanese word lookup", "artifacts": ["test"], "modules": ["janome"]}},
               "artifacts": {"test": item}}
    monkeypatch.setattr(packs, "catalog", lambda: catalog)
    monkeypatch.setattr(packs, "urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))
    return catalog, payload


def test_install_verify_reuse_and_remove_shared_pack(pack_store, monkeypatch):
    assert not packs.ready("ja-text")
    progress = []
    packs.install("ja-text", progress=progress.append)
    assert packs.ready("ja-text")
    assert progress[-1].received == progress[-1].total == packs.download_bytes("ja-text")
    assert len(list(packs.packs_root().glob("ja-text-*"))) == 1
    assert packs._installed("ja-text", verify=True)
    def no_download(*_args, **_kwargs):
        pytest.fail("An intact pack must not download again")
    monkeypatch.setattr(packs, "urlopen", no_download)
    packs.install("ja-text")
    packs.remove("ja-text")
    assert not packs.ready("ja-text")
    assert not list(packs.packs_root().glob("ja-text-*"))


@pytest.mark.parametrize("failure", ["truncated", "checksum", "cancel"])
def test_failed_update_preserves_published_installation(pack_store, monkeypatch, failure):
    catalog, payload = pack_store
    packs.install("ja-text")
    pointer = packs.packs_root() / "ja-text.json"
    previous = pointer.read_bytes()
    old_directory = packs.packs_root() / json.loads(previous)["directory"]
    catalog["artifacts"]["test"]["version"] = "new-version"
    if failure == "cancel":
        def interrupted(*_args, **_kwargs):
            raise KeyboardInterrupt
        monkeypatch.setattr(packs, "urlopen", interrupted)
        expected = KeyboardInterrupt
    else:
        bad = payload[:-1] if failure == "truncated" else b"x" * len(payload)
        monkeypatch.setattr(packs, "urlopen", lambda *_args, **_kwargs: io.BytesIO(bad))
        expected = KnownTaskError
    with pytest.raises(expected):
        packs.install("ja-text")
    assert pointer.read_bytes() == previous
    assert (old_directory / "janome/__init__.py").exists()
    assert list(packs.packs_root().glob("ja-text-*")) == [old_directory]
    # The old app's catalogue can still load the old pack.
    catalog["artifacts"]["test"]["version"] = "0.5.0"
    assert packs.ready("ja-text")


def test_same_size_corruption_is_repaired_even_with_preserved_timestamp(pack_store):
    packs.install("ja-text")
    directory, _ = packs._installed("ja-text")
    path = directory / "janome/__init__.py"
    previous = path.stat()
    path.write_bytes(b"x" * previous.st_size)
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert packs._installed("ja-text", verify=True) is None
    packs.install("ja-text")
    replacement, _ = packs._installed("ja-text", verify=True)
    assert replacement != directory
    assert not directory.exists()


@pytest.mark.parametrize("name", ["../outside", "a/../../outside", "/absolute", "C:/outside", "..\\outside", "a/../x", "a/./x"])
def test_archive_paths_cannot_escape_installation(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output:
        entry = zipfile.ZipInfo("placeholder")
        entry.filename = name  # retain Windows separators instead of writer normalization
        output.writestr(entry, "bad")
    with pytest.raises(KnownTaskError):
        packs._extract(archive, {"format": "wheel"}, tmp_path / "destination")


def test_sdist_extracts_package_and_notice_without_running_setup(tmp_path):
    archive = tmp_path / "jieba.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        for name in ("jieba/__init__.py", "LICENSE", "setup.py", "tests/test.py"):
            item = tarfile.TarInfo("jieba-0.42.1/" + name)
            content = b"raise RuntimeError('must not run')"
            item.size = len(content)
            output.addfile(item, io.BytesIO(content))
    destination = tmp_path / "unpacked"
    packs._extract(archive, {"format": "sdist"}, destination)
    assert (destination / "jieba/__init__.py").exists()
    assert (destination / "LICENSE").exists()
    assert not (destination / "setup.py").exists()


def test_missing_pack_activation_never_downloads(pack_store, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Capture must never download packs")
    monkeypatch.setattr(packs, "urlopen", forbidden)
    with pytest.raises(KnownTaskError, match="missing_pack"):
        packs.activate("ja-text")


def test_pack_readiness_only_invalidates_its_source_language(tmp_path, monkeypatch, offline_record):
    from language_lens.services import offline
    monkeypatch.setattr(offline, "assets_root", lambda: tmp_path)
    monkeypatch.setattr(offline, "runtime_identity", lambda: {"runtime": "fixture"})
    monkeypatch.setattr(packs, "ready", lambda _pack: True)
    model = tmp_path / "model"
    model.write_bytes(b"model")
    offline.marker_path("en", "ja").write_text(json.dumps(offline_record("en", "ja", model)))
    marker = offline_record("ja", "en", model)
    marker["language_pack"] = packs.identity("ja-text")
    offline.marker_path("ja", "en").write_text(json.dumps(marker))
    assert offline.offline_ready("ja", "en")
    monkeypatch.setattr(packs, "ready", lambda _pack: False)
    assert not offline.offline_ready("ja", "en")
    assert offline.offline_ready("en", "ja")


def test_pack_removal_does_not_touch_other_user_assets(pack_store):
    voices = packs.packs_root().parent / "voices/example"
    voices.mkdir(parents=True)
    model = voices / "voice.onnx"
    model.write_bytes(b"keep")
    packs.install("ja-text")
    packs.remove("ja-text")
    assert model.read_bytes() == b"keep"


def test_archive_symlinks_are_rejected(tmp_path):
    import stat
    archive = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive, "w") as output:
        entry = zipfile.ZipInfo("link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        output.writestr(entry, "../../outside")
    with pytest.raises(KnownTaskError):
        packs._extract(archive, {"format": "wheel"}, tmp_path / "destination")


def test_japanese_ipa_only_can_download_pack_without_voice(qapp, monkeypatch):
    from language_lens.config import Settings
    from language_lens.ui.pronunciation import PronunciationSettings
    monkeypatch.setattr(packs, "ready", lambda _pack: False)
    widget = PronunciationSettings(Settings(source_language="ja", speech_enabled=False, show_ipa=True))
    commands = []
    monkeypatch.setattr(widget.download, "start", lambda command, _voice: commands.append(command))
    assert widget.install.isEnabled()
    assert widget.install.text().startswith("Download pronunciation")
    widget.install.click()
    assert commands == ["download-pronunciation"]
    widget.set_maintenance_blocked(True)
    assert not widget.install.isEnabled()
    widget.shutdown()
