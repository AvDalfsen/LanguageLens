"""Stream Argos models into their normal cache with observable byte progress."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import time
from http.client import HTTPException
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4
import zipfile
import zlib

from language_lens.config import settings_path


def configure_cache(package, scratch: Path) -> None:
    """Persist completed archives; keep interrupted transfers in the job directory."""
    package.settings.downloads_dir = settings_path().parent / "model-cache"
    package.settings.language_lens_download_scratch = scratch / "downloads"


def _prune_cache(directory: Path, keep: Path, limit: int = 2 * 1024**3) -> None:
    archives = []
    for path in directory.glob("*.argosmodel"):
        try:
            info = path.stat()
            archives.append((info.st_mtime, info.st_size, path))
        except OSError:
            continue
    total = sum(size for _, size, _ in archives)
    for _, size, path in sorted(archives):
        if total <= limit:
            break
        if path != keep:
            try:
                path.unlink()
            except OSError:
                continue  # retention must not invalidate a completed download
            total -= size


@dataclass(frozen=True)
class DownloadProgress:
    received: int
    total: int | None
    timestamp: float = field(default_factory=time.monotonic)


def valid_archive(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return bool(archive.namelist()) and archive.testzip() is None
    except (OSError, zipfile.BadZipFile, EOFError, RuntimeError, zlib.error):
        return False


def download_model(model, package, label: str, report: Callable[[str], None],
                   progress: Callable[[DownloadProgress], None] | None = None) -> Path:
    """Keep Argos cache compatibility; never publish a partial download.

    Content-Length supplies the total where available. When absent, report bytes
    without inventing a percentage. Try each supported mirror twice and reset
    its progress visibly on retry. All network work runs in the install worker.
    """
    notify = progress or (lambda _event: None)
    name = package.argospm_package_name(model) + ".argosmodel"
    if Path(name).name != name or "\\" in name:
        raise ValueError("The model index contains an invalid package filename.")
    managed = hasattr(package.settings, "language_lens_download_scratch")
    if managed:
        identity = {key: getattr(model, key, None) for key in ("from_code", "to_code", "package_version", "links")}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        name = f"{Path(name).stem}-{digest}.argosmodel"
    directory = Path(package.settings.downloads_dir)
    directory.mkdir(parents=True, exist_ok=True)
    partials = Path(package.settings.language_lens_download_scratch) if managed else directory
    partials.mkdir(parents=True, exist_ok=True)
    destination = directory / name
    if destination.exists():
        report(f"Checking cached {label}…")
        if valid_archive(destination):
            if managed:
                destination.touch()
                _prune_cache(directory, destination)
            return destination

    links = [url for url in model.links if urlparse(url).scheme in ("http", "https")]
    if not links:
        raise ValueError(f"No supported download link is available for {label}.")
    last_error: Exception | None = None
    attempts = len(links) * 2
    for attempt, url in enumerate((url for url in links for _ in range(2)), 1):
        suffix = f" (attempt {attempt}/{attempts})" if attempt > 1 else ""
        report(f"Downloading {label}{suffix}…")
        temporary = partials / f".{name}.{uuid4().hex}.part"
        try:
            request = Request(url, headers={"User-Agent": "ArgosTranslate", "Accept-Encoding": "identity"})
            with urlopen(request, timeout=30) as response, temporary.open("xb") as output:
                try:
                    size = int(response.headers.get("Content-Length", ""))
                    total = size if size > 0 else None
                except (TypeError, ValueError):
                    total = None
                received = 0
                notify(DownloadProgress(received, total))
                last_report = time.monotonic()
                # read1 returns available data, including partial chunks on slow links.
                read = getattr(response, "read1", response.read)
                while chunk := read(64 * 1024):
                    output.write(chunk)
                    received += len(chunk)
                    now = time.monotonic()
                    if now - last_report >= .15:
                        notify(DownloadProgress(received, total, now))
                        last_report = now
                if total is not None and received != total:
                    raise ValueError(f"Incomplete model download ({received:,} of {total:,} bytes).")
                notify(DownloadProgress(received, total))
            report(f"Checking downloaded {label}…")
            if not valid_archive(temporary):
                raise ValueError("The downloaded model archive is incomplete or damaged.")
            temporary.replace(destination)
            if managed:
                _prune_cache(directory, destination)
            return destination
        except (OSError, ValueError, EOFError, HTTPException) as exc:
            last_error = exc
        finally:
            temporary.unlink(missing_ok=True)
    raise RuntimeError(f"Could not download {label} after {attempts} attempts: {last_error}") from last_error
