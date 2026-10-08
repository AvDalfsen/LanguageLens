"""Explicit network test: install packs using the packaged worker in isolated storage."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    from language_lens.config import Settings
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PYTHON", "ARGOS_", "LANGUAGE_LENS_"))}
    env.update(LOCALAPPDATA=str(root), XDG_DATA_HOME=str(root / "data"),
               XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
               PATH=str(Path(os.environ["SystemRoot"]) / "System32"))
    worker = args.bundle.resolve() / "LanguageLensWorker.exe"
    for pack in ("ja-text", "zh-text", "ja-speech"):
        scratch = root / (pack + "-scratch")
        scratch.mkdir(exist_ok=True)
        payload = json.dumps({"settings": asdict(Settings()), "pack": pack}).encode()
        with (root / (pack + ".log")).open("wb") as log:
            result = subprocess.run([str(worker), "--worker", "task", "pack-install", "--scratch", str(scratch)],
                                    input=payload, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=root,
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=1800)
        if result.returncode:
            raise RuntimeError(f"Pack download failed; see {root / (pack + '.log')}")
        print(f"Installed and verified {pack}", flush=True)


if __name__ == "__main__":
    main()
