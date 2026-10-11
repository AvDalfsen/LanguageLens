"""Aggregate the frozen joint experiment and verify source policy assignments."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import mean

from language_lens.config import LANGUAGES
from language_lens.services.ocr_profiles import profile_for
from language_lens.services.ocr_settings import OcrSettings, settings_for


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


joint = module("joint_benchmark", "verify-ocr-joint.py")
settings_report = module("settings_report", "report-ocr-settings.py")


def load_records(runs, require_complete=True):
    records = {}
    for run in runs:
        for path in run.glob("*.json"):
            if path.stem not in {code for _name, code in LANGUAGES}:
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            if path.stem == "en" and "english_catalogue_probe" not in record.get("inputs", {}):
                continue  # Superseded by the expanded English experiment.
            if "summary" not in record:
                # A split queue can retain an interrupted future language.
                # Only finished records are evidence; coverage below still
                # requires every language exactly once for a final report.
                continue
            if path.stem in records:
                raise ValueError(f"Duplicate language {path.stem}")
            record["source"] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            records[path.stem] = record
    if require_complete and set(records) != {code for _name, code in LANGUAGES}:
        raise ValueError(f"Incomplete coverage: {set(code for _name, code in LANGUAGES) - set(records)}")
    return records


def check_record(record):
    language = record["language"]
    assert record["inputs"]["protocol"] == joint.PROTOCOL
    assert record["identity"] == hashlib.sha256(json.dumps(record["inputs"], sort_keys=True).encode()).hexdigest()
    expected = joint.bench.MODELS if language == "en" else joint.bench.CANDIDATES[language]
    assert set(record["models"]) == set(expected)
    validation_ids = {row["id"] for row in record["validation_incumbent"]["rows"]}
    assert len(validation_ids) == 110
    for model, result in record["models"].items():
        assert len(result["initial"]) == len({joint.experiment.candidate()["id"], record["current"]["id"]})
        assert all(len(value["rows"]) == 84 for value in result["initial"])
        assert {row["id"] for row in result["validation"]["rows"]} == validation_ids
        assert result["winner"]["settings"] == result["validation"]["settings"]
        assert result["validation"]["metric"] == joint.experiment.metric(result["validation"]["rows"])
    frozen = record["frozen"]
    assert record["frozen_sha256"] == hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    assert frozen["settings"] == record["models"][frozen["model"]]["winner"]["settings"]
    old, new = record["validation_incumbent"]["metric"], record["models"][frozen["model"]]["validation"]["metric"]
    assert record["summary"]["gates"] == joint.gates(old, new)
    assert record["summary"]["accepted"] == all(joint.gates(old, new).values())
    expected = frozen if record["summary"]["accepted"] else {"model": record["incumbent"], "settings": record["current"]}
    assert record["summary"]["selected"] == expected


def audit_evidence(paths, records):
    observed, files = {}, []
    expected = {}
    for language, record in records.items():
        selected = record["summary"]["selected"]
        value = (record["models"][selected["model"]]["validation"] if record["summary"]["accepted"]
                 else record["validation_incumbent"])
        scenarios = ("clean-serif", "small-light", "low-contrast", "panel-dark", "rotated-180",
                     "blue-light", "red-light", "decorations")
        for scenario in scenarios:
            row = next(row for row in value["rows"] if row["scenario"] == scenario)
            expected[row["id"]] = row["actual"]
        expected[f"worker-{language}"] = next(row["actual"] for row in value["rows"] if row["scenario"] == "panel-dark")
    for directory in paths:
        path = directory / "audit.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert not data["mismatches"]
        files.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for row in data["rows"]:
            assert row["id"] not in observed and row["actual"] == expected[row["id"]]
            observed[row["id"]] = row
    assert set(observed) == set(expected), set(expected) - set(observed)
    return {"adapter_samples": sum(not key.startswith("worker-") for key in observed),
            "worker_samples": sum(key.startswith("worker-") for key in observed),
            "native_spans": sum(row["native_spans"] for row in observed.values()), "files": files}


def markdown(report):
    stats = report["summary"]
    lines = ["# Joint OCR model and settings validation", "",
        f"This follow-up compares {stats['compatible_model_language_pairs']} recognizer/language pairs across all 25 supported languages, including all-catalogue English probes. Every model receives both the previous baseline and the current tuned settings when those differ. {stats['challengers_tuned']} challengers receive a separate settings search.", "",
        f"Fresh validation accepts {stats['model_changes']} model changes and {stats['settings_changes']} settings changes. Source assignments reflect only accepted frozen proposals.", "",
        "## Protocol", "",
        "Initial comparison uses the complete preceding development partition: six authored passages × ten renderings, four interface panels, two negative controls and eighteen color variants (84 selections per language). All compatible models see identical pixels, settings, default confidence floor 0.45 and application reading order/fragment suppression. Shared detector v6 small and orientation classifier v4 mobile remain fixed.", "",
        "An audit of [PaddleOCR's model documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/module_usage/text_recognition.en.md) found that several recognizers labelled for other scripts also support English. The earlier English comparison omitted these. This follow-up therefore probes all 22 catalogue recognizers on English, including models whose full English repertoire is not promised. Seven models' identical development checkpoints are reused; earlier English validation and its frozen choice are discarded. English receives a replacement set of eight fresh passages, and the expanded proposal is frozen again before evaluating that set. Other languages use their documented script-family candidates.", "",
        "For each language, the strongest non-incumbent gets resize/expansion and published-preset screening, then up to two rounds of other controls. A second challenger also gets this search when its initial score is within 0.2 percentage points of the incumbent. The full development set chooses among baseline/current settings and the top three screening alternatives. Incumbents retain the benefit of the preceding comprehensive settings search; this stage checks both their baseline and current settings. This is a bounded joint search, not an exhaustive Cartesian search of every parameter for every model.", "",
        "The proposed model/settings pair is frozen in the result file with a SHA256 fingerprint before any fresh validation inference. Fresh validation evaluates every compatible model with its development-winning settings, including tuned challengers, for a complete comparison; those results never feed another tuning round. Only the single development-selected proposal can replace the incumbent. A runner-up with a better final score is reported without being selected from the holdout.", "",
        "Eight new passages per language cover everyday vocabulary, orthography, a short label, quotation, measurements, technical notation, long context and mixed text. Ten renderings per passage plus three colors per passage, four multi-line layouts and two blank/decorative controls give 110 selections per language (2750 total). All variants of fresh passages stay outside development. The final set adds vocabulary evidence; it shares rendering recipes with development and is not a collection of real desktop captures.", "",
        "The primary score averages seventeen positive scenario CERs: ten font/degradation cases, four layouts and three colors. Each scenario has equal weight; each passage within a scenario has equal weight. NFC and whitespace are normalized; case, accents and punctuation count. Missing text counts as error. The preceding settings report used fourteen scenarios plus a separate color guard, so its percentages are not directly comparable with this report.", "",
        "During development ranking, each negative selection containing hallucinated text adds a 0.10 penalty to balanced CER. This can keep a model with lower positive-text CER from entering the challenger shortlist. Negative results, plain CER and settings are all retained, so this practical selection rule is visible rather than mistaken for a universal model ranking.", "",
        "Acceptance requires at least 0.1 percentage point lower fresh CER, upright regression ≤0.2 points, clean and color regression ≤1 point, and no increase in completely missed positive selections or false-positive negative selections. These practical gates are not statistical significance tests. The limited number of passages/layouts means close rankings remain uncertain.", "",
        "## Fresh validation results", "",
        "[All candidate comparisons](ocr-joint-candidates.md) show baseline, current and development-winning settings scores for each compatible model, followed by fresh validation scores.", "",
        f"Across equally weighted languages, balanced CER changes from {stats['baseline_balanced_cer'] * 100:.3f}% to {stats['selected_balanced_cer'] * 100:.3f}%; upright CER changes from {stats['baseline_upright_cer'] * 100:.3f}% to {stats['selected_upright_cer'] * 100:.3f}%.", "",
        "| Language | Previous → selected recognizer | Fresh CER: previous → selected | Frozen proposal / decision |",
        "|---|---|---:|---|"]
    for name, language in LANGUAGES:
        value = report["languages"][language]
        summary = value["summary"]
        unchanged = summary["proposed"] == {"model": summary["incumbent"], "settings": value["inputs"]["settings"]}
        decision = ("accepted" if summary["accepted"] else "retained (development winner)" if unchanged else
                    "rejected: " + ", ".join(key for key, passed in summary["gates"].items() if not passed))
        lines.append(f"| {name} | {summary['incumbent']} → {summary['selected']['model']} | {summary['baseline']['balanced_cer'] * 100:.3f}% → {summary['selected_metric']['balanced_cer'] * 100:.3f}% | {summary['proposed']['model']}: {decision} |")
    lines += ["", "## Reproducibility and integration", "",
        "[Machine-readable evidence](ocr-joint-benchmark.json) includes every model's initial settings scores, tuning scores, fresh predictions, model checksums, runtime/corpus fingerprints, frozen proposals and acceptance gates. Detailed development predictions and full-precision detector caches remain in ignored artifacts. Recognition caches never cross model instances. Resume rejects changes to protocol, scripts, runtime, corpus pixels and current policy.", "",
        "```powershell",
        ".venv/Scripts/python.exe scripts/verify-ocr-joint.py --output artifacts/ocr-joint",
        ".venv/Scripts/python.exe scripts/verify-ocr-joint-english.py --output artifacts/ocr-joint-english --development-checkpoint artifacts/ocr-joint/en.json",
        ".venv/Scripts/python.exe scripts/report-ocr-joint.py --runs artifacts/ocr-joint artifacts/ocr-joint-english --check-assignments",
        ".venv/Scripts/python.exe scripts/audit-ocr-joint.py --runs artifacts/ocr-joint artifacts/ocr-joint-english",
        "```", "",
        "These commands repeat the search against the policy currently in the checkout. After accepted assignments change, a new run has a different incumbent and fingerprint. The checked-in evidence retains the exact earlier policy and corpus fingerprints; resuming its raw checkpoints against a changed policy is deliberately rejected.", "",
        "Model/settings selection uses the same pipeline as normal inference, with word geometry disabled during bulk scoring. Final adapter checks enable actual word geometry and final worker checks exercise the application subprocess protocol. Timings from concurrent cached runs are not evidence about production speed.", ""]
    if "integration" in report:
        audit = report["integration"]
        lines += [f"The uncached adapter matched {audit['adapter_samples']} representative fresh predictions across all languages. The offline worker matched {audit['worker_samples']} fresh dark panels. Span offsets and geometry were checked for finite, valid coordinates.", ""]
    lines += ["## Limits", "",
        "This establishes the best accepted configuration within this bounded search and rendered-text corpus. It does not establish a universal optimum. Photographs, handwriting, native vertical CJK layouts and broad real-screen fonts/backgrounds remain untested. Some scripts still have substantial error. A rejected proposal or fresh runner-up may have lower aggregate CER while failing a regression gate; the report preserves that evidence.", "",
        "The original Dependency heading has no role in screening, tuning or validation. Its screenshot alone cannot reproduce the original pre-overlay pixels. User settings, confidence preferences and installed assets are not changed by the experiment. Restart from this checkout and run **Check required files** to prepare the current policy.", ""]
    return "\n".join(lines)


def candidate_markdown(report):
    lines = ["# OCR candidate comparisons", "",
        "Development scores choose the proposal before fresh validation. Fresh scores are a check, never another selection/tuning round. All scores are balanced CER across the same seventeen scenarios; lower is better. Current settings are the language's policy before this follow-up, including cases where they equal baseline. A model's development-winning settings include challenger tuning when performed.", ""]
    for name, language in LANGUAGES:
        record = report["languages"][language]
        summary = record["summary"]
        lines += [f"## {name} ({language})", "",
            f"Frozen proposal: **{summary['proposed']['model']}**. Applied policy: **{summary['selected']['model']}**.", "",
            "| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for model, value in record["models"].items():
            baseline = next(result for result in value["initial"] if result["settings"]["id"] == joint.experiment.candidate()["id"])
            current = next((result for result in value["initial"] if result["settings"]["id"] == record["inputs"]["settings"]["id"]), baseline)
            best, fresh = value["development_winner"]["metric"], value["validation"]["metric"]
            lines.append(f"| {model} | {baseline['metric']['balanced_cer'] * 100:.3f}% | {current['metric']['balanced_cer'] * 100:.3f}% | {best['balanced_cer'] * 100:.3f}% | {best['false_positive_samples']} | {fresh['balanced_cer'] * 100:.3f}% | {fresh['upright_cer'] * 100:.3f}% | {fresh['empty']} / {fresh['false_positive_samples']} |")
        lines += ["", "Selected settings:", "", "```json", json.dumps(summary["selected"]["settings"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/ocr-joint-benchmark.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("docs/ocr-joint-selection.md"))
    parser.add_argument("--candidate-output", type=Path, default=Path("docs/ocr-joint-candidates.md"))
    parser.add_argument("--policy-output", type=Path)
    parser.add_argument("--check-assignments", action="store_true")
    parser.add_argument("--audits", type=Path, nargs="+")
    args = parser.parse_args()
    records = load_records(args.runs)
    report = {"protocol": joint.PROTOCOL, "languages": {}, "runs": [str(run) for run in args.runs]}
    changes = {}
    policy_models, policy_settings = ["PROFILES_BY_LANGUAGE = {"], ["SETTINGS_BY_LANGUAGE: dict[str, OcrSettings] = {"]
    defaults = asdict(OcrSettings())
    for _name, language in LANGUAGES:
        record = records[language]
        check_record(record)
        if "runtime" in report and report["runtime"] != record["inputs"]["runtime"]:
            raise ValueError("Mixed inference runtimes")
        report["runtime"] = record["inputs"]["runtime"]
        selected = record["summary"]["selected"]
        setting = settings_report.selected_settings(selected["settings"])
        if profile_for(language).name != selected["model"] or settings_for(language) != setting:
            changes[language] = selected
        generation, script, size = joint.bench.MODELS[selected["model"]]
        policy_models.append(f'    "{language}": OcrProfile({selected["model"]!r}, {generation!r}, {script!r}, {size!r}),')
        controls = ", ".join(f"{key}={value!r}" for key, value in asdict(setting).items() if value != defaults[key])
        policy_settings.append(f'    "{language}": OcrSettings({controls}),')
        models = {}
        for model, value in record["models"].items():
            models[model] = {"assets": value["assets"],
                "initial": [{key: result[key] for key in ("settings", "metric")} for result in value["initial"]],
                "development_winner": {key: value["winner"][key] for key in ("settings", "metric")},
                "validation": value["validation"]}
            if "tuning" in value:
                models[model]["tuning"] = {stage: [{key: result[key] for key in ("settings", "metric")}
                                                     for result in value["tuning"][stage]]
                                           for stage in ("screen", "development")}
        report["languages"][language] = {"summary": record["summary"], "models": models,
            "validation_incumbent": record["validation_incumbent"], "inputs": record["inputs"],
            "identity": record["identity"], "frozen_sha256": record["frozen_sha256"], "source": record["source"]}
    report["summary"] = {
        "compatible_model_language_pairs": sum(len(record["models"]) for record in records.values()),
        "challengers_tuned": sum(len(record["challengers"]) for record in records.values()),
        "model_changes": sum(record["summary"]["selected"]["model"] != record["incumbent"] for record in records.values()),
        "accepted_languages": sum(record["summary"]["accepted"] for record in records.values()),
        "settings_changes": sum(record["summary"]["selected"]["settings"] != record["current"] for record in records.values()),
        "settings_screened": sum(len(value.get("tuning", {}).get("screen", [])) for record in records.values() for value in record["models"].values()),
        "initial_configuration_evaluations": sum(len(value["initial"]) for record in records.values() for value in record["models"].values()),
        "fresh_model_evaluations": sum(len(record["models"]) for record in records.values()),
        "fresh_samples": 25 * 110,
        **{f"{which}_{metric}": mean(record["summary"]["baseline" if which == "baseline" else "selected_metric"][metric]
                                   for record in records.values())
           for which in ("baseline", "selected") for metric in ("balanced_cer", "upright_cer")}}
    if args.audits:
        report["integration"] = audit_evidence(args.audits, records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    args.candidate_output.write_text(candidate_markdown(report), encoding="utf-8")
    if args.policy_output:
        args.policy_output.write_text("\n".join(policy_models + ["}", ""] + policy_settings + ["}", ""]), encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "assignment_changes": changes}, ensure_ascii=False))
    if args.check_assignments and changes:
        raise RuntimeError("Implemented policy differs from accepted frozen proposals")


if __name__ == "__main__":
    main()
