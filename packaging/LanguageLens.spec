# Windows x64 / Python 3.10 portable preview. Shared runtime, two entry points.
from pathlib import Path
import json
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata
from PyInstaller.config import CONF

root = Path(SPECPATH).parent
datas = collect_data_files("language_lens")
datas += [(str(root / "packaging" / "portable-release.json"), ".")]
for package in ("piper", "minisbd"):
    datas += collect_data_files(package)
datas += collect_data_files("rapidocr", excludes=["models/**", "**/*.onnx"])
# Version checks and offline readiness depend on installed distribution metadata.
datas += copy_metadata("language-lens", recursive=True)
binaries = collect_dynamic_libs("piper")

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")],
    datas=datas,
    binaries=binaries,
    hiddenimports=["rapidocr.main", "pydantic"],
    # Lens installs its version-checked SBD adapter before importing Argos.
    # OCR and sentence models both use ONNX; CTranslate2 runs translation.
    excludes=["janome", "jieba", "pyopenjtalk", "sudachipy", "sudachidict_core",
              "argostranslate.sbd", "stanza", "torch", "spacy", "thinc", "blis",
              "pytest", "_pytest", "IPython", "notebook",
              "tkinter", "matplotlib", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtTest"],
    noarchive=False,
)
# Refuse DLLs from unrelated applications, even if a future hook changes search paths.
allowed = [Path(p).resolve() for p in (sys.prefix, sys.base_prefix, os.environ["SystemRoot"])]
for destination, source, kind in a.binaries:
    if not any(Path(source).resolve().is_relative_to(base) for base in allowed):
        raise RuntimeError(f"Unexpected binary dependency outside the build runtime: {source}")
(Path(CONF["workpath"]) / "bundle-inputs.json").write_text(json.dumps({
    "python": sys.version, "executable": sys.executable,
    "binary_count": len(a.binaries), "data_count": len(a.datas),
    "excluded_modules": a.excludes,
}, indent=2), encoding="utf-8")
pyz = PYZ(a.pure)
options = [("X utf8", None, "OPTION")]
gui = EXE(pyz, a.scripts, options, exclude_binaries=True, name="LanguageLens",
          console=False, debug=False, strip=False, upx=False)
worker = EXE(pyz, a.scripts, options, exclude_binaries=True, name="LanguageLensWorker",
             console=True, debug=False, strip=False, upx=False)
uninstaller = EXE(pyz, a.scripts, options, exclude_binaries=True, name="LanguageLensUninstall",
                  console=False, debug=False, strip=False, upx=False)
COLLECT(gui, worker, uninstaller, a.binaries, a.datas, name="LanguageLens", strip=False, upx=False)
