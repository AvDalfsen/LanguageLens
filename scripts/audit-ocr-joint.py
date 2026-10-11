"""Verify final joint policy through uncached adapter and real OCR worker."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import cv2

from language_lens.config import Settings
from language_lens.domain import reading_order
from language_lens.services.ocr import RapidOcrEngine
from language_lens.services.ocr_profiles import parameters_for, profile_for
from language_lens.services.ocr_settings import settings_for
from language_lens.services.offline import matches, no_network, ocr_models

spec = importlib.util.spec_from_file_location("joint_report", Path(__file__).with_name("report-ocr-joint.py"))
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)
joint = reporter.joint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-joint-audit"))
    parser.add_argument("--model-cache", type=Path, default=Path("artifacts/ocr-models/models"))
    parser.add_argument("--languages", nargs="+")
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    args.output.mkdir(parents=True, exist_ok=True)
    records = reporter.load_records(args.runs, require_complete=not bool(args.languages))
    if args.languages:
        records = {language: records[language] for language in args.languages}
    samples, app = joint.fresh_corpus(args.output, [code for code in records if code != "en"])
    if "en" in records:
        original = joint.FRESH_TEXTS
        joint.FRESH_TEXTS = Path(__file__).parent / "data/ocr-joint-english-validation-texts.json"
        english_output = args.output / "english"
        english_output.mkdir(exist_ok=True)
        english, app = joint.fresh_corpus(english_output, ["en"])
        samples.extend(english)
        joint.FRESH_TEXTS = original
    recorded_pixels = {row[0]: row[2] for record in records.values() for row in record["inputs"]["validation"]}
    assert all(recorded_pixels[row["id"]] == joint.experiment.tensor_key(row["pixels"]) for row in samples)
    rows, mismatches = [], []
    appdata = (args.output / "appdata").resolve()
    environment = dict(os.environ, LOCALAPPDATA=str(appdata), QT_QPA_PLATFORM="offscreen")
    for language, record in records.items():
        selected = record["summary"]["selected"]
        assert profile_for(language).name == selected["model"]
        assert settings_for(language) == reporter.settings_report.selected_settings(selected["settings"])
        expected = (record["models"][selected["model"]]["validation"] if record["summary"]["accepted"]
                    else record["validation_incumbent"])
        expected_rows = {row["id"]: row["actual"] for row in expected["rows"]}
        params = parameters_for(language)
        for section, installed, _url, digest, _existing in ocr_models(language):
            source = args.model_cache / installed.name
            assert matches(source, digest)
            params[f"{section}.model_path"] = str(source)
            target = appdata / "LanguageLens/offline/ocr" / installed.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not matches(target, digest):
                shutil.copyfile(source, target)
        group = [sample for sample in samples if sample["language"] == language]
        selected_samples = [next(row for row in group if row["scenario"] == scenario) for scenario in
                            ("clean-serif", "small-light", "low-contrast", "panel-dark", "rotated-180",
                             "blue-light", "red-light", "decorations")]
        with no_network():
            engine = RapidOcrEngine(language, params=params)
            for sample in selected_samples:
                lines = reading_order(engine.recognize(sample["pixels"]), language)
                actual = joint.bench.normalized(" ".join(line.text for line in lines))
                if actual != expected_rows[sample["id"]]:
                    mismatches.append({"id": sample["id"], "expected": expected_rows[sample["id"]], "actual": actual})
                for line in lines:
                    assert all(math.isfinite(value) for point in line.polygon for value in point)
                    assert all(0 <= box.start < box.end <= len(line.text) for box in line.span_boxes)
                    assert all(math.isfinite(value) for box in line.span_boxes for point in box.polygon for value in point)
                rows.append({"id": sample["id"], "language": language, "actual": actual,
                             "native_spans": sum(len(line.span_boxes) for line in lines), "lines": len(lines)})
            del engine
        sample = next(row for row in group if row["scenario"] == "panel-dark")
        scratch = (args.output / language).resolve()
        scratch.mkdir(exist_ok=True)
        cv2.imwrite(str(scratch / "crop.png"), sample["pixels"])
        height, width = sample["pixels"].shape[:2]
        payload = {"settings": asdict(Settings(source_language=language, speech_enabled=False)),
                   "selection_size": [width, height], "regions": [
                       {"image": "crop.png", "retry": None, "offset": [0, 0], "size": [width, height], "mapping": [0, 0, 1, 1]}]}
        process = subprocess.run([sys.executable, "-m", "language_lens.services.task_worker", "ocr", "--scratch", str(scratch)],
                                 env=environment, input=json.dumps(payload).encode(), capture_output=True, timeout=180)
        events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith(b"{")]
        assert process.returncode == 0 and any(event.get("ok") for event in events), (language, events)
        lines = next(event["result"] for event in events if "result" in event)
        actual = joint.bench.normalized(" ".join(line["text"] for line in lines))
        if actual != expected_rows[sample["id"]]:
            mismatches.append({"id": f"worker-{language}", "expected": expected_rows[sample["id"]], "actual": actual})
        rows.append({"id": f"worker-{language}", "language": language, "actual": actual,
                     "native_spans": sum(len(line["span_boxes"]) for line in lines), "lines": len(lines), "ok": True})
        joint.experiment.write_json(args.output / "audit.json", {"rows": rows, "mismatches": mismatches})
        print(json.dumps({"language": language, "checked": 9, "mismatches": len(mismatches)}), flush=True)
    if mismatches:
        raise RuntimeError("Uncached application output differs from recorded benchmark")


if __name__ == "__main__":
    main()
