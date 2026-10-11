"""Aggregate settings experiments and check the implemented language policy."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from language_lens.config import LANGUAGES
from language_lens.services.ocr_settings import OcrSettings, settings_for

FIELDS = {"Det.limit_type": "det_limit_type", "Det.limit_side_len": "det_limit_side_len",
          "Det.unclip_ratio": "unclip_ratio", "Det.thresh": "det_thresh", "Det.box_thresh": "box_thresh",
          "Det.use_dilation": "dilation", "Det.score_mode": "score_mode",
          "Global.use_vertical_padding": "vertical_padding", "Global.width_height_ratio": "width_height_ratio",
          "Cls.cls_thresh": "cls_thresh", "Global.text_score": "text_score"}


def selected_settings(selected):
    unknown = set(selected["parameters"]) - set(FIELDS) - {"Rec.rec_img_shape"}
    if unknown:
        raise ValueError(f"Unsupported selected controls: {unknown}")
    values = {FIELDS[key]: value for key, value in selected["parameters"].items() if key in FIELDS}
    shape = selected["parameters"].get("Rec.rec_img_shape")
    if shape:
        values["rec_min_width"] = shape[2]
    values.update(use_cls=selected["use_cls"], preprocessing=selected["preprocessing"])
    return OcrSettings(**values)


def integration_checks(paths, report, worker=False):
    expected = {}
    scenarios = {"clean-serif", "small-light", "low-contrast", "panel-dark", "rotated-180", "decorations"}
    for language, record in report["languages"].items():
        validation = record["validation_candidate"] if record["summary"]["accepted"] else record["validation_baseline"]
        for row in validation["rows"]:
            if worker and row["id"] == f"validation-{language}-panel-dark":
                expected[language] = row["actual"]
            elif not worker and row["scenario"] in scenarios:
                # Several passages have the same single-line scenario; audit
                # uses its first validation occurrence, exactly as recorded.
                if not any(key.startswith(f"validation-{language}-") and scenario == row["scenario"]
                           for key, (_actual, scenario) in expected.items()):
                    expected[row["id"]] = (row["actual"], row["scenario"])
    observed, files = {}, []
    for directory in paths:
        path = directory / "audit.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("mismatches"):
            raise ValueError(f"Failed adapter audit {path}")
        files.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for row in data["rows"]:
            key = row["language"] if worker else row["id"]
            if key in observed:
                raise ValueError(f"Duplicate integration evidence {key}")
            reference = expected[key] if worker else expected[key][0]
            if row["actual"] != reference or (worker and not row["ok"]):
                raise ValueError(f"Integration prediction changed for {key}")
            observed[key] = row
    if set(observed) != set(expected):
        raise ValueError(f"Incomplete integration evidence: {set(expected) - set(observed)}")
    return {"samples": len(observed), "languages": len(report["languages"]),
            "native_spans": sum(row["native_spans"] for row in observed.values()), "files": files}


def markdown_report(report):
    stats = report["summary"]
    lines = ["# OCR settings selection", "",
        "Recognizers remain fixed at the previously selected language assignments.",
        f"The search evaluated {stats['settings_screened']} language/configuration combinations on {stats['samples']} rendered selections across all 25 languages.",
        f"Independent validation accepted changes for {stats['accepted_changes']} languages; the remaining languages retain their previous settings.", "",
        "## Published guidance", "",
        "[RapidOCR's maintainer guidance for PP-OCRv6](https://github.com/RapidAI/RapidOCR/discussions/703) proposes a 64-pixel minimum detection side, disabled dilation, a box threshold of 0.6 and expansion of 1.5 when aligning output with PaddleOCR. This is a useful starting point for this model family, not a validated per-language optimum.", "",
        "[PaddleOCR's small detector configuration](https://github.com/PaddlePaddle/PaddleOCR/blob/main/configs/det/PP-OCRv6/PP-OCRv6_small_det.yml) supplies another seed: pixel threshold 0.2, box threshold 0.45 and expansion 1.4. These were tested with the existing detector and with low and moderate upscaling.", "",
        "[PaddleOCR's detection guide](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/module_usage/text_detection.en.md) discusses minimum-side 960 for low-resolution images and larger scales such as 1216. Both scales enter the search. [RapidOCR's parameter documentation](https://rapidai.github.io/RapidOCRDocs/v3.9.0/install_usage/rapidocr/parameters/) explains the general controls but does not establish best settings for each supported language. No validated 25-language settings table was found in the reviewed resources.", "",
        "[An older PaddleOCR Arabic detection discussion](https://github.com/PaddlePaddle/PaddleOCR/issues/7623) suggests increasing expansion to reduce fragmented text. This motivates the additional Arabic 2.5/3.0 trials; it does not establish those values as suitable for the current model.", "",
        "## Workload and selection", "",
        "Each language has 132 selections: 120 single-line crops (12 authored challenge passages under ten conditions), eight multi-line panels, and four blank/decorative controls. Conditions include clean sans/serif/monospace, small light/dark text, italics, blur, JPEG compression, low contrast and downscaling. Panels include light/dark interfaces, closely spaced rows and upside-down text. Public UI strings provide panel text, with separate messages for development and validation.", "",
        "Six challenge passages are used for development and six different passages for validation. Every rendering of a passage stays in its partition. A small development screening set covers all 14 positive scenarios plus negatives. Resizing/expansion and published presets are screened first, followed by up to two rounds of other controls. Three shortlisted alternatives and the baseline are evaluated on the full development partition. The development winner is frozen before validation.", "",
        "The score is the mean of 14 scenario-level mean character error rates (CER). Case, accents and punctuation count; Unicode NFC and whitespace are normalized. Missing all text counts as 100% error. Negative samples are scored separately. The original Dependency heading has no role in settings selection.", "",
        "Acceptance requires at least 0.1 percentage point improvement in validation CER, no more than 0.2 percentage point upright-text regression, no more than 1 point clean-text regression, and no increase in completely missed selections or false-positive negative samples. A final guard tests all six validation passages with blue/red text on light backgrounds and green text on a dark colored background (18 additional selections per language); a regression over 1 point retains the baseline. Grayscale is removed when it leaves every development and validation pixel unchanged, avoiding an unsupported transformation of future colored captures. The chosen configuration can still worsen an individual scenario; all scenario scores and validation predictions remain in the machine-readable report.", "",
        "The benchmark uses the app's default 0.45 minimum confidence. A user's different confidence preference changes which recognized lines survive and was not independently optimized here.", "",
        "## Measured validation results", "",
        f"Across equally weighted languages, balanced CER falls from {stats['baseline_balanced_cer'] * 100:.3f}% to {stats['selected_balanced_cer'] * 100:.3f}%. Excluding the rotated-panel scenario, upright CER falls from {stats['baseline_upright_cer'] * 100:.3f}% to {stats['selected_upright_cer'] * 100:.3f}%. These are corpus error rates, not word accuracy or a general real-world accuracy promise.", "",
        "| Language | Validation CER: previous → selected | Upright CER: previous → selected | Selected controls differing from previous defaults |",
        "|---|---:|---:|---|"]
    defaults = asdict(OcrSettings())
    for name, language in LANGUAGES:
        record = report["languages"][language]
        summary = record["summary"]
        before, after = summary["baseline"], summary["selected_metric"]
        selected = record["implemented_settings"]
        changes = [f"{key}={value}" for key, value in selected.items() if value != defaults[key]]
        lines.append(f"| {name} | {before['balanced_cer'] * 100:.3f}% → {after['balanced_cer'] * 100:.3f}% | {before['upright_cer'] * 100:.3f}% → {after['upright_cer'] * 100:.3f}% | {'; '.join(changes) or 'Retained defaults'} |")
    lines += ["", "## Integration and reproducibility", "",
        "[The settings registry](../src/language_lens/services/ocr_settings.py) feeds both inference and offline preparation. Its identity is included in prepared markers alongside the recognition assignments. The shared detector (v6 small), orientation classifier (v4 mobile), and preprocessing limits are explicit to preserve the tested configuration across library-default changes. Restart Lens and run **Check required files** for the selected pair to verify the revised policy. Model assignments and the user's minimum-confidence preference are preserved.", "",
        "The search tests minimum-side 64/128/256/384/736/960/1216, automatic maximum-side detection, expansion 1.0/1.3/1.4/1.5/1.6/2.0 (also 2.5/3.0 for Arabic), segmentation and box thresholds, dilation, scoring mode, padding, rotation thresholds/enabling, recognition minimum widths, higher confidence filters, grayscale, contrast stretching and dark-background inversion. Not every combination is exhaustive. Recognition height stays at the model's trained 48 pixels and CPU thread limits stay fixed. The existing capture retry behavior is preserved.", "",
        "The shared detector's input normalization stays at RapidOCR's mean/std 0.5, preprocessing limits stay at 30/2000 pixels, the orientation input stays at 48×192, and recognition batch size stays at six. These settings, detector weights, and crop retry behavior are held fixed rather than searched in this stage.", "",
        "| Control | Role | Values or alternatives tested |",
        "|---|---|---|",
        "| Detector resize | How much detail reaches the shared detector | Minimum side 64, 128, 256, 384, 736, 960, 1216; automatic maximum-side mode |",
        "| Crop expansion (`unclip_ratio`) | How far detection contours expand into recognition crops | 1.0, 1.3, 1.4, 1.5, 1.6, 2.0; Arabic also 2.5, 3.0 |",
        "| Pixel/box thresholds | Which probability pixels become contours and which boxes survive | Pixel 0.2/0.3/0.4; box 0.35/0.45/0.5/0.6/0.65 |",
        "| Dilation / box scoring | Whether nearby probability pixels merge and how box confidence is measured | Dilation on/off; fast/slow scoring |",
        "| Vertical padding | Extra background around wide or short selections | On/off; width-to-height triggers 8/16/disabled |",
        "| Orientation classification | Whether and when a crop rotates 180 degrees | On/off; thresholds 0.8/0.9/0.98 |",
        "| Recognition minimum width | How narrow crops are padded in recognition batches | 64/320/640; trained height kept at 48 |",
        "| Text confidence floor | Drop unreliable recognized lines | Library 0.35/0.6/0.75, combined with app floor 0.45 |",
        "| Color preprocessing | Change contrast without moving source coordinates | None; grayscale; dark-background inversion; percentile contrast stretching |", "",
        "RapidOCR 3.9.2 ignores the configured detector side length in `max` mode, instead selecting 960/1500/2000 from the image dimensions. Actual detector tensor shapes are retained in the results. The previous temporary 'max-side 736' experiment should therefore be understood as automatic maximum-side detection, not a 736-pixel cap.", "",
        "Detector probability maps are cached at full float32 precision, and recognition outputs are cached only for identical pixel crops and recognition settings. Caches accelerate the experiment; application inference uses the normal uncached pipeline. Benchmark timings include caching and concurrent jobs and are not production latency measurements.", "",
        "```powershell",
        ".venv/Scripts/python.exe scripts/verify-ocr-settings.py --output artifacts/ocr-settings",
        ".venv/Scripts/python.exe scripts/finalize-ocr-settings.py --runs artifacts/ocr-settings",
        ".venv/Scripts/python.exe scripts/report-ocr-settings.py --runs artifacts/ocr-settings-final --check-assignments",
        ".venv/Scripts/python.exe scripts/audit-ocr-settings.py --runs artifacts/ocr-settings-final",
        ".venv/Scripts/python.exe scripts/audit-ocr-workers.py --runs artifacts/ocr-settings-final",
        "```", "",
        "[Machine-readable results](ocr-settings-benchmark.json) retain model checksums, runtime versions, corpus fingerprints, candidate settings/scores, actual detector input shapes, acceptance gates and both validation predictions. Detailed screening predictions remain in ignored experiment outputs.", "",
        "## Limits", "",
        "These are the best validated configurations from this search. The corpus covers rendered screen text, not arbitrary photos, handwriting, natural scene backgrounds or native vertical CJK composition. There is one multi-line panel per layout in each partition; close wins and orientation gains need independent real captures. The rotated case has equal scenario weight, so upright results are shown separately. Holding models fixed does not prove these models would win every future joint model/settings search.", "",
        "Arabic, Ukrainian, Korean and Greek retain substantial errors on this workload. Retaining defaults can mean that a proposal failed a safety gate, not that defaults have the lowest observed CER in every scenario. In particular, Arabic's monochrome improvement failed the color check, and Ukrainian's improvement increased fully missed selections. A future broader development corpus or joint model/settings comparison may find better choices.", "",
        "The original pre-overlay selection remains unavailable for an identical reproduction of the reported extra I. Synthetic heading checks can demonstrate behavior but cannot establish that exact screenshot as fixed.", ""]
    if report.get("integration"):
        checks = report["integration"]
        lines += ["## Application verification", "",
                  f"The real uncached adapter matched recorded predictions on {checks['adapter']['samples']} validation selections across all 25 languages, with finite line/character geometry and valid span offsets. The offline subprocess protocol matched {checks['worker']['samples']} dark multi-line selections, one per language. Audit fingerprints are retained in the machine-readable report.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/ocr-settings-benchmark.json"))
    parser.add_argument("--check-assignments", action="store_true")
    parser.add_argument("--policy-output", type=Path, help="Write reviewable language assignments as Python text.")
    parser.add_argument("--markdown-output", type=Path, default=Path("docs/ocr-settings-selection.md"))
    parser.add_argument("--adapter-audits", type=Path, nargs="+")
    parser.add_argument("--worker-audits", type=Path, nargs="+")
    args = parser.parse_args()
    report = {"runs": [], "languages": {}}
    for run in args.runs:
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        if "runtime" in report and report["runtime"] != summary["runtime"]:
            raise ValueError("Mixed inference runtimes")
        report["runtime"] = summary["runtime"]
        report["base_parameters"] = summary["base_parameters"]
        report["published_presets"] = summary["published_presets"]
        report["method"] = summary["method"]
        report["runs"].append({"directory": str(run), "corpus_sha256": hashlib.sha256((run / "corpus.json").read_bytes()).hexdigest()})
        for language in summary["languages"]:
            if language in report["languages"]:
                raise ValueError(f"Duplicate {language}")
            record = json.loads((run / f"{language}.json").read_text(encoding="utf-8"))
            report["languages"][language] = {
                "summary": record["summary"], "assets": record["assets"],
                "screen": [{key: result[key] for key in ("settings", "metric")} for result in record["screen"]],
                "development": [{key: result[key] for key in ("settings", "metric")} for result in record["development"]],
                "validation_baseline": record["validation_baseline"],
                "validation_candidate": record["validation_candidate"],
                "equivalent_simplification": record.get("equivalent_simplification"),
                "color_baseline": record.get("color_baseline"), "color_candidate": record.get("color_selected"),
                "color_selected": (record.get("color_selected") if record["summary"]["gates"].get("color_text_safe")
                                   else record.get("color_baseline")),
                "source_sha256": record.get("source_sha256"), "rendering_protocol": record.get("rendering_protocol"),
                "cache": record["cache"], "elapsed_seconds": record["elapsed_seconds"],
            }
    codes = [language for _name, language in LANGUAGES]
    if set(report["languages"]) != set(codes):
        raise ValueError(f"Incomplete language coverage: {set(codes) - set(report['languages'])}")
    actual_changes, policy_lines = {}, ["SETTINGS_BY_LANGUAGE: dict[str, OcrSettings] = {"]
    accepted = 0
    for name, language in LANGUAGES:
        record = report["languages"][language]
        proposed = selected_settings(record["summary"]["selected"])
        record["implemented_settings"] = asdict(proposed)
        if proposed != settings_for(language):
            actual_changes[language] = asdict(proposed)
        arguments = ", ".join(f"{field}={value!r}" for field, value in asdict(proposed).items() if value != asdict(OcrSettings())[field])
        policy_lines.append(f'    "{language}": OcrSettings({arguments}),')
        accepted += record["summary"]["accepted"]
    policy_lines.append("}")
    report["summary"] = {"languages": len(codes), "accepted_changes": accepted,
        "samples": sum(len(record["validation_baseline"]["rows"]) * 2 +
                       len(record.get("color_baseline", {}).get("rows", [])) for record in report["languages"].values()),
        "settings_screened": sum(len(record["screen"]) for record in report["languages"].values()),
        "baseline_balanced_cer": sum(record["summary"]["baseline"]["balanced_cer"] for record in report["languages"].values()) / len(codes),
        "selected_balanced_cer": sum(record["summary"]["selected_metric"]["balanced_cer"] for record in report["languages"].values()) / len(codes),
        "baseline_upright_cer": sum(record["summary"]["baseline"]["upright_cer"] for record in report["languages"].values()) / len(codes),
        "selected_upright_cer": sum(record["summary"]["selected_metric"]["upright_cer"] for record in report["languages"].values()) / len(codes)}
    if args.adapter_audits or args.worker_audits:
        if not (args.adapter_audits and args.worker_audits):
            raise ValueError("Provide both adapter and worker evidence")
        report["integration"] = {"adapter": integration_checks(args.adapter_audits, report),
                                 "worker": integration_checks(args.worker_audits, report, worker=True)}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown_output.write_text(markdown_report(report), encoding="utf-8")
    if args.policy_output:
        args.policy_output.write_text("\n".join(policy_lines) + "\n", encoding="utf-8")
    print(json.dumps({**report["summary"], "assignment_changes": actual_changes}, ensure_ascii=False))
    if args.check_assignments and actual_changes:
        raise SystemExit("Implemented settings differ from accepted validation results")


if __name__ == "__main__":
    main()
