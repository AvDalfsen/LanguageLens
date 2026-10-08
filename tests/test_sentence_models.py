import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from language_lens.config import LANGUAGES
from language_lens.services import sentence_models as models
from language_lens.services.errors import KnownTaskError


def test_all_language_choices_have_explicit_models_and_portuguese_is_shared():
    assert set(models.catalog()["languages"]) == {code for _name, code in LANGUAGES}
    assert models.model_path("pb") == models.model_path("pt")
    assert models.model_code("zh") == "zh-hans"
    with pytest.raises(KnownTaskError, match="sentence_language"):
        models.model_code("unsupported")


@pytest.fixture
def storage(tmp_path, monkeypatch):
    payload = b"test-model-content"
    item = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "url": "https://example.invalid/en.onnx"}
    catalog = {"languages": {"en": "en", "pt": "en", "pb": "en"}, "models": {"en": item}}
    monkeypatch.setattr(models, "catalog", lambda: catalog)
    monkeypatch.setattr(models, "model_root", lambda: tmp_path)
    monkeypatch.setattr(models, "urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))
    return payload


def test_explicit_prepare_verifies_and_reuses_shared_model(storage, monkeypatch):
    calls = []
    paths = models.prepare(["pt", "pb", "en"], lambda _message: None, calls.append)
    assert len(paths) == 1
    assert paths[0].read_bytes() == storage
    assert calls[-1].received == calls[-1].total == len(storage)
    def forbidden(*_args, **_kwargs):
        pytest.fail("Verified models must be reused without network access")
    monkeypatch.setattr(models, "urlopen", forbidden)
    models.prepare(["pt", "pb"], lambda _message: None, calls.append)
    assert models.verified_path("en") == paths[0]


@pytest.mark.parametrize("payload", [b"truncated", b"x" * 18, b"x" * 1000])
def test_bad_download_does_not_publish_model(storage, monkeypatch, payload):
    monkeypatch.setattr(models, "urlopen", lambda *_args, **_kwargs: io.BytesIO(payload))
    with pytest.raises(KnownTaskError, match="integrity"):
        models.prepare(["en"], lambda _message: None, lambda _item: None)
    assert not models.model_path("en").exists()
    assert not list(models.model_root().glob("*.part"))


def test_missing_model_cannot_trigger_implicit_minisbd_download(storage, monkeypatch):
    monkeypatch.setattr(models, "_detector", lambda *_args: pytest.fail("Detector must not see a missing path"))
    with pytest.raises(KnownTaskError, match="missing_assets"):
        models.split("Hello.", "en")


def test_corrupted_model_is_rejected_even_with_same_size_and_mtime(storage):
    models.prepare(["en"], lambda _message: None, lambda _item: None)
    path = models.model_path("en")
    info = path.stat()
    path.write_bytes(b"x" * info.st_size)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
    with pytest.raises(KnownTaskError, match="missing_assets"):
        models.verified_path("en")


def test_sentence_splitter_must_preserve_every_nonspace_character(storage, monkeypatch):
    models.prepare(["en"], lambda _message: None, lambda _item: None)
    monkeypatch.setattr(models, "_detector", lambda *_args: SimpleNamespace(sentences=lambda _text: ["Hello."]))
    with pytest.raises(KnownTaskError, match="sentence_split"):
        models.split("Hello. Goodbye!", "en")
    assert models.split("\n \t", "en") == []


def test_backend_initializes_with_heavy_imports_blocked(tmp_path):
    # A fresh interpreter proves absence, even though development has Torch installed.
    code = '''
import importlib.abc, sys
class BlockHeavy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'stanza', 'torch', 'spacy'}:
            raise AssertionError('Heavy import attempted: ' + fullname)
sys.meta_path.insert(0, BlockHeavy())
from language_lens.services.translation import ArgosTranslator
from language_lens.services.argos_sentences import MiniSBDSentencizer
from types import SimpleNamespace
package, backend = ArgosTranslator._modules()
assert package.settings.chunk_type == package.settings.ChunkType.MINISBD
assert backend.get_installed_languages() == []
translation = backend.PackageTranslation(None, None, SimpleNamespace(from_code='pt'))
assert isinstance(translation.sentencizer, MiniSBDSentencizer)
print('ok')
'''
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path), XDG_DATA_HOME=str(tmp_path / "data"),
               XDG_CONFIG_HOME=str(tmp_path / "config"), XDG_CACHE_HOME=str(tmp_path / "cache"),
               ARGOS_PACKAGES_DIR=str(tmp_path / "packages"), ARGOS_CHUNK_TYPE="STANZA")
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_catalog_upgrade_only_invalidates_records_for_changed_models(monkeypatch):
    records = models.identities(["en", "pt"])
    assert models.compatible(records)
    original = models.catalog()
    catalog = json.loads(json.dumps(original))
    monkeypatch.setattr(models, "catalog", lambda: catalog)
    catalog["models"]["ja"]["sha256"] = "changed"
    assert models.compatible(records)
    catalog["models"]["pt"]["sha256"] = "changed"
    assert not models.compatible(records)
