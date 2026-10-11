"""Check the accepted policy through the real adapter, including word geometry."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path

from language_lens.domain import reading_order
from language_lens.services.ocr import RapidOcrEngine
from language_lens.services.ocr_profiles import parameters_for
from language_lens.services.ocr_settings import settings_for
from language_lens.services.offline import matches, no_network, ocr_models

spec = importlib.util.spec_from_file_location("settings_benchmark", Path(__file__).with_name("verify-ocr-settings.py"))
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-settings-audit"))
    parser.add_argument("--model-cache", type=Path, default=Path("artifacts/ocr-models/models"))
    parser.add_argument("--languages", nargs="*", help="Audit only these recorded languages.")
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    args.output.mkdir(parents=True, exist_ok=True)
    records = {language: json.loads((run / f"{language}.json").read_text(encoding="utf-8"))
               for run in args.runs
               for language in json.loads((run / "summary.json").read_text(encoding="utf-8"))["languages"]}
    fingerprints = {sample["id"]: sample["pixel_sha256"]
                    for run in args.runs
                    for sample in json.loads((run / "corpus.json").read_text(encoding="utf-8"))}
    if args.languages is not None:
        records = {language: records[language] for language in args.languages}
    samples, app = experiment.make_corpus(args.output, list(records))
    assert all(fingerprints[sample["id"]] == experiment.tensor_key(sample["pixels"])
               for sample in samples), "Rendered inputs changed"
    output, mismatches = [], []
    for language, record in records.items():
        accepted = record["summary"]["accepted"]
        expected = record["validation_candidate"] if accepted else record["validation_baseline"]
        selected = record["summary"]["selected"]
        params = parameters_for(language)
        assert settings_for(language).preprocessing == selected["preprocessing"]
        assert params["Global.use_cls"] == selected["use_cls"]
        assert all(params[key] == value for key, value in selected["parameters"].items())
        for section, installed, _url, digest, _existing in ocr_models(language):
            model = args.model_cache / installed.name
            assert matches(model, digest)
            params[f"{section}.model_path"] = str(model)
        group = [sample for sample in samples if sample["language"] == language and sample["partition"] == "validation"]
        selected_samples = []
        for scenario in ("clean-serif", "small-light", "low-contrast", "panel-dark", "rotated-180", "decorations"):
            selected_samples.append(next(sample for sample in group if sample["scenario"] == scenario))
        expected_rows = {row["id"]: row for row in expected["rows"]}
        with no_network():
            engine = RapidOcrEngine(language, params=params)
            for sample in selected_samples:
                lines = reading_order(engine.recognize(sample["pixels"]), language)
                actual = experiment.bench.normalized(" ".join(line.text for line in lines))
                if actual != expected_rows[sample["id"]]["actual"]:
                    mismatches.append({"id": sample["id"], "benchmark": expected_rows[sample["id"]]["actual"], "adapter": actual})
                for line in lines:
                    assert all(math.isfinite(v) for point in line.polygon for v in point)
                    assert all(0 <= box.start < box.end <= len(line.text) for box in line.span_boxes)
                    assert all(math.isfinite(v) for box in line.span_boxes for point in box.polygon for v in point)
                output.append({"id": sample["id"], "actual": actual,
                               "lines": len(lines), "native_spans": sum(len(line.span_boxes) for line in lines)})
            del engine
        print(json.dumps({"language": language, "checked": len(selected_samples),
                          "mismatches": sum(item["id"].startswith(f"validation-{language}-") for item in mismatches)}), flush=True)
        experiment.write_json(args.output / "audit.json", {"rows": output, "mismatches": mismatches})
    if mismatches:
        raise RuntimeError("Adapter predictions differ from the recorded experiment; inspect audit.json")


if __name__ == "__main__":
    main()
