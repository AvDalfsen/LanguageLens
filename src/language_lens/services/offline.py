"""Explicit asset preparation; capture workers never have network permission."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import shutil
import socket
from urllib.request import urlopen

from language_lens.config import settings_path
from language_lens.services.errors import KnownTaskError


def assets_root() -> Path:
    return settings_path().parent / "offline"


@contextmanager
def no_network():
    """Only use in a disposable worker, never monkeypatch the GUI process."""
    def denied(*_args, **_kwargs):
        raise RuntimeError("Network access is disabled during capture. Use 'Download required files' or 'Check required files' in 'Settings'.")
    connect, connect_ex, create = socket.socket.connect, socket.socket.connect_ex, socket.create_connection
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = denied
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = connect, connect_ex, create


def ocr_parameters(language: str) -> dict:
    from rapidocr import LangRec, ModelType, OCRVersion
    from language_lens.services.ocr import SCRIPT_BY_LANGUAGE
    return {"Rec.lang_type": getattr(LangRec, SCRIPT_BY_LANGUAGE.get(language, "LATIN")),
            "Rec.model_type": ModelType.MOBILE, "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Global.text_score": .35, "Global.log_level": "critical",
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1}


def ocr_models(language: str) -> list[tuple[str, Path, str, str, Path]]:
    from rapidocr.main import DEFAULT_CFG_PATH, root_dir
    from rapidocr.utils.parse_parameters import ParseParams
    from rapidocr.inference_engine.base import FileInfo, InferSession
    cfg = ParseParams.update_batch(ParseParams.load(DEFAULT_CFG_PATH), ocr_parameters(language))
    result = []
    for section in ("Det", "Cls", "Rec"):
        item = cfg[section]
        info = InferSession.get_model_url(FileInfo(item.engine_type, item.ocr_version,
                   item.task_type, item.lang_type, item.model_type))
        name = Path(info["model_dir"]).name
        result.append((section, assets_root() / "ocr" / name, info["model_dir"],
                       info["SHA256"], root_dir / "models" / name))
    return result


def matches(path: Path, digest: str) -> bool:
    try:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest().lower() == digest.lower()
    except OSError:
        return False


def local_ocr_parameters(language: str) -> dict:
    params = ocr_parameters(language)
    for section, path, _url, digest, _existing in ocr_models(language):
        if not matches(path, digest):
            raise KnownTaskError("missing_assets")
        params[f"{section}.model_path"] = str(path)
    return params


def marker_path(source: str, target: str) -> Path:
    # Language codes come from validated Settings, not arbitrary paths.
    if not all(code.isalpha() and len(code) <= 8 for code in (source, target)):
        raise ValueError("Invalid language code.")
    return assets_root() / f"{source}-{target}.json"


def runtime_identity() -> dict:
    identity = {}
    for name in ("rapidocr", "onnxruntime", "argostranslate", "ctranslate2", "sentencepiece", "sacremoses",
                 "minisbd", "regex"):
        try:
            identity[name] = version(name)
        except PackageNotFoundError:
            identity[name] = "missing"
    from language_lens.services.sentence_models import BACKEND_ID
    identity["sentence_backend"] = BACKEND_ID
    return identity


def offline_ready(source: str, target: str) -> bool:
    from language_lens.services import language_packs as packs
    required = packs.text_pack(source)
    if required and not packs.ready(required):
        return False
    try:
        records = json.loads(marker_path(source, target).read_text(encoding="utf-8"))
        from language_lens.services import sentence_models
        if not sentence_models.compatible(records["sentence_models"]):
            return False
        if required and records.get("language_pack") != packs.identity(required):
            return False
        if records["version"] != 2 or records["runtime"] != runtime_identity() or not records["files"]:
            return False
        for name, size, modified in records["files"]:
            stat = Path(name).stat()
            if (stat.st_size, stat.st_mtime_ns) != (size, modified):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def prepare(source: str, target: str, report, progress) -> None:
    from language_lens.services import language_packs as packs
    required = packs.text_pack(source)
    if required:
        packs.install(required, report, progress)
        packs.activate(required)
    from language_lens.services.translation import ArgosTranslator
    from language_lens.services.model_download import DownloadProgress
    translator = ArgosTranslator()
    if not translator.is_pair_installed(source, target):
        translator.install_pair(source, target, report, progress, staged=True)
    paths = []
    for section, path, url, digest, existing in ocr_models(source):
        report(f"Preparing OCR {section.lower()} model…")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not matches(path, digest):
            temporary = path.with_suffix(".part")
            try:
                if matches(existing, digest):
                    shutil.copyfile(existing, temporary)
                else:
                    with urlopen(url, timeout=30) as response, temporary.open("wb") as handle:
                        total = int(response.headers.get("Content-Length", 0)) or None
                        done = 0
                        progress(DownloadProgress(done, total))
                        while chunk := response.read(64 * 1024):
                            handle.write(chunk)
                            done += len(chunk)
                            progress(DownloadProgress(done, total))
                if not matches(temporary, digest):
                    raise KnownTaskError("integrity")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        paths.append(path)
    from language_lens.services import sentence_models
    sentence_languages = [item.from_code for item in translator.route(source, target)]
    paths.extend(sentence_models.prepare(sentence_languages, report, progress))
    # All inference, including the fixed warmup sample, is now offline.
    from language_lens.services.voices import selected_voice
    voice = selected_voice(source, {})
    sample = voice.sample if voice else "Hello."
    report("Verifying OCR and translation with networking disabled…")
    _package, backend = translator._modules()
    backend.get_installed_languages.cache_clear()
    backend.installed_translates.clear()
    with no_network():
        from language_lens.text import word_spans
        list(word_spans(sample, source))
        from language_lens.services.ocr import RapidOcrEngine
        import numpy as np
        engine = RapidOcrEngine(source, params=local_ocr_parameters(source))
        engine.recognize(np.full((64, 256, 3), 255, dtype=np.uint8))
        translator.translate.cache_clear()
        translator.translate(sample, source, target)
        translator.word_candidates(sample.split()[0], source, target)
    for package in translator.route(source, target):
        paths.extend(path for path in package.package_path.rglob("*") if path.is_file()
                     and path.relative_to(package.package_path).parts[0] not in ("stanza", "minisbd"))
    records = {"version": 2, "runtime": runtime_identity(), "sentence_models": sentence_models.identities(sentence_languages),
               "files": [(str(path), path.stat().st_size, path.stat().st_mtime_ns)
                                       for path in sorted(set(paths))]}
    if required:
        records["language_pack"] = packs.identity(required)
    marker = marker_path(source, target)
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(records), encoding="utf-8")
    temporary.replace(marker)
    report("OCR and translation verified for offline use. Voices are separate downloads.")
