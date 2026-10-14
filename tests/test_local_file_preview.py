"""Size estimates are offline, honest about unknowns, and non-blocking."""
from dataclasses import asdict
from types import SimpleNamespace
import pytest
from language_lens.config import Settings
from language_lens.services import local_files, offline, voices, task_worker, translation_backends


@pytest.fixture
def preview(monkeypatch, tmp_path):
    model = {"files": [{"name": "remote", "bytes": 100, "compressed_bytes": 40},
                       {"name": "word-model", "bytes": 200, "compressed_bytes": 75}]}
    catalog = {"models": {"model": model},
               "node_runtime": {"files": [{"name": "node.exe", "bytes": 500}]},
               "bergamot_runtime": {"files": [{"name": "worker.wasm", "bytes": 250}]}}
    monkeypatch.setattr(local_files.assets, "catalog", lambda: catalog)
    monkeypatch.setattr(local_files.assets, "model_ids", lambda *a: ["model"])
    monkeypatch.setattr(local_files.assets, "model_path", lambda *a: tmp_path / "model")
    monkeypatch.setattr(local_files.assets, "root", lambda: tmp_path)
    monkeypatch.setattr(local_files.assets, "selection", lambda *a: {"full": {"model": "model"}, "word": "model"})
    monkeypatch.setattr(local_files.assets, "valid", lambda *a: False)
    monkeypatch.setattr(local_files.sentence_models, "catalog", lambda: {"models": {"en": {"bytes": 12, "sha256": "x"}}})
    monkeypatch.setattr(local_files.sentence_models, "model_code", lambda *a: "en")
    monkeypatch.setattr(local_files.sentence_models, "model_path", lambda *a: tmp_path / "sentence")
    monkeypatch.setattr(voices, "valid_file", lambda *a: False)
    monkeypatch.setattr(offline, "ocr_models", lambda *a: [])
    monkeypatch.setattr(local_files.language_packs, "text_pack", lambda *a: None)
    return SimpleNamespace(argos_required=lambda *a: False), catalog


def test_runtime_archive_unknowns_do_not_discard_known_downloads(preview):
    translator, _ = preview
    result = local_files.pair_file_summary(Settings(source_language="en", target_language="nl"), translator, [])
    assert result["download_bytes"] == 127  # both compressed models and the sentence model
    assert result["download_unknown"]
    assert [item["size"] for item in result["files"]] == [300, 500, 250, 12]
    assert all(not item["installed"] for item in result["files"])


def test_installed_assets_are_not_counted_as_remaining_downloads(preview, monkeypatch):
    translator, _ = preview
    monkeypatch.setattr(local_files.assets, "valid", lambda *a: True)
    monkeypatch.setattr(voices, "valid_file", lambda *a: True)
    result = local_files.pair_file_summary(Settings(source_language="en", target_language="nl"), translator, [])
    assert result["download_bytes"] == 0 and not result["download_unknown"]
    assert all(item["installed"] for item in result["files"])


def test_known_runtime_archive_size_is_counted_once(preview):
    translator, catalog = preview
    catalog["node_runtime"]["bytes"] = 80
    catalog["bergamot_runtime"]["bytes"] = 60
    result = local_files.pair_file_summary(Settings(source_language="en", target_language="nl"), translator, [])
    assert result["download_bytes"] == 267 and not result["download_unknown"]


def test_failed_preview_does_not_change_capture_readiness(monkeypatch, tmp_path):
    monkeypatch.setattr(translation_backends, "RoutedTranslator", lambda: SimpleNamespace(
        is_pair_installed=lambda *a: True, route=lambda *a: []))
    monkeypatch.setattr(offline, "offline_ready", lambda *a, **k: True)
    monkeypatch.setattr(local_files.language_packs, "inventory", lambda: [])
    def failure(*a): raise OSError("cannot inspect size")
    monkeypatch.setattr(local_files, "pair_file_summary", failure)
    events = []
    task_worker.execute("status", {"settings": asdict(Settings(source_language="en", target_language="nl"))}, tmp_path, events.append)
    assert events[0]["result"]["ready"] and events[0]["result"]["prepared"]
    assert events[0]["result"]["download_unknown"]
