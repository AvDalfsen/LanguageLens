"""Validate and stage Argos archives before publishing; retain removed models."""
from pathlib import Path
import json
import os
import shutil
import stat
import tempfile
from uuid import uuid4
import zipfile

from language_lens.services.offline import marker_path
from language_lens.services.errors import KnownTaskError


class InvalidModelArchive(KnownTaskError, ValueError):
    def __init__(self, message):
        super().__init__("integrity", message)


def _not_link(path: Path) -> None:
    # Python 3.10 has no Path.is_junction(); reject Windows reparse points too.
    try:
        attributes = path.lstat()
    except FileNotFoundError:
        return
    if path.is_symlink() or getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError("Model management paths must not be links or junctions.")


def _owned_directory(path: Path) -> Path:
    _not_link(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _leaf(value: str) -> str:
    if (not isinstance(value, str) or not value or Path(value).name != value
            or value in (".", "..") or any(c in value for c in "\\/:")):
        raise ValueError("Invalid model recovery journal.")
    return value


def _write_journal(journal: Path, record: dict) -> None:
    draft = journal.with_suffix(".tmp")
    try:
        with draft.open("w", encoding="utf-8") as handle:
            json.dump(record, handle)
            handle.flush()
            os.fsync(handle.fileno())
        draft.replace(journal)
    finally:
        draft.unlink(missing_ok=True)


def _recover_record(root: Path, record: dict) -> None:
    removed = root.parent / "language-lens-removed-models"
    _not_link(removed)
    destination = root / _leaf(record["destination"])
    _not_link(destination)
    if record.get("version") != 2:
        # Read journals left by earlier versions of Lens.
        backup = removed / _leaf(record["backup"])
        _not_link(backup)
        if not destination.exists() and backup.is_dir():
            backup.replace(destination)
        if not destination.is_dir():
            raise ValueError("Model recovery is incomplete; keep the journal and check the backup directory.")
        return
    phase = record["phase"]
    if phase not in ("retiring", "publishing", "committed"):
        raise ValueError("Invalid model recovery journal.")
    entries = record["backups"]
    if not isinstance(entries, list):
        raise ValueError("Invalid model recovery journal.")
    pairs = [(root / _leaf(item["original"]), removed / _leaf(item["backup"])) for item in entries]
    if len({path for path, _ in pairs}) != len(pairs) or len({path for _, path in pairs}) != len(pairs):
        raise ValueError("Invalid model recovery journal.")
    for original, backup in pairs:
        _not_link(original)
        _not_link(backup)
    if phase == "committed" and destination.is_dir():
        return
    # A publish without a durable commit is rolled back as a whole. Preserve
    # the new package as well; no model is deleted during recovery.
    if phase != "retiring" and destination.exists():
        retire(destination, root)
    for original, backup in pairs:
        if backup.is_dir():
            if original.exists():
                raise ValueError("Model recovery would overwrite another package; keep the journal.")
            backup.replace(original)
        elif not original.is_dir():
            raise ValueError("Model recovery is incomplete; keep the journal and check the backup directory.")


def _package_identity(path: Path) -> tuple[str, str] | None:
    metadata = path / "metadata.json"
    _not_link(metadata)
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, UnicodeError):
        return None  # a damaged package can still be replaced by its exact name
    if (isinstance(data, dict) and isinstance(data.get("from_code"), str) and data["from_code"]
            and isinstance(data.get("to_code"), str) and data["to_code"]):
        return data["from_code"], data["to_code"]
    return None


def _matching_packages(root: Path, identities: set[tuple[str, str]]) -> list[Path]:
    matches = []
    for path in sorted(root.iterdir()):
        _not_link(path)
        if path.is_dir() and _package_identity(path) in identities:
            matches.append(path)
    return matches


def validate_staged_model(path: Path, package, expected: tuple[str, str] | None = None):
    """Load tokenizer and weights before retiring any active package.

    This runs inside the disposable model worker, with outbound connections
    disabled. Direct inference avoids downloading sentence models at preflight.
    """
    from language_lens.services.offline import no_network
    with no_network():
        model = package.Package(path)
        identity = (model.from_code, model.to_code)
        if not all(isinstance(code, str) and code for code in identity) or (expected and identity != expected):
            raise ValueError("The archive does not contain the requested translation model.")
        if not hasattr(model, "tokenizer") or not (path / "model" / "model.bin").is_file():
            raise ValueError("Translation model weights or tokenizer are missing.")
        from language_lens.services.voices import selected_voice
        voice = selected_voice(model.from_code, {})
        sample = voice.sample if voice else "Hello."
        tokens = model.tokenizer.encode(sample)
        if not tokens:
            raise ValueError("The translation tokenizer returned no input.")
        import ctranslate2
        runtime = ctranslate2.Translator(str(path / "model"), device="cpu", intra_threads=2, inter_threads=1)
        try:
            prefix = getattr(model, "target_prefix", "")
            request = {"target_prefix": [[prefix]]} if prefix else {}
            result = runtime.translate_batch([tokens], beam_size=1, num_hypotheses=1, **request)
            output = model.tokenizer.decode(result[0].hypotheses[0]).strip() if result and result[0].hypotheses else ""
            if prefix and output.startswith(prefix):
                output = output[len(prefix):].strip()
            if not output:
                raise ValueError("The staged translation model returned no output.")
        finally:
            # Release native handles on failure too, before staging cleanup.
            del runtime
    return model


def recover_transactions(root: Path) -> None:
    """Restore the old package if a worker died between the two publish renames.

    Called under the model-action file lock, never by a passive status check.
    Journals contain only validated leaf names, not arbitrary filesystem paths.
    """
    _not_link(root)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    journals = root.parent / "language-lens-model-transactions"
    _not_link(journals)
    removed = root.parent / "language-lens-removed-models"
    _not_link(removed)
    for journal in journals.glob("*.json"):
        _not_link(journal)
        record = json.loads(journal.read_text(encoding="utf-8"))
        _recover_record(root, record)
        journal.unlink()
    staging = root.parent / "language-lens-model-staging"
    _not_link(staging)
    if staging.exists():
        for directory in staging.iterdir():
            # The action lock ensures no current extraction owns these folders.
            _not_link(directory)
            if (directory.name.startswith("install-") and directory.is_dir()
                    and not directory.is_symlink() and directory.resolve().parent == staging.resolve()):
                shutil.rmtree(directory)


def install_archive(archive_path, package, *, expected: tuple[str, str] | None = None):
    root = Path(package.settings.package_data_dir)
    _not_link(root)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Same-volume staging permits an atomic directory rename. A cancelled
    # extraction never becomes visible as an installed Argos package.
    staging = _owned_directory(root.parent / "language-lens-model-staging")
    with tempfile.TemporaryDirectory(prefix="install-", dir=staging) as temporary:
        stage = Path(temporary).resolve()
        with zipfile.ZipFile(archive_path) as archive:
            for item in archive.infolist():
                target = (stage / item.filename).resolve()
                if not target.is_relative_to(stage) or "\\" in item.filename:
                    raise InvalidModelArchive("Unsafe archive member.")
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise InvalidModelArchive("Symbolic links are not accepted in model archives.")
            archive.extractall(stage)
        folders = list(stage.iterdir())
        if len(folders) != 1 or not folders[0].is_dir():
            raise InvalidModelArchive("The archive must contain one model directory.")
        if not (folders[0] / "model").is_dir() or not (folders[0] / "metadata.json").is_file():
            raise InvalidModelArchive("Translation model files are missing.")
        try:
            model = validate_staged_model(folders[0], package, expected)
        except (ImportError, PermissionError):
            raise
        except Exception as exc:
            raise InvalidModelArchive("The staged translation weights or tokenizer could not be validated.") from exc
        destination = root / folders[0].name
        _not_link(destination)
        old = _matching_packages(root, {(model.from_code, model.to_code)})
        if destination.exists() and destination not in old:
            if not destination.is_dir() or _package_identity(destination) is not None:
                raise InvalidModelArchive("The archive folder collides with a different installed package.")
            old.append(destination)
        removed = _owned_directory(root.parent / "language-lens-removed-models")
        journals = _owned_directory(root.parent / "language-lens-model-transactions")
        journal = journals / f"{uuid4().hex}.json"
        record = {"version": 2, "destination": destination.name, "phase": "retiring",
                  "backups": [{"original": path.name, "backup": f"{path.name}-{uuid4().hex}"} for path in old]}
        _write_journal(journal, record)
        try:
            for item in record["backups"]:
                (root / item["original"]).replace(removed / item["backup"])
            record["phase"] = "publishing"
            _write_journal(journal, record)
            folders[0].replace(destination)
            record["phase"] = "committed"
            _write_journal(journal, record)
        except OSError:
            # Use the last durable phase, not an in-memory draft that failed.
            _recover_record(root, json.loads(journal.read_text(encoding="utf-8")))
            journal.unlink()
            raise
        journal.unlink()


def retire(path: Path, root: Path) -> Path:
    _not_link(path)
    _not_link(root)
    path, root = path.resolve(), root.resolve()
    if path.parent != root or not path.is_dir() or path.is_symlink():
        raise ValueError("Model directory is outside the installed package root.")
    # Keep backup on the same volume, outside Argos's installed-package scan.
    removed = _owned_directory(root.parent / "language-lens-removed-models")
    destination = removed / f"{path.name}-{uuid4().hex}"
    path.replace(destination)
    return destination


def remove_route(source, target, report):
    from language_lens.services.translation import ArgosTranslator
    translator = ArgosTranslator()
    package, backend = translator._modules()
    packages = translator.route(source, target)
    root = Path(package.settings.package_data_dir)
    _not_link(root)
    identities = {(item.from_code, item.to_code) for item in packages}
    paths = set(_matching_packages(root, identities)) | {Path(item.package_path) for item in packages}
    for path in sorted(paths):
        destination = retire(path, root)
        report(f"Model moved to recoverable backup: {destination.name}")
    backend.get_installed_languages.cache_clear()
    cached = getattr(backend, "installed_translates", None)
    if cached is not None:
        cached.clear()
    translator.translate.cache_clear()
    translator.word_candidates.cache_clear()
    marker_path(source, target).unlink(missing_ok=True)
