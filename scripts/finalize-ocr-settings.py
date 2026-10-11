"""Remove redundant transforms and check unseen colored renderings before use."""
from __future__ import annotations

import argparse
import importlib.util
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from language_lens.services.offline import matches, no_network, ocr_models
from language_lens.services.ocr_profiles import profile_for

spec = importlib.util.spec_from_file_location("settings_benchmark", Path(__file__).with_name("verify-ocr-settings.py"))
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-settings-final"))
    parser.add_argument("--model-cache", type=Path, default=Path("artifacts/ocr-models/models"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    args.output.mkdir(parents=True, exist_ok=True)
    records, first, source_pixels = {}, None, {}
    for run in args.runs:
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        first = first or summary
        source_pixels.update({sample["id"]: sample["pixel_sha256"] for sample in
                              json.loads((run / "corpus.json").read_text(encoding="utf-8"))})
        for language in summary["languages"]:
            if language in records:
                raise ValueError(f"Duplicate language {language}")
            source = run / f"{language}.json"
            records[language] = json.loads(source.read_text(encoding="utf-8"))
            records[language]["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    samples, app = experiment.make_corpus(args.output, list(records))
    assert all(source_pixels[sample["id"]] == experiment.tensor_key(sample["pixels"]) for sample in samples), "Rendered inputs changed"
    from rapidocr import RapidOCR
    final_summary = {key: value for key, value in first.items() if key != "languages"}
    final_summary["languages"] = {}
    for language, record in records.items():
        saved = args.output / f"{language}.json"
        if args.resume and saved.exists():
            previous = json.loads(saved.read_text(encoding="utf-8"))
            if previous.get("source_sha256") == record["source_sha256"] and previous.get("rendering_protocol") == "offscreen-v1":
                final_summary["languages"][language] = previous["summary"]
                continue
        original = record["summary"]["selected"]
        record["rendering_protocol"] = "offscreen-v1"
        group = [sample for sample in samples if sample["language"] == language]
        selected = original
        simplified = (original["preprocessing"] == "gray" and all(
            np.array_equal(sample["pixels"], experiment.transform(sample["pixels"], "gray")) for sample in group))
        if simplified:
            selected = experiment.candidate(original["parameters"], original["use_cls"], "none")
            record["equivalent_simplification"] = {"original": original, "selected": selected,
                "reason": "Every development and validation input is bit-identical after grayscale conversion; prefer no transform."}
            record["summary"]["selected"] = selected
            record["validation_candidate"]["settings"] = selected
        validation = [sample for sample in group if sample["partition"] == "validation"]
        colors = experiment.color_checks(validation)
        params = {**profile_for(language).parameters(), **experiment.BASE}
        for section, installed, _url, digest, _existing in ocr_models(language):
            model = args.model_cache / installed.name
            assert matches(model, digest)
            params[f"{section}.model_path"] = str(model)
        with no_network():
            engine = RapidOCR(params=params)
            engine.text_det.session = experiment.CachedSession(engine.text_det.session, args.output / "detector-cache", capacity=24)
            engine.text_cls.session = experiment.CachedSession(engine.text_cls.session, capacity=1024)
            engine.text_rec = experiment.CachedRecognizer(engine.text_rec)
            baseline = experiment.evaluate(engine, experiment.candidate(), colors)
            result = experiment.evaluate(engine, selected, colors)
            del engine
        record["color_baseline"], record["color_selected"] = baseline, result
        safe = result["metric"]["balanced_cer"] <= baseline["metric"]["balanced_cer"] + .01
        record["summary"]["gates"]["color_text_safe"] = safe
        if not safe:
            record["summary"]["accepted"] = False
            record["summary"]["selected"] = experiment.candidate()
            record["summary"]["selected_metric"] = record["summary"]["baseline"]
        experiment.write_json(args.output / f"{language}.json", record)
        final_summary["languages"][language] = record["summary"]
        experiment.write_json(args.output / "summary.json", final_summary)
        print(json.dumps({"language": language, "simplified": simplified, "color_safe": safe,
                          "accepted": record["summary"]["accepted"]}), flush=True)
    experiment.write_json(args.output / "summary.json", final_summary)


if __name__ == "__main__":
    main()
