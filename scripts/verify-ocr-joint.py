"""Offline joint recognizer/settings comparison; fresh final passages stay frozen.

All compatible recognizers get identical baseline/current development inputs.
The strongest non-incumbent (and a second competitive challenger) receive the
same settings search as the preceding experiment. Selection is frozen before
any fresh validation inference. This never changes user settings or assets.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import gc
import hashlib
import importlib.util
from importlib.metadata import version
import json
import os
from pathlib import Path
from time import perf_counter

import cv2

from language_lens.config import LANGUAGES
from language_lens.services.ocr_profiles import OcrProfile, profile_for
from language_lens.services.ocr_settings import settings_for
from language_lens.services.offline import matches, no_network, ocr_models

spec = importlib.util.spec_from_file_location("settings_benchmark", Path(__file__).with_name("verify-ocr-settings.py"))
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)
bench = experiment.bench
FRESH_TEXTS = Path(__file__).parent / "data/ocr-joint-validation-texts.json"
PROTOCOL = "joint-v1-all-compatible-two-settings-full-development-frozen-fresh-validation"


def canonical(value):
    parameters = {key: setting for key, setting in value["parameters"].items()
                  if setting != experiment.BASE.get(key) and key != "Global.use_cls"}
    return experiment.candidate(parameters, value["use_cls"], value["preprocessing"])


def current_settings(language):
    settings = settings_for(language)
    return canonical(experiment.candidate(settings.parameters(), settings.use_cls, settings.preprocessing))


def fresh_corpus(output, languages):
    directory = output / "fresh-rendered"
    directory.mkdir(parents=True, exist_ok=True)
    samples, app = bench.corpus(directory, languages, challenge=True, challenge_path=FRESH_TEXTS)
    rows = [{**sample, "partition": "fresh-validation", "scenario": sample["variant"], "negative": False}
            for sample in samples]
    for language in languages:
        group = [row for row in rows if row["language"] == language]
        categories = list(dict.fromkeys(row["category"] for row in group))
        layouts = (("panel-light", "small-light", (0, 1, 2), False, False, False, True),
                   ("panel-dark", "small-dark", (3, 4, 5), True, False, False, True),
                   ("close-lines", "clean-serif", (5, 6, 7), False, True, False, False),
                   ("rotated-180", "small-light", (0, 4, 6), False, False, True, False))
        for scenario, variant, indexes, dark, tight, rotated, clutter in layouts:
            selected = [next(row for row in group if row["category"] == categories[index] and row["variant"] == variant)
                        for index in indexes]
            rows.append({"id": f"fresh-{language}-{scenario}", "language": language,
                         "partition": "fresh-validation", "scenario": scenario, "negative": False,
                         "category": f"layout-{scenario}",
                         "text": bench.normalized(" ".join(row["text"] for row in (selected[::-1] if rotated else selected))),
                         "pixels": experiment.compose(selected, dark, tight, rotated, clutter)})
        for scenario in ("blank", "decorations"):
            import numpy as np
            image = np.full((144, 420, 3), 26, dtype=np.uint8)
            if scenario == "decorations":
                cv2.rectangle(image, (15, 20), (140, 120), (100, 100, 100), 2)
                cv2.circle(image, (210, 70), 28, (100, 100, 100), 3)
                cv2.line(image, (270, 30), (380, 100), (100, 100, 100), 3)
            rows.append({"id": f"fresh-{language}-{scenario}", "language": language,
                         "partition": "fresh-validation", "scenario": scenario,
                         "category": scenario, "negative": True, "text": "", "pixels": image})
        rows.extend(experiment.color_checks(group))
    manifest = [{**{key: value for key, value in row.items() if key != "pixels"},
                 "shape": list(row["pixels"].shape), "pixel_sha256": experiment.tensor_key(row["pixels"])} for row in rows]
    experiment.write_json(output / "fresh-corpus.json", manifest)
    return rows, app


def engine_for(language, model, args):
    from rapidocr import RapidOCR
    generation, script, size = bench.MODELS[model]
    params = {**OcrProfile(model, generation, script, size).parameters(), **experiment.BASE}
    _cfg, info = bench.model_config(model, args.output, False, args.model_cache)
    params["Rec.model_path"] = str(args.model_cache / info["file"])
    assets = [{"section": "Rec", **info}]
    for section, installed, url, digest, _existing in ocr_models(language):
        if section == "Rec":
            continue
        path = args.model_cache / installed.name
        if not matches(path, digest):
            raise FileNotFoundError(f"Missing verified {path}")
        params[f"{section}.model_path"] = str(path)
        assets.append({"section": section, "file": installed.name, "sha256": digest, "url": url})
    engine = RapidOCR(params=params)
    # Separate cache namespace per shared model hash; no recognizer cache crosses models.
    digest = next(asset["sha256"] for asset in assets if asset["section"] == "Det")
    engine.text_det.session = experiment.CachedSession(engine.text_det.session, args.output / f"detector-{digest}", capacity=24)
    engine.text_cls.session = experiment.CachedSession(engine.text_cls.session, capacity=1024)
    engine.text_rec = experiment.CachedRecognizer(engine.text_rec)
    return engine, assets


def result_rank(result):
    metric = result["metric"]
    return (metric["balanced_cer"] + .1 * metric["false_positive_samples"],
            len(result["settings"]["parameters"]) + int(result["settings"]["preprocessing"] != "none"),
            result["settings"]["id"])


def tune(engine, language, development, seeds):
    screen = []
    for index, scenario in enumerate(dict.fromkeys(row["scenario"] for row in development)):
        group = [row for row in development if row["scenario"] == scenario]
        screen.append(group[index % len(group)])
    results, seen = [], set()
    for settings in [*seeds, *experiment.coarse_candidates(language)]:
        settings = canonical(settings)
        if settings["id"] not in seen:
            seen.add(settings["id"])
            results.append(experiment.evaluate(engine, settings, screen))
    for _round in range(2):
        anchor = min(results, key=result_rank)["settings"]
        for settings in experiment.neighbours(anchor):
            settings = canonical(settings)
            if settings["id"] not in seen:
                seen.add(settings["id"])
                results.append(experiment.evaluate(engine, settings, screen))
        if min(results, key=result_rank)["settings"]["id"] == anchor["id"]:
            break
    finalists = {setting["id"]: setting for setting in seeds}
    for result in sorted(results, key=result_rank)[:3]:
        finalists[result["settings"]["id"]] = result["settings"]
    full = [experiment.evaluate(engine, setting, development) for setting in finalists.values()]
    winner = min(full, key=result_rank)
    # Gray is only supported if it changes training inputs. Remove a no-op
    # transformation before validating colored captures.
    if winner["settings"]["preprocessing"] == "gray" and all(
            experiment.tensor_key(row["pixels"]) == experiment.tensor_key(experiment.transform(row["pixels"], "gray"))
            for row in development):
        settings = canonical({**winner["settings"], "preprocessing": "none"})
        winner = experiment.evaluate(engine, settings, development)
        full.append(winner)
    return {"screen": results, "development": full, "winner": winner}


def gates(old, new):
    colors = ("blue-light", "red-light", "green-dark")
    color_old = sum(old["scenario_cer"][name] for name in colors) / 3
    color_new = sum(new["scenario_cer"][name] for name in colors) / 3
    return {"cer_improves": new["balanced_cer"] < old["balanced_cer"] - .001,
            "upright_safe": new["upright_cer"] <= old["upright_cer"] + .002,
            "clean_safe": new["clean_cer"] <= old["clean_cer"] + .01,
            "color_safe": color_new <= color_old + .01,
            "empty_safe": new["empty"] <= old["empty"],
            "negative_safe": new["false_positive_samples"] <= old["false_positive_samples"]}


def fingerprint(language, rows, fresh, incumbent, settings):
    value = {"protocol": PROTOCOL, "runtime": {name: version(name) for name in
             ("rapidocr", "onnxruntime", "python-bidi", "opencv-python", "PySide6")},
             "language": language, "incumbent": incumbent, "settings": settings,
             "models": {model: bench.MODELS[model] for model in bench.CANDIDATES[language]},
             "shared_models": [(section, digest) for section, _path, _url, digest, _other in ocr_models(language) if section != "Rec"],
             "development": [(row["id"], row["text"], experiment.tensor_key(row["pixels"])) for row in rows],
             "validation": [(row["id"], row["text"], experiment.tensor_key(row["pixels"])) for row in fresh],
             "scripts": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                         (Path(__file__), Path(__file__).with_name("verify-ocr-settings.py"), Path(__file__).with_name("verify-ocr-models.py"))}}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(), value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-joint"))
    parser.add_argument("--model-cache", type=Path, default=Path("artifacts/ocr-models/models"))
    parser.add_argument("--languages", nargs="+", default=[code for _name, code in LANGUAGES])
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    previous, app = experiment.make_corpus(args.output, args.languages)
    fresh, app = fresh_corpus(args.output, args.languages)
    # Fresh passages may share individual words, never whole normalized lines.
    assert not {row["text"] for row in fresh if row["text"]} & {row["text"] for row in previous if row["text"]}
    summary = {"protocol": PROTOCOL, "languages": {}}
    for language in args.languages:
        development = [row for row in previous if row["language"] == language and row["partition"] == "development"]
        development += experiment.color_checks(development)
        validation = [row for row in fresh if row["language"] == language]
        incumbent, current = profile_for(language).name, current_settings(language)
        identity, inputs = fingerprint(language, development, validation, incumbent, current)
        path = args.output / f"{language}.json"
        if args.resume and path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["identity"] != identity:
                raise ValueError(f"Protocol/runtime/corpus/policy changed for {language}")
            if "summary" in record:
                summary["languages"][language] = record["summary"]
                experiment.write_json(args.output / "summary.json", summary)
                continue
        else:
            record = {"language": language, "identity": identity, "inputs": inputs,
                      "incumbent": incumbent, "current": current, "models": {}}
        started = perf_counter()
        seeds = list({value["id"]: value for value in (experiment.candidate(), current)}.values())
        with no_network():
            for model in bench.CANDIDATES[language]:
                if "initial" in record["models"].get(model, {}):
                    continue
                engine, assets = engine_for(language, model, args)
                initial = [experiment.evaluate(engine, setting, development) for setting in seeds]
                record["models"][model] = {"assets": assets, "initial": initial,
                                            "winner": min(initial, key=result_rank)}
                experiment.write_json(path, record)
                print(json.dumps({"language": language, "model": model, "stage": "initial-development",
                                  "scores": [value["metric"]["balanced_cer"] for value in initial]}), flush=True)
                del engine
                gc.collect()
            ranked = sorted((model for model in record["models"] if model != incumbent),
                            key=lambda model: result_rank(record["models"][model]["winner"]))
            challengers = ranked[:1]
            if len(ranked) > 1 and record["models"][ranked[1]]["winner"]["metric"]["balanced_cer"] <= \
                    record["models"][incumbent]["winner"]["metric"]["balanced_cer"] + .002:
                challengers.append(ranked[1])
            record["challengers"] = challengers
            for model in challengers:
                if "tuning" in record["models"][model]:
                    continue
                engine, _assets = engine_for(language, model, args)
                tuning = tune(engine, language, development, seeds)
                record["models"][model]["tuning"] = tuning
                record["models"][model]["winner"] = tuning["winner"]
                experiment.write_json(path, record)
                print(json.dumps({"language": language, "model": model, "stage": "challenger-tuned",
                                  "settings": tuning["winner"]["settings"], "metric": tuning["winner"]["metric"]}), flush=True)
                del engine
                gc.collect()
            proposed = min(record["models"], key=lambda model: (
                result_rank(record["models"][model]["winner"])[0], model != incumbent,
                result_rank(record["models"][model]["winner"])[1:]))
            frozen = {"model": proposed, "settings": record["models"][proposed]["winner"]["settings"]}
            if "frozen" in record and record["frozen"] != frozen:
                raise ValueError("Selection changed after validation began")
            record["frozen"] = frozen
            record["frozen_sha256"] = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
            experiment.write_json(path, record)  # Commit choice before validation.
            for model, value in record["models"].items():
                if "validation" in value:
                    continue
                engine, _assets = engine_for(language, model, args)
                value["validation"] = experiment.evaluate(engine, value["winner"]["settings"], validation)
                if model == incumbent:
                    record["validation_incumbent"] = (copy.deepcopy(value["validation"])
                        if value["winner"]["settings"]["id"] == current["id"] else
                        experiment.evaluate(engine, current, validation))
                experiment.write_json(path, record)
                print(json.dumps({"language": language, "model": model, "stage": "fresh-validation",
                                  "metric": value["validation"]["metric"]}), flush=True)
                del engine
                gc.collect()
        old = record["validation_incumbent"]["metric"]
        new = record["models"][proposed]["validation"]["metric"]
        gate_values = gates(old, new)
        accepted = all(gate_values.values())
        record["summary"] = {"incumbent": incumbent, "proposed": frozen, "accepted": accepted,
                             "gates": gate_values,
                             "selected": frozen if accepted else {"model": incumbent, "settings": current},
                             "baseline": old, "candidate": new, "selected_metric": new if accepted else old,
                             "development_samples": len(development), "validation_samples": len(validation),
                             "compatible_models": len(record["models"]), "challengers": challengers}
        record["elapsed_seconds_this_process"] = round(perf_counter() - started, 3)
        experiment.write_json(path, record)
        summary["languages"][language] = record["summary"]
        experiment.write_json(args.output / "summary.json", summary)
        print(json.dumps({"language": language, "stage": "complete", **record["summary"]}), flush=True)
    experiment.write_json(args.output / "summary.json", summary)


if __name__ == "__main__":
    main()
