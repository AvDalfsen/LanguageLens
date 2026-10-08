"""Collect dependency notices, inventory the portable bundle, and create its ZIP."""
import argparse
from collections import defaultdict
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import shutil
import sys
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def runtime_distributions():
    pending, found = ["language-lens"], {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found:
            continue
        dist = metadata.distribution(name)
        found[name] = dist
        for raw in dist.requires or []:
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle, output = args.bundle.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    project = Path(__file__).resolve().parents[1]
    for source, name in ((project / "LICENSE", "LICENSE"),
                         (project / "THIRD_PARTY_SPEECH.md", "THIRD_PARTY_SPEECH.md"),
                         (project / "packaging/README-portable.txt", "README.txt")):
        shutil.copy2(source, bundle / name)
    notices = bundle / "notices"
    notices.mkdir(exist_ok=True)
    distributions, baseline_files, inventory = runtime_distributions(), set(), []
    # The PyInstaller bootloader/runtime hooks are shipped even though the build
    # tool itself is not an application dependency.
    notice_distributions = {**distributions, "pyinstaller": metadata.distribution("pyinstaller")}
    for name, dist in sorted(notice_distributions.items()):
        inventory.append({"name": name, "version": dist.version,
                          "license_expression": dist.metadata.get("License-Expression"),
                          "project_urls": dist.metadata.get_all("Project-URL") or []})
        for file in dist.files or []:
            source = Path(dist.locate_file(file)).resolve()
            if source.is_file() and name in distributions:
                baseline_files.add(source)
            if not source.is_file() or not any(word in file.name.lower() for word in ("license", "copying", "notice", "copyright")):
                continue
            # Distribution records can contain ../Scripts entries. Copy only
            # notice files whose relative paths stay inside their own package.
            if file.is_absolute() or ".." in file.parts:
                continue
            target = notices / name / file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("The build interpreter's LICENSE.txt could not be found")
    shutil.copy2(python_license, notices / "Python-LICENSE.txt")
    (notices / "dependencies.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (notices / "README.txt").write_text(
        "Notices from the installed runtime dependency closure are retained here, including packages "
        "whose code is excluded from the portable bundle. Consult THIRD_PARTY_SPEECH.md for speech "
        "runtime and model provenance. This unsigned preview has not been cleared for public redistribution.\n",
        encoding="utf-8")
    buckets = defaultdict(int)
    files = []
    for path in sorted(bundle.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(bundle)
        size = path.stat().st_size
        bucket = relative.parts[1] if relative.parts[0] == "_internal" and len(relative.parts) > 1 else relative.parts[0]
        buckets[bucket] += size
        files.append({"path": relative.as_posix(), "bytes": size})
    version = metadata.version("language-lens")
    archive = output / f"LanguageLens-{version}-windows-x64-preview.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as handle:
        for item in files:
            handle.write(bundle / item["path"], "LanguageLens/" + item["path"])
    hasher = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    (output / (archive.name + ".sha256")).write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    report = {"app_version": version, "python": platform.python_version(), "platform": platform.platform(),
              "runtime_dependency_files_bytes": sum(p.stat().st_size for p in baseline_files),
              "installed_bundle_bytes": sum(item["bytes"] for item in files),
              "download_zip_bytes": archive.stat().st_size, "sha256": digest,
              "language_assets": "OCR, translation, sentence models, voices and optional Japanese/Chinese language packs are separate downloads.",
              "components": dict(sorted(buckets.items(), key=lambda pair: -pair[1])), "files": files}
    (output / "size-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    mib = lambda value: f"{value / 1024**2:,.1f} MiB"
    lines = ["# Portable preview size report", "", f"Python: {report['python']} (Windows x64)", "",
             f"Runtime dependency files in build environment: {mib(report['runtime_dependency_files_bytes'])}",
             f"Installed portable folder: {mib(report['installed_bundle_bytes'])}",
             f"ZIP download: {mib(report['download_zip_bytes'])}", "", report["language_assets"], "",
             "| Component | Installed size |", "| --- | ---: |"]
    lines.extend(f"| {name} | {mib(size)} |" for name, size in list(report["components"].items())[:20])
    (output / "size-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("installed_bundle_bytes", "download_zip_bytes", "sha256")}))


if __name__ == "__main__":
    main()
