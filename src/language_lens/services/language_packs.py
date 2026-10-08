"""Pinned optional runtimes. Downloads happen only in explicit maintenance jobs."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import importlib
from importlib import metadata, resources
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import sys
import tarfile
import time
from urllib.request import urlopen
from uuid import uuid4
import zipfile

from filelock import FileLock

from language_lens.config import settings_path
from language_lens.runtime import frozen
from language_lens.services.errors import KnownTaskError
from language_lens.services.model_download import DownloadProgress


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(resources.files("language_lens").joinpath("data/language-packs.json").read_text("utf-8"))


def packs_root() -> Path:
    return settings_path().parent / "language-packs"


def text_pack(language: str) -> str | None:
    return {"ja": "ja-text", "zh": "zh-text"}.get(language)


def definition(pack: str) -> dict:
    if pack not in catalog()["packs"]:
        raise ValueError("Unknown language pack.")
    return catalog()["packs"][pack]


def artifacts(pack: str) -> list[dict]:
    python = f"cp{sys.version_info.major}{sys.version_info.minor}"
    try:
        return [catalog()["artifacts"][key.format(python=python)] for key in definition(pack)["artifacts"]]
    except KeyError:
        raise KnownTaskError("pack_platform") from None


def identity(pack: str) -> str:
    return hashlib.sha256(json.dumps(artifacts(pack), sort_keys=True).encode()).hexdigest()


def download_bytes(pack: str) -> int:
    return sum(item["bytes"] for item in artifacts(pack))


def _source_ready(pack: str) -> bool:
    if frozen():
        return False
    try:
        return all(metadata.version(item["distribution"]) == item["version"] for item in artifacts(pack))
    except metadata.PackageNotFoundError:
        return False


def _inside(root: Path, name: str) -> Path:
    # Archives, manifests and active pointers use the same strict path policy.
    parts = PurePosixPath(name).parts
    if (not parts or "\\" in name or ":" in name or name.startswith("/")
            or any(part in (".", "..") or part.endswith((".", " ")) for part in name.split("/"))):
        raise KnownTaskError("integrity")
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise KnownTaskError("integrity")
    return target


def _installed(pack: str, *, verify: bool = False) -> tuple[Path, dict] | None:
    definition(pack)
    root = packs_root()
    try:
        pointer = json.loads((root / f"{pack}.json").read_text("utf-8"))
        if pointer["identity"] != identity(pack):
            return None
        directory = _inside(root, pointer["directory"])
        if directory.parent != root or not directory.name.startswith(pack + "-"):
            return None
        manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
        if manifest["identity"] != pointer["identity"] or not manifest["files"]:
            return None
        for name, size, modified, digest in manifest["files"]:
            path = _inside(directory, name)
            info = path.stat()
            if not path.is_file() or (info.st_size, info.st_mtime_ns) != (size, modified):
                return None
            if verify and _hash(path) != digest:
                return None
        return directory, manifest
    except (OSError, ValueError, KeyError, TypeError, KnownTaskError):
        return None


def ready(pack: str) -> bool:
    return _installed(pack) is not None or _source_ready(pack)


def inventory() -> list[dict]:
    return [{"id": key, "name": definition(key)["name"], "bytes": download_bytes(key),
             "ready": ready(key), "managed": (packs_root() / f"{key}.json").exists()
             or any(packs_root().glob(key + "-*"))}
            for key in catalog()["packs"]]


_activated: dict[str, str] = {}


def activate(pack: str) -> None:
    installed = _installed(pack)
    if installed is None:
        if pack not in _activated and _source_ready(pack):
            return
        raise KnownTaskError("missing_pack")
    directory, _manifest = installed
    previous = _activated.get(pack)
    if previous and previous != str(directory):
        raise KnownTaskError("pack_restart")
    if previous:
        return
    if _installed(pack, verify=True) is None:
        raise KnownTaskError("integrity")
    if any(module in sys.modules for module in definition(pack)["modules"]):
        raise KnownTaskError("pack_restart")
    sys.path.insert(0, str(directory))
    importlib.invalidate_caches()
    _activated[pack] = str(directory)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract(archive: Path, item: dict, destination: Path) -> None:
    """Never run installers; retain package code, data and upstream notices."""
    total = 0
    seen = set()

    def copy(name, size, source):
        nonlocal total
        total += size
        if total > 1024**3 or len(seen) > 20000 or name.casefold() in seen:
            raise KnownTaskError("integrity")
        seen.add(name.casefold())
        target = _inside(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
        if target.stat().st_size != size:
            raise KnownTaskError("integrity")

    if item["format"] == "wheel":
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                _inside(destination, entry.filename.rstrip("/"))
                if stat.S_ISLNK(entry.external_attr >> 16):
                    raise KnownTaskError("integrity")
                if not entry.is_dir():
                    copy(entry.filename, entry.file_size, source.open(entry))
    else:
        # jieba publishes only an sdist. Extract its package and licence;
        # setup.py, tests and build scripts are deliberately never executed.
        with tarfile.open(archive, "r:gz") as source:
            for entry in source:
                _inside(destination, entry.name.rstrip("/"))
                if not (entry.isfile() or entry.isdir()):
                    raise KnownTaskError("integrity")
                parts = PurePosixPath(entry.name).parts[1:]
                if entry.isfile() and parts and (parts[0] == "jieba" or parts[-1] in ("LICENSE", "COPYING", "PKG-INFO")):
                    copy("/".join(parts), entry.size, source.extractfile(entry))


def _discard(path: Path) -> None:
    root = packs_root().resolve()
    if path.resolve().parent != root or path.is_symlink():
        raise KnownTaskError("integrity")
    # Loaded dictionaries/DLLs may be locked on Windows; retry next maintenance.
    shutil.rmtree(path, ignore_errors=True)


def _clean_orphans(pack: str, keep: Path | None = None) -> None:
    for path in packs_root().glob(pack + "-*"):
        if path.is_dir() and path != keep:
            _discard(path)


def install(pack: str, report=lambda _message: None, progress=lambda _event: None) -> None:
    items = artifacts(pack)
    if pack == "ja-speech" and (sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64")):
        if _source_ready(pack):
            return
        raise KnownTaskError("pack_platform")
    root = packs_root()
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / "maintenance.lock"), timeout=10):
        installed = _installed(pack, verify=True)
        if installed or _source_ready(pack):
            report(f"{definition(pack)['name']} verified.")
            if installed:
                _clean_orphans(pack, installed[0])
            return
        # Keep the old published installation until the replacement is complete.
        staging = root / f"{pack}-{uuid4().hex}"
        staging.mkdir()
        published = False
        try:
            total, completed = download_bytes(pack), 0
            for item in items:
                report(f"Downloading {definition(pack)['name']}…")
                archive = staging / "download.part"
                digest = hashlib.sha256()
                count, last = 0, 0.0
                progress(DownloadProgress(completed, total))
                with urlopen(item["url"], timeout=30) as response, archive.open("xb") as output:
                    while chunk := response.read(256 * 1024):
                        count += len(chunk)
                        if count > item["bytes"]:
                            raise KnownTaskError("integrity")
                        digest.update(chunk)
                        output.write(chunk)
                        if time.monotonic() - last > .15:
                            progress(DownloadProgress(completed + count, total))
                            last = time.monotonic()
                if count != item["bytes"] or digest.hexdigest() != item["sha256"]:
                    raise KnownTaskError("integrity")
                report(f"Verifying {definition(pack)['name']}…")
                _extract(archive, item, staging)
                archive.unlink()
                completed += count
                progress(DownloadProgress(completed, total))
            records = [(path.relative_to(staging).as_posix(), path.stat().st_size,
                        path.stat().st_mtime_ns, _hash(path))
                       for path in sorted(staging.rglob("*")) if path.is_file()]
            stamp = identity(pack)
            (staging / "manifest.json").write_text(json.dumps({"identity": stamp, "files": records}), "utf-8")
            pointer = root / f"{pack}.tmp"
            pointer.write_text(json.dumps({"identity": stamp, "directory": staging.name}), "utf-8")
            os.replace(pointer, root / f"{pack}.json")
            published = True
            _clean_orphans(pack, staging)
            report(f"{definition(pack)['name']} installed for offline use.")
        finally:
            if not published:
                _discard(staging)


def remove(pack: str) -> None:
    definition(pack)
    root = packs_root()
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / "maintenance.lock"), timeout=10):
        (root / f"{pack}.json").unlink(missing_ok=True)
        _clean_orphans(pack)
