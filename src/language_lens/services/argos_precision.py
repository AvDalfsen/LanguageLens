"""Package-scoped computation repair for the pinned Spanish-English model."""
from functools import lru_cache
import hashlib
from pathlib import Path


POLICY_ID = "es-en-1.9-float32-v1"
MODEL_SHA256 = "3c634f2fbfce11ba9c3db839db50079c08d3cdb12c74f2c21671f742dbbb30f1"


@lru_cache(maxsize=8)
def _model_matches(path, size, modified):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == MODEL_SHA256


def prepare_translation(translation):
    """Prepare only the affected leg, including inside Argos caches/pivots.

    Call under the Argos translation lock, before any hypothesis lookup.
    Other package versions/weights retain their existing computation settings.
    """
    if hasattr(translation, "underlying"):
        changed = prepare_translation(translation.underlying)
        if changed:
            translation.cache.clear()
        return changed
    if hasattr(translation, "t1"):
        first = prepare_translation(translation.t1)
        second = prepare_translation(translation.t2)
        return first or second
    package = getattr(translation, "pkg", None)
    if (package is None or package.from_code != "es" or package.to_code != "en"
            or str(package.package_version) != "1.9"
            or getattr(translation, "_lens_precision_policy", None) == POLICY_ID):
        return False
    model = package.package_path / "model" / "model.bin"
    info = model.stat()
    if not _model_matches(str(model.resolve()), info.st_size, info.st_mtime_ns):
        return False
    import ctranslate2
    backend = ctranslate2.Translator(str(model.parent), device="cpu", inter_threads=1,
                                    intra_threads=2, compute_type="float32")
    previous = translation.translator
    if previous is not None:
        previous.unload_model()
    translation.translator = backend
    translation._lens_precision_policy = POLICY_ID
    return True
