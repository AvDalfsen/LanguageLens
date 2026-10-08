"""Run PyInstaller with a controlled DLL search path and retain its complete log."""
import argparse
from importlib import metadata
import os
from pathlib import Path
import subprocess
import struct
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32" or sys.version_info[:2] != (3, 10) or struct.calcsize("P") != 8:
        raise RuntimeError("The release snapshot targets Windows x64 Python 3.10")
    for source in (root / "constraints/windows-python310.txt", root / "packaging/requirements-build.txt"):
        for line in source.read_text(encoding="utf-8").splitlines():
            if "==" not in line or line.startswith("#"):
                continue
            name, expected = line.split("==", 1)
            try:
                actual = metadata.version(name)
            except metadata.PackageNotFoundError:
                continue  # Unused development dependencies need not be installed.
            if actual != expected:
                raise RuntimeError(f"Release version mismatch: {name} {actual}, expected {expected}")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PYTHON", "QT_"))}
    env["PATH"] = os.pathsep.join((str(Path(sys.executable).parent), str(Path(sys.base_prefix)),
                                  str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["SystemRoot"]))
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(output / "dist"),
               "--workpath", str(output / "work"), str(root / "packaging/LanguageLens.spec")]
    with (output / "build.log").open("w", encoding="utf-8") as log:
        return subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
