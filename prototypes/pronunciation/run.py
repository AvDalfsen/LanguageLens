"""Reproducible CLI and listening report for stage one; not the application UI."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote
from urllib.request import urlopen

from .engine import LOCALES, PIPER_VERSION, Pronouncer, VoiceRenderer


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "artifacts" / "pronunciation"


def manifest() -> dict:
    return json.loads((HERE / "voices.json").read_text(encoding="utf-8"))


def valid_file(path: Path, expected: list) -> bool:
    if not path.is_file() or path.stat().st_size != expected[0]:
        return False
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected[1]


def download(locales: list[str]) -> None:
    """Explicit network step, pinned upstream revision and catalogue checksums."""
    catalog = manifest()
    for locale in locales:
        entry = catalog["voices"][locale]
        directory = DATA / "voices" / locale
        directory.mkdir(parents=True, exist_ok=True)
        for filename, expected in entry["files"].items():
            target = directory / filename
            if valid_file(target, expected):
                print(f"{locale}: already verified {filename}", flush=True)
                continue
            url = (f"https://huggingface.co/{catalog['repository']}/resolve/"
                   f"{catalog['revision']}/{quote(entry['directory'] + '/' + filename)}")
            print(f"{locale}: downloading {filename} ({expected[0] / 1_000_000:.1f} MB)", flush=True)
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as output:
                    temporary = Path(output.name)
                    with urlopen(url, timeout=30) as response:
                        count, last_step = 0, -1
                        while chunk := response.read(1024 * 1024):
                            count += len(chunk)
                            if count > expected[0]:
                                raise ValueError(f"Unexpected file size for {filename}.")
                            output.write(chunk)
                            step = count * 10 // expected[0]
                            if expected[0] > 1_000_000 and step != last_step:
                                print(f"  {locale}: {min(100, count * 100 // expected[0])}%", flush=True)
                                last_step = step
                if not valid_file(temporary, expected):
                    raise ValueError(f"Upstream size/checksum verification failed: {filename}")
                temporary.replace(target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)


def model_path(locale: str) -> Path:
    entry = manifest()["voices"][locale]
    directory = DATA / "voices" / locale
    for filename, expected in entry["files"].items():
        if not valid_file(directory / filename, expected):
            raise ValueError(f"Missing or corrupt {locale} voice. Run the download command first.")
    return directory / (entry["id"] + ".onnx")


def worker(locale: str, output: Path, text: str | None, word: int | None) -> dict:
    started = time.perf_counter()
    pronouncer = Pronouncer()
    renderer = VoiceRenderer(model_path(locale), locale)
    load_seconds = time.perf_counter() - started
    cases = json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))
    if text is not None:
        cases = [{"id": "selection", "text": text, "locales": [locale], "review": "User-supplied selection; not linguistically validated."}]
    results = []
    for case in cases:
        if locale not in case["locales"]:
            continue
        case_output = output / locale / case["id"]
        case_output.mkdir(parents=True, exist_ok=True)
        began = time.perf_counter()
        prepared = pronouncer.prepare(case["text"], locale)
        result = prepared.to_dict()
        result.update(id=case["id"], review=case["review"], errors=[], word_audio={})
        result["prepare_seconds"] = time.perf_counter() - began
        audio_started = time.perf_counter()
        try:
            result["sentence_audio"] = renderer.render(prepared.sentence_phonemes, case_output / "sentence.wav")
        except Exception as exc:
            result["errors"].append(f"Sentence audio: {exc}")
        if word is not None and not 0 <= word < len(prepared.words):
            raise ValueError(f"Word index {word} is outside this selection (0..{len(prepared.words) - 1}).")
        for selected in prepared.words:
            if word is not None and selected.index != word:
                continue
            if selected.mode == "unavailable":
                continue
            try:
                result["word_audio"][str(selected.index)] = renderer.render(
                    (selected.phonemes,), case_output / f"word-{selected.index:03}.wav")
            except Exception as exc:
                result["errors"].append(f"Word {selected.index}: {exc}")
        result["render_seconds"] = time.perf_counter() - audio_started
        if "different_words" in case:
            first, second = (prepared.words[i] for i in case["different_words"])
            result["contrast_check"] = {
                "passed": first.phonemes != second.phonemes,
                "words": case["different_words"],
                "meaning": "Expected pronunciations to differ; a pass does not establish full pronunciation accuracy.",
            }
        (case_output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(result)
    return {"locale": locale, "voice": manifest()["voices"][locale]["id"],
            "load_seconds": load_seconds, "cases": results}


def run_supervised(locales: list[str], output: Path, text: str | None, word: int | None, timeout: float) -> dict:
    """Native calls and inference are killable without affecting Language Lens."""
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "python": sys.version, "piper": PIPER_VERSION, "voice_revision": manifest()["revision"],
              "locales": [], "errors": []}
    for locale in locales:
        print(f"Checking {locale}: sentence phonemes, source mapping, and audio…", flush=True)
        command = [sys.executable, "-m", "prototypes.pronunciation.run", "_worker", "--locale", locale,
                   "--output", str(output)]
        if text is not None:
            command.extend(["--text", text])
        if word is not None:
            command.extend(["--word", str(word)])
        try:
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=timeout,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            report["errors"].append(f"{locale}: worker exceeded {timeout:g} seconds and was terminated.")
            continue
        if process.returncode:
            report["errors"].append(f"{locale}: worker failed ({process.returncode}): {process.stderr.strip()}")
            continue
        try:
            report["locales"].append(json.loads(process.stdout))
        except json.JSONDecodeError:
            report["errors"].append(f"{locale}: worker returned invalid output.")
    return report


def write_report(report: dict, output: Path) -> None:
    esc = html.escape
    cases = [case for locale in report["locales"] for case in locale["cases"]]
    words = [word for case in cases for word in case["words"]]
    report["summary"] = {
        "cases": len(cases), "words": len(words),
        "context_words": sum(w["mode"] == "context" for w in words),
        "isolated_words": sum(w["mode"] == "isolated" for w in words),
        "unavailable_words": sum(w["mode"] == "unavailable" for w in words),
        "event_matches": sum(c["events_match"] for c in cases),
        "audio_files": sum(bool(c.get("sentence_audio")) + len(c["word_audio"]) for c in cases),
        "audio_errors": sum(len(c["errors"]) for c in cases),
        "failed_contrasts": [f"{c['locale']}/{c['id']}" for c in cases
                             if "contrast_check" in c and not c["contrast_check"]["passed"]],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    blocks = ["<h1>Language Lens · pronunciation experiment</h1>",
              "<p>Stage one research report. The application has not changed. Nothing plays automatically; all audio is local.</p>",
              "<p><strong>Context means verified source/phoneme mapping, not verified linguistic correctness.</strong> "
              "Isolated fallbacks were generated separately. Listen to the sentence and compare the word samples.</p>",
              "<p>Generated IPA is an estimate. Voices are test fixtures, not an approved distribution catalogue.</p>",
              f"<pre>{esc(json.dumps(report['summary'], indent=2))}</pre>"]
    for error in report["errors"]:
        blocks.append(f"<p class='warning'>{esc(error)}</p>")
    for locale in report["locales"]:
        blocks.append(f"<h2>{esc(locale['locale'])} · {esc(locale['voice'])}</h2>"
                      f"<p>Voice load: {locale['load_seconds']:.2f} seconds. CPU inference, two threads.</p>")
        for case in locale["cases"]:
            base = quote(f"{locale['locale']}/{case['id']}/")
            blocks.append(f"<section><h3>{esc(case['id'])}</h3><p class='source'>{esc(case['text'])}</p>"
                          f"<p>{esc(case['review'])}</p>")
            if "contrast_check" in case:
                passed = case["contrast_check"]["passed"]
                blocks.append(f"<p class='{'pass' if passed else 'warning'}'>"
                              f"Pronunciation contrast: {'different, as expected' if passed else 'FAILED: both pronunciations are identical'}.</p>")
            for error in case["errors"] + case["warnings"]:
                blocks.append(f"<p class='warning'>{esc(error)}</p>")
            if "sentence_audio" in case:
                blocks.append(f"<p>Whole selection</p><audio controls preload='none' src='{base}sentence.wav'></audio>")
            blocks.append(f"<p>Preparation: {case['prepare_seconds']:.3f}s · "
                          f"All audio generation: {case['render_seconds']:.2f}s</p><div class='words'>")
            for word in case["words"]:
                blocks.append(f"<article><strong>{word['index']}: {esc(word['text'])}</strong>"
                              f"<div class='ipa'>/{esc(word['ipa'])}/</div>"
                              f"<small>{esc(word['mode'])} · source {word['start']}:{word['end']}</small>")
                if word["reason"]:
                    blocks.append(f"<p class='warning'>{esc(word['reason'])}</p>")
                if str(word["index"]) in case["word_audio"]:
                    blocks.append(f"<audio controls preload='none' src='{base}word-{word['index']:03}.wav'></audio>")
                blocks.append("</article>")
            blocks.append("</div></section>")
    style = """body{font:16px system-ui,sans-serif;background:#0b1424;color:#e8eef8;max-width:1100px;margin:40px auto;padding:0 24px}
        section{background:#111e32;border:1px solid #31435f;border-radius:12px;padding:20px;margin:24px 0}
        .words{display:flex;flex-wrap:wrap;gap:12px}article{background:#0b1424;border:1px solid #31435f;border-radius:8px;padding:12px;width:300px}
        audio{width:100%;max-width:500px}small{color:#b8c6da}.warning{color:#ffd28b}.pass{color:#63e6be}
        .ipa{font:22px 'Segoe UI',sans-serif;margin:8px 0}.source{font-size:20px;white-space:pre-wrap}pre{white-space:pre-wrap}h2{margin-top:48px}"""
    (output / "index.html").write_text("<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Language Lens pronunciation experiment</title>"
        f"<style>{style}</style><body>{''.join(blocks)}</body></html>", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2), flush=True)
    print(f"Listening report: {output / 'index.html'}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["download", "suite", "render", "_worker"])
    parser.add_argument("--locale", choices=[*LOCALES, "all"], default="all")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--text")
    parser.add_argument("--word", type=int, help="Zero-based word occurrence; omitted renders every word.")
    parser.add_argument("--timeout", type=float, default=180, help="Maximum seconds per disposable locale worker.")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    locales = list(LOCALES) if args.locale == "all" else [args.locale]
    if args.command == "download":
        download(locales)
        return 0
    if args.command == "render" and (args.text is None or args.locale == "all"):
        parser.error("render requires --text and a specific --locale")
    if args.word is not None and args.text is None:
        parser.error("--word requires --text")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.command == "_worker":
        if args.locale == "all" or args.output is None:
            parser.error("worker requires a locale and output directory")
        print(json.dumps(worker(args.locale, args.output, args.text, args.word), ensure_ascii=False))
        return 0
    output = (args.output or DATA / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Use an empty output directory to preserve previous listening reports.")
    report = run_supervised(locales, output, args.text, args.word, args.timeout)
    write_report(report, output)
    return 1 if report["errors"] or report["summary"]["audio_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
