"""Aggregate complete model runs with equal weight for each rendering scenario."""
from __future__ import annotations

import argparse
from collections import defaultdict
from importlib.metadata import version
import json
from pathlib import Path
import runpy
from statistics import mean

from language_lens.config import LANGUAGES
from language_lens.services.ocr_profiles import profile_for


BASELINES = {"ar": "arabic-v5", "el": "greek-v5", "hi": "hindi-v5", "ko": "korean-v5",
             "ru": "cyrillic-v5", "uk": "cyrillic-v5", "ja": "chinese-v5-mobile", "zh": "chinese-v5-mobile"}


def metrics(rows):
    return {"samples": len(rows), "edits": sum(row["edits"] for row in rows),
            "characters": sum(row["characters"] for row in rows), "exact": sum(row["exact"] for row in rows),
            "cer": sum(row["edits"] for row in rows) / sum(row["characters"] for row in rows),
            "mean_line_cer": mean(row["edits"] / row["characters"] for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True, help="Result JSON files (split model runs are supported).")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-model-selection.json"))
    parser.add_argument("--check-assignments", action="store_true")
    args = parser.parse_args()
    benchmark = runpy.run_path(str(Path(__file__).with_name("verify-ocr-models.py")))
    candidates = benchmark["CANDIDATES"]
    grouped, models, corpora = defaultdict(dict), {}, {}
    for path in args.runs:
        result = json.loads(path.read_text(encoding="utf-8"))
        partition = result.get("partition", "initial")
        manifest = path.with_name("corpus.json")
        if manifest.exists():
            corpus = json.loads(manifest.read_text(encoding="utf-8"))
            corpora[partition] = {key: value for key, value in corpus.items() if key != "samples"}
        for model, info in result["models"].items():
            models[model] = {key: value for key, value in info.items() if key not in {"rows", "load_seconds"}}
            for original in info["rows"]:
                language = original["language"]
                if model not in candidates[language]:
                    continue
                # These two original diagnostic examples are demonstration-only;
                # neither influences language assignments.
                if original["id"].startswith(("en-dependency-heading-", "en-ambiguous-characters-")):
                    continue
                row = dict(original)
                variant = row.get("variant") or next(variant[0] for variant in benchmark["VARIANTS"]
                                                     if row["id"].endswith("-" + variant[0]))
                row["scenario"] = ("challenge-" if partition == "challenge" else "ui-") + variant
                row["partition"] = partition
                key = (partition, row["id"])
                if key in grouped[(language, model)]:
                    raise ValueError(f"Duplicate observation: {language}, {model}, {key}")
                grouped[(language, model)][key] = row
    languages = {}
    for label, language in LANGUAGES:
        scores = {}
        reference_ids = set(grouped[(language, candidates[language][0])])
        for model in candidates[language]:
            rows = list(grouped[(language, model)].values())
            if len(rows) != 228 or set(grouped[(language, model)]) != reference_ids:
                raise ValueError(f"Incomplete comparison for {language}, {model}: {len(rows)} samples, expected 228.")
            scenarios = {name: metrics([row for row in rows if row["scenario"] == name])
                         for name in sorted({row["scenario"] for row in rows})}
            partitions = {name: metrics([row for row in rows if row["partition"] == name])
                          for name in sorted({row["partition"] for row in rows})}
            scores[model] = {**metrics(rows), "balanced_cer": mean(metric["mean_line_cer"] for metric in scenarios.values()),
                             "scenarios": scenarios, "partitions": partitions}
        baseline = BASELINES.get(language, "latin-v5")
        best_score = min(score["balanced_cer"] for score in scores.values())
        winners = [model for model, score in scores.items() if abs(score["balanced_cer"] - best_score) < 1e-12]
        recommended = baseline if baseline in winners else min(winners, key=lambda model: scores[model]["cer"])
        selected = profile_for(language).name
        languages[language] = {"language": label, "baseline": baseline, "selected": selected,
                               "recommended": recommended, "candidates": scores}
        print(f"| {label} ({language}) | {recommended} | {100 * scores[baseline]['balanced_cer']:.3f}% | {100 * best_score:.3f}% |")
    output = {"date": "2026-10-11", "runtime": {name: version(name) for name in ("rapidocr", "onnxruntime", "python-bidi", "PySide6", "opencv-python")},
              "method": "Minimum mean of 14 equally weighted scenario mean line CERs (4 UI + 10 challenge). Each line has equal weight within its scenario. NFC and whitespace normalized; case, accents and punctuation retained. Original heading and ambiguity diagnostic examples excluded from ranking. Baseline retained on exact ties. Timings from concurrent runs are not selection evidence.",
              "corpus": {"languages": 25, "ranking_images": 5700, "images_per_language": 228,
                         "ui_messages_per_language": 27, "challenge_messages_per_language": 12,
                         "supported_candidate_inferences": sum(len(rows) for rows in grouped.values()), "manifests": corpora},
              "models": models, "languages": languages}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    differences = {language: result["recommended"] for language, result in languages.items()
                   if result["selected"] != result["recommended"]}
    print(json.dumps({"assignment_changes": differences}))
    if args.check_assignments and differences:
        raise RuntimeError("Assignments differ from the recorded comparison.")


if __name__ == "__main__":
    main()
