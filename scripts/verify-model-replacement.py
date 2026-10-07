"""Opt-in preflight/publication check using copies of a real Argos model."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True, help="An existing installed Argos package directory.")
    args = parser.parse_args()
    source = args.model.resolve()
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    identity = (metadata["from_code"], metadata["to_code"])
    artifacts = Path(__file__).resolve().parents[1] / "artifacts" / "model-replacement-validation"
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=artifacts) as temporary:
        root = Path(temporary)
        packages = root / "packages"
        os.environ.update(LOCALAPPDATA=str(root / "app"), XDG_DATA_HOME=str(root / "data"),
            XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
            ARGOS_PACKAGES_DIR=str(packages))
        from language_lens.services.translation import ArgosTranslator
        from language_lens.services.model_management import install_archive, InvalidModelArchive, remove_route, validate_staged_model
        from language_lens.services.offline import no_network
        def copy_file(original, destination):
            try:
                os.link(original, destination)
            except OSError:
                shutil.copy2(original, destination)
            return destination
        old = packages / source.name
        shutil.copytree(source, old, copy_function=copy_file)
        with no_network():
            translator = ArgosTranslator()
            package, backend = translator._modules()
            assert Path(package.settings.package_data_dir) == packages
            validate_staged_model(old, package, identity)
            assert translator.route(*identity)[0].package_path == old
            broken = root / "broken.argosmodel"
            with zipfile.ZipFile(broken, "w") as archive:
                archive.writestr(source.name + "/metadata.json", json.dumps(metadata))
                archive.writestr(source.name + "/model/", "")
            try:
                install_archive(broken, package, expected=identity)
            except InvalidModelArchive:
                pass
            else:
                raise AssertionError("Broken archive was published")
            assert old.is_dir() and (old / "model" / "model.bin").is_file()
            print("PASS broken replacement retained the working model", flush=True)
            archive_path = root / "verified.argosmodel"
            name = source.name + "-verified"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        archive.write(path, str(Path(name) / path.relative_to(source)))
            install_archive(archive_path, package, expected=identity)
            backend.get_installed_languages.cache_clear()
            backend.installed_translates.clear()
            assert not old.exists()
            assert translator.route(*identity)[0].package_path == packages / name
            validate_staged_model(packages / name, package, identity)
            print("PASS real staged inference and versioned replacement selected the new directory", flush=True)
            remove_route(*identity, report=lambda _: None)
            assert not translator.is_pair_installed(*identity)
            backups = list((root / "language-lens-removed-models").iterdir())
            assert len(backups) == 2 and all((path / "model" / "model.bin").is_file() for path in backups)
            print("PASS removal left no active route and retained both recoverable models", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
