"""Verify each language's accepted settings through the offline worker protocol."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import cv2

from language_lens.config import Settings
from language_lens.services.offline import matches, ocr_models

spec = importlib.util.spec_from_file_location("settings_benchmark", Path(__file__).with_name("verify-ocr-settings.py"))
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-worker-audit"))
    parser.add_argument("--model-cache", type=Path, default=Path("artifacts/ocr-models/models"))
    parser.add_argument("--languages", nargs="*", help="Audit only these recorded languages.")
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    args.output.mkdir(parents=True, exist_ok=True)
    records, fingerprints = {}, {}
    for run in args.runs:
        fingerprints.update({sample["id"]: sample["pixel_sha256"]
                             for sample in json.loads((run / "corpus.json").read_text(encoding="utf-8"))})
        for language in json.loads((run / "summary.json").read_text(encoding="utf-8"))["languages"]:
            if language in records:
                raise ValueError(f"Duplicate language {language}")
            records[language] = json.loads((run / f"{language}.json").read_text(encoding="utf-8"))
    if args.languages is not None:
        records = {language: records[language] for language in args.languages}
    samples, app = experiment.make_corpus(args.output, list(records))
    assert all(fingerprints[sample["id"]] == experiment.tensor_key(sample["pixels"])
               for sample in samples), "Rendered inputs changed"
    # The child gets only a workspace-local asset cache and its public crop.
    appdata = (args.output / "appdata").resolve()
    environment = dict(os.environ, LOCALAPPDATA=str(appdata), QT_QPA_PLATFORM="offscreen")
    output = []
    for language, record in records.items():
        for _section, installed, _url, digest, _existing in ocr_models(language):
            source = args.model_cache / installed.name
            assert matches(source, digest)
            target = appdata / "LanguageLens/offline/ocr" / installed.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not matches(target, digest):
                shutil.copyfile(source, target)
        sample = next(sample for sample in samples if sample["id"] == f"validation-{language}-panel-dark")
        scratch = (args.output / language).resolve()
        scratch.mkdir(exist_ok=True)
        cv2.imwrite(str(scratch / "crop.png"), sample["pixels"])
        height, width = sample["pixels"].shape[:2]
        payload = {"settings": asdict(Settings(source_language=language, speech_enabled=False)),
                   "selection_size": [width, height], "regions": [
                       {"image": "crop.png", "retry": None, "offset": [0, 0],
                        "size": [width, height], "mapping": [0, 0, 1, 1]}]}
        process = subprocess.run([sys.executable, "-m", "language_lens.services.task_worker", "ocr",
                                  "--scratch", str(scratch)], env=environment,
                                 input=json.dumps(payload).encode(), capture_output=True, timeout=120)
        events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith(b"{")]
        assert process.returncode == 0 and any(event.get("ok") for event in events), (language, events)
        lines = next(event["result"] for event in events if "result" in event)
        actual = experiment.bench.normalized(" ".join(line["text"] for line in lines))
        expected = record["validation_candidate"] if record["summary"]["accepted"] else record["validation_baseline"]
        reference = next(row["actual"] for row in expected["rows"] if row["id"] == sample["id"])
        assert actual == reference, (language, actual, reference)
        entry = {"language": language, "id": sample["id"], "actual": actual,
                 "lines": len(lines), "native_spans": sum(len(line["span_boxes"]) for line in lines), "ok": True}
        output.append(entry)
        experiment.write_json(args.output / "audit.json", {"rows": output})
        print(json.dumps({key: entry[key] for key in ("language", "lines", "native_spans", "ok")}), flush=True)


if __name__ == "__main__":
    main()
