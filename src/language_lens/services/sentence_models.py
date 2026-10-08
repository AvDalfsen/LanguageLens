"""Explicit, checksummed MiniSBD preparation; inference accepts local paths only."""
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
import time
from urllib.request import urlopen

from filelock import FileLock

from language_lens.config import settings_path
from language_lens.services.errors import KnownTaskError
from language_lens.services.model_download import DownloadProgress
from language_lens.services.voices import valid_file

BACKEND_ID = "minisbd-0.9.5-lens-v1"


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files("language_lens").joinpath("data/sentence-models.json").read_text("utf-8"))


def model_code(language):
    try:
        return catalog()["languages"][language]
    except KeyError:
        # Do not silently split an unsupported language with an English model.
        raise KnownTaskError("sentence_language") from None


def model_root():
    return settings_path().parent / "offline" / "sentences"


def model_path(language):
    code = model_code(language)
    item = catalog()["models"][code]
    return model_root() / f"{code}-{item['sha256'][:16]}.onnx"


def identities(languages):
    return {model_code(language): catalog()["models"][model_code(language)]["sha256"]
            for language in languages}


def compatible(records):
    return isinstance(records, dict) and all(catalog()["models"].get(code, {}).get("sha256") == digest
                                            for code, digest in records.items())


def verified_path(language):
    item = catalog()["models"][model_code(language)]
    path = model_path(language)
    if not valid_file(path, item["bytes"], item["sha256"]):
        raise KnownTaskError("missing_assets")
    return path


def prepare(languages, report, progress):
    """One shared model per source/pivot language, never per translation pair."""
    languages = list(dict.fromkeys(languages))
    by_code = {model_code(language): language for language in languages}
    if not by_code:
        return []
    root = model_root()
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    with FileLock(str(root / "download.lock"), timeout=10):
        for code, language in by_code.items():
            path = model_path(language)
            item = catalog()["models"][code]
            report(f"Checking {code} sentence model…")
            if not valid_file(path, item["bytes"], item["sha256"]):
                temporary = path.with_suffix(".part")
                try:
                    report(f"Downloading {code} sentence model…")
                    received, last = 0, 0.0
                    digest = hashlib.sha256()
                    progress(DownloadProgress(0, item["bytes"]))
                    with urlopen(item["url"], timeout=30) as response, temporary.open("wb") as output:
                        while chunk := response.read(64 * 1024):
                            received += len(chunk)
                            if received > item["bytes"]:
                                raise KnownTaskError("integrity")
                            digest.update(chunk)
                            output.write(chunk)
                            if time.monotonic() - last >= .15:
                                progress(DownloadProgress(received, item["bytes"]))
                                last = time.monotonic()
                    if received != item["bytes"] or digest.hexdigest() != item["sha256"]:
                        raise KnownTaskError("integrity")
                    temporary.replace(path)
                    progress(DownloadProgress(received, item["bytes"]))
                finally:
                    temporary.unlink(missing_ok=True)
            paths.append(path)
    return paths


@lru_cache(maxsize=4)
def _detector(path, size, modified):
    from minisbd import SBDetect
    return SBDetect(path, use_gpu=False, max_threads=2)


def split(text, language):
    if not text.strip():
        return []
    path = verified_path(language)
    info = path.stat()
    detector = _detector(str(path), info.st_size, info.st_mtime_ns)
    sentences = detector.sentences(text)
    # Never silently discard recognized characters on a frontend failure.
    compact = lambda value: "".join(value.split())
    if not sentences or compact("".join(sentences)) != compact(text):
        raise KnownTaskError("sentence_split")
    return sentences
