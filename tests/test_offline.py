"""Preparation must track catalog and route changes without loading models."""
import builtins
import json
from types import SimpleNamespace

import pytest
from language_lens.services import offline


def add_package(root, source, target, name=None):
    directory = root / (name or f"{source}-{target}")
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(json.dumps({"type": "translate", "from_code": source, "to_code": target}), "utf-8")
    return SimpleNamespace(from_code=source, to_code=target, package_path=directory)


@pytest.fixture
def pivot(monkeypatch, tmp_path):
    root = tmp_path / "packages"
    route = [add_package(root, "pt", "en"), add_package(root, "en", "nl")]
    configuration = tmp_path / "argos-settings.json"
    package = SimpleNamespace(settings=SimpleNamespace(package_dirs=[root], settings_file=configuration))
    asset = tmp_path / "ocr.onnx"
    asset.write_bytes(b"verified asset")
    monkeypatch.setattr(offline, "assets_root", lambda: tmp_path)
    monkeypatch.setattr(offline, "runtime_identity", lambda: {"fixture": "1"})
    record = {"version": 3, "runtime": offline.runtime_identity(), "sentence_models": {},
              "translation": offline.translation_state(package, route),
              "files": [[str(asset), asset.stat().st_size, asset.stat().st_mtime_ns]]}
    offline.marker_path("pt", "nl").write_text(json.dumps(record))
    assert offline.offline_ready("pt", "nl", route=route)
    return root, route, configuration


@pytest.mark.parametrize("change", ["direct", "duplicate", "unrelated", "metadata", "remove", "configuration"])
def test_catalog_changes_invalidate_preparation(pivot, change):
    root, route, configuration = pivot
    if change == "direct":
        add_package(root, "pt", "nl")  # Metadata only, no usable weights/tokenizer.
    elif change == "duplicate":
        add_package(root, "pt", "en", "new-version")
    elif change == "unrelated":
        add_package(root, "de", "fr")  # Conservative: pivot/enumeration may change.
    elif change == "metadata":
        (route[0].package_path / "metadata.json").write_text("{}", "utf-8")
    elif change == "remove":
        (route[0].package_path / "metadata.json").unlink()
    else:
        configuration.write_text('{"ARGOS_PACKAGES_DIR": "different"}', "utf-8")
    assert not offline.offline_ready("pt", "nl")


def test_status_can_reject_a_different_selected_route(pivot):
    root, route, _ = pivot
    changed = SimpleNamespace(from_code="pt", to_code="nl", package_path=route[0].package_path)
    assert not offline.offline_ready("pt", "nl", route=[changed])


def test_gui_readiness_does_not_import_native_translation(pivot, monkeypatch):
    real = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith(("argostranslate", "ctranslate2", "sentencepiece")), name
        return real(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert offline.offline_ready("pt", "nl")


def test_legacy_marker_requires_one_new_offline_check(pivot):
    path = offline.marker_path("pt", "nl")
    record = json.loads(path.read_text("utf-8"))
    record["version"] = 2
    path.write_text(json.dumps(record), "utf-8")
    assert not offline.offline_ready("pt", "nl")
