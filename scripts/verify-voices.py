"""Opt-in real synthesis smoke test; assets stay in ignored development artifacts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

from language_lens.services.voices import VOICES


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Download and verify every catalogue voice (~1.8 GB).")
    parser.add_argument("--ids", nargs="*", default=["nl_NL-pim-medium", "ja_JP-hi_fi_captain-medium", "zh_CN-huayan-medium"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "artifacts" / "voice-validation"
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LOCALAPPDATA=str(root / "app-data"))
    failures = []
    for voice in VOICES:
        if not args.all and voice.id not in args.ids:
            continue
        print(f"Checking {voice.id} ({voice.total_bytes / 1e6:.0f} MB)…", flush=True)
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            scratch = Path(temporary)
            base = [sys.executable, "-m", "language_lens.services.speech_worker"]
            options = ["--voice", voice.id, "--root", str(root), "--scratch", str(scratch)]
            try:
                download = subprocess.run(base + ["download"] + options, input=b"{}", capture_output=True, timeout=300, env=env)
                if download.returncode:
                    raise RuntimeError(download.stdout[-500:].decode("utf-8", errors="replace"))
                for speed in (1., .75):
                    result = subprocess.run(base + ["synthesize"] + options,
                        input=json.dumps({"text": voice.sample, "speed": speed}, ensure_ascii=True).encode(),
                        capture_output=True, timeout=60, env=env)
                    if result.returncode:
                        raise RuntimeError(result.stdout.decode("utf-8", errors="replace"))
                    with wave.open(str(scratch / "selection.wav")) as audio:
                        seconds = audio.getnframes() / audio.getframerate()
                        assert .1 < seconds < 60 and audio.getnchannels() == 1
                print(f"PASS {voice.id} · normal + slower synthesis", flush=True)
            except Exception as exc:
                failures.append(voice.id)
                print(f"FAIL {voice.id}: {exc}", flush=True)
    print(f"Failed voices: {failures}", flush=True)
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
