"""Explicit, pair-specific word downloads retain the tested model bytes."""
import hashlib
import io

import pytest
import zstandard

from language_lens.services import translation_assets as assets
from language_lens.services.errors import KnownTaskError


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def downloads(monkeypatch, tmp_path):
    payloads = {}
    models = {}
    for kind in ("small", "m2m"):
        files = []
        for name in ("model.bin", "config.json", "shared_vocabulary.json", "sentencepiece.bpe.model"):
            raw = (kind + ":" + name).encode() * 256
            packed = zstandard.ZstdCompressor().compress(raw)
            url = f"https://example.test/{kind}-{name}.zst"
            payloads[url] = packed
            files.append({"name": name, "bytes": len(raw), "sha256": digest(raw), "url": url,
                          "compression": "zstd", "compressed_bytes": len(packed), "compressed_sha256": digest(packed)})
        models[kind] = {"files": files}
    catalog = {"models": models, "full_text": {}, "words": {
        "en-ja": "m2m", "es-en": "m2m", "ko-nl": "small", "ko-en": "small"}}
    monkeypatch.setattr(assets, "catalog", lambda: catalog)
    monkeypatch.setattr(assets, "settings_path", lambda: tmp_path / "LanguageLens/settings.json")
    requests = []
    def fetch(request, *, timeout):
        requests.append(request.full_url)
        return io.BytesIO(payloads[request.full_url])
    monkeypatch.setattr(assets, "urlopen", fetch)
    return catalog, payloads, requests


def test_selected_model_downloads_once_and_is_shared_across_pairs(downloads):
    catalog, _, requests = downloads
    progress = []
    assert not assets.ready("en", "ja")
    assert not requests  # Readiness checks never initiate downloads.
    paths = assets.prepare("en", "ja", lambda _: None, progress.append)
    assert len(paths) == 4 and assets.ready("en", "ja")
    assert requests == [item["url"] for item in catalog["models"]["m2m"]["files"]]
    assert not assets.model_path("small").exists()
    assert all(assets.valid(path, item) for path, item in assets.required_files("en", "ja"))
    assert progress[0].received == 0 and progress[-1].received == progress[-1].total
    assets.prepare("es", "en", lambda _: None, progress.append)
    assert len(requests) == 4 and assets.ready("es", "en")
    assert not list(assets.root().rglob("*.part")) and not list(assets.root().rglob("*.download"))


def test_argos_only_pair_does_not_download_word_weights(downloads):
    _, _, requests = downloads
    assert assets.prepare("en", "nl", lambda _: None, lambda _: None) == []
    assert not requests


@pytest.mark.parametrize("damage", ["transfer", "checksum", "decoded_size", "decoded_checksum", "not_zstd"])
def test_failed_download_preserves_existing_file_and_cleans_temporary_data(downloads, damage):
    catalog, payloads, _ = downloads
    item = catalog["models"]["small"]["files"][0]
    path = assets.model_path("small") / item["name"]
    path.parent.mkdir(parents=True)
    previous = b"previous model awaiting repair"
    path.write_bytes(previous)
    if damage == "transfer":
        payloads[item["url"]] = payloads[item["url"]][:-1]
    elif damage == "checksum":
        item["compressed_sha256"] = "0" * 64
    elif damage == "decoded_size":
        item["bytes"] -= 1
    elif damage == "decoded_checksum":
        item["sha256"] = "0" * 64
    else:
        payloads[item["url"]] = b"not a Zstandard frame"
        item["compressed_bytes"] = len(payloads[item["url"]])
        item["compressed_sha256"] = digest(payloads[item["url"]])
    with pytest.raises(KnownTaskError):
        assets.prepare("ko", "nl", lambda _: None, lambda _: None)
    assert path.read_bytes() == previous
    assert not assets.ready("ko", "nl")
    assert not list(assets.root().rglob("*.part")) and not list(assets.root().rglob("*.download"))


def test_existing_prepared_word_model_needs_no_network_after_update(downloads, monkeypatch):
    assets.prepare("ko", "nl", lambda _: None, lambda _: None)
    def no_network(*args, **kwargs):
        raise AssertionError("Already prepared weights must be reused")
    monkeypatch.setattr(assets, "urlopen", no_network)
    assert assets.ready("ko", "en")
    assets.prepare("ko", "en", lambda _: None, lambda _: None)


def test_t5_preparation_needs_no_firefox_or_node_runtime(downloads,monkeypatch):
    catalog, _, requests = downloads
    catalog['models']['t5']={**catalog['models']['small'],'kind':'t5'}
    catalog['full_text']['en-nl']={'model':'t5','pivot':None}
    assert not assets.ready('en','nl')
    paths=assets.prepare('en','nl',lambda _:None,lambda _:None)
    assert len(paths)==4 and len(requests)==4 and assets.ready('en','nl')
    assert not assets.needs_firefox('en','nl')
    assert not (assets.root()/'node_runtime').exists()
    from types import SimpleNamespace
    from language_lens.config import Settings
    from language_lens.services import local_files,offline,sentence_models
    monkeypatch.setattr(offline,'ocr_models',lambda _:[])
    monkeypatch.setattr(sentence_models,'model_root',lambda:assets.root()/'sentences')
    summary=local_files.pair_file_summary(Settings(source_language='en',target_language='nl'),
        SimpleNamespace(argos_required=lambda *_:False),[])
    assert {row['name'] for row in summary['files']}=={'t5','en · MiniSBD'}
