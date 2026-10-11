"""Opt-in, offline settings search with fixed recognizers and disjoint validation.

Uses authored public text only. Detector probability maps and recognition
outputs are cached without rounding, so postprocessing sweeps avoid redundant
inference. User captures, settings and installed assets are never modified.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
import copy
import gc
import hashlib
import importlib.util
from importlib.metadata import version
import json
import os
from pathlib import Path
from time import perf_counter
import zipfile

import cv2
import numpy as np

from language_lens.config import LANGUAGES
from language_lens.domain import OcrLine, suppress_contained_ocr_fragments
from language_lens.services.offline import matches, no_network, ocr_models
from language_lens.services.ocr_profiles import profile_for

spec = importlib.util.spec_from_file_location("model_benchmark", Path(__file__).with_name("verify-ocr-models.py"))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

# Explicit previous application settings, independent of future policy changes.
BASE = {
    "Det.limit_type": "min", "Det.limit_side_len": 736,
    "Det.unclip_ratio": 1.6, "Det.thresh": .3, "Det.box_thresh": .5,
    "Det.use_dilation": True, "Det.score_mode": "fast",
    "Global.use_preprocess_img": True, "Global.min_side_len": 30,
    "Global.max_side_len": 2000, "Global.use_vertical_padding": True,
    "Global.min_height": 30, "Global.width_height_ratio": 8,
    "Global.text_score": .35, "Cls.cls_thresh": .9,
    "Rec.rec_img_shape": [3, 48, 320], "Rec.rec_batch_num": 6,
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def tensor_key(array):
    digest = hashlib.sha256()
    digest.update(str((array.shape, array.dtype.str)).encode())
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


class CachedSession:
    def __init__(self, original, directory=None, capacity=8):
        self.original, self.directory, self.capacity = original, directory, capacity
        self.memory = OrderedDict()
        self.hits = self.misses = 0
        self.shapes = set()
        if directory:
            directory.mkdir(parents=True, exist_ok=True)

    def __call__(self, tensor):
        self.shapes.add(tuple(tensor.shape))
        key = tensor_key(tensor)
        if key in self.memory:
            self.hits += 1
            self.memory.move_to_end(key)
            return self.memory[key]
        path = self.directory / f"{key}.npz" if self.directory else None
        result = None
        if path and path.exists():
            try:
                with np.load(path) as archive:
                    result = archive["prediction"]
                self.hits += 1
            except (EOFError, OSError, ValueError, zipfile.BadZipFile):
                pass  # An interrupted older run may have left a partial cache.
        if result is None:
            self.misses += 1
            result = self.original(tensor)
            if path:
                temporary = path.with_suffix(f".{os.getpid()}.part")
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                    with archive.open("prediction.npy", "w") as handle:
                        np.lib.format.write_array(handle, result, allow_pickle=False)
                temporary.replace(path)
        self.memory[key] = result
        while len(self.memory) > self.capacity:
            self.memory.popitem(last=False)
        return result


class CachedRecognizer:
    def __init__(self, original):
        self.original = original
        self.cache = {}
        self.hits = self.misses = 0

    def __call__(self, args):
        from rapidocr.ch_ppocr_rec import TextRecOutput
        images = [args.img] if isinstance(args.img, np.ndarray) else args.img
        key = (tuple(self.original.rec_image_shape), self.original.rec_batch_num,
               tuple(tensor_key(image) for image in images))
        if key not in self.cache:
            self.misses += 1
            result = self.original(args)
            self.cache[key] = (result.txts, result.scores, result.word_results)
        else:
            self.hits += 1
        texts, scores, words = self.cache[key]
        return TextRecOutput(images, texts, scores, words, 0.)


def compose(samples, dark=False, tight=False, rotated=False, clutter=False):
    """Combine actual rendered rows; their text order is the ground truth."""
    background = 23 if dark else 250
    margin, gap = (4, 2) if tight else (28, 12)
    width = max(sample["pixels"].shape[1] for sample in samples) + margin * 2
    height = sum(sample["pixels"].shape[0] for sample in samples) + gap * (len(samples) - 1) + margin * 2
    image = np.full((height, width, 3), background, dtype=np.uint8)
    top = margin
    for sample in samples:
        pixels = sample["pixels"]
        if dark and sample["variant"] not in {"small-dark", "normal-dark", "heading-dark"}:
            pixels = 255 - pixels
        h, w = pixels.shape[:2]
        image[top:top + h, margin:margin + w] = pixels
        top += h + gap
    if clutter:
        color = (90, 90, 90) if dark else (175, 175, 175)
        cv2.rectangle(image, (1, 1), (width - 2, height - 2), color, 1)
        cv2.line(image, (3, height - 5), (width - 4, height - 5), color, 1)
    if rotated:
        image = cv2.rotate(image, cv2.ROTATE_180)
    return image


def make_corpus(output, languages):
    directory = output / "rendered"
    directory.mkdir(parents=True, exist_ok=True)
    challenge, app = bench.corpus(directory, languages, challenge=True)
    ui_directory = output / "ui"
    ui_directory.mkdir(exist_ok=True)
    # New messages, disjoint from the model-comparison UI partitions.
    previous_keys = bench.MESSAGE_KEYS
    bench.MESSAGE_KEYS = ("intro", "footer", "target_tip", "capture_tip", "voice_tip", "maintenance_tip", "pron_note", "getting_started")
    ui, _ = bench.corpus(ui_directory, languages)
    bench.MESSAGE_KEYS = previous_keys
    ui = [sample for sample in ui if sample["category"] not in {"mixed-version", "dependency-heading", "ambiguous-characters"}]
    rows = []
    for language in languages:
        selected = [sample for sample in challenge if sample["language"] == language]
        categories = list(dict.fromkeys(sample["category"] for sample in selected))
        # Text categories, not renderings, are split to prevent text leakage.
        for partition, indexes in (("development", range(0, 12, 2)), ("validation", range(1, 12, 2))):
            subset = [sample for sample in selected if categories.index(sample["category"]) in indexes]
            for sample in subset:
                rows.append({**sample, "id": f"{partition}-{sample['id']}", "partition": partition,
                             "scenario": sample["variant"], "negative": False})
            selected_ui = [sample for sample in ui if sample["language"] == language]
            keys = list(dict.fromkeys(sample["category"] for sample in selected_ui))
            chosen_keys = keys[:4] if partition == "development" else keys[4:]
            layouts = (
                ("panel-light", "small-light", False, False, False, True),
                ("panel-dark", "normal-dark", True, False, False, True),
                ("close-lines", "serif-light", False, True, False, False),
                ("rotated-180", "small-light", False, False, True, False),
            )
            for scenario, variant, dark, tight, rotated, clutter in layouts:
                group = [next(sample for sample in selected_ui if sample["category"] == key and sample["variant"] == variant)
                         for key in chosen_keys[:3]]
                rows.append({"id": f"{partition}-{language}-{scenario}", "language": language,
                             "partition": partition, "scenario": scenario, "negative": False,
                             # The app reads physical rows top-to-bottom; an
                             # upside-down panel reverses their physical order.
                             "text": bench.normalized(" ".join(sample["text"] for sample in (group[::-1] if rotated else group))),
                             "pixels": compose(group, dark, tight, rotated, clutter)})
            for scenario in ("blank", "decorations"):
                image = np.full((144, 420, 3), 245 if partition == "development" else 26, dtype=np.uint8)
                if scenario == "decorations":
                    color = (100, 100, 100)
                    cv2.rectangle(image, (15, 20), (140, 120), color, 2)
                    cv2.circle(image, (210, 70), 28, color, 3)
                    cv2.line(image, (270, 30), (380, 100), color, 3)
                rows.append({"id": f"{partition}-{language}-{scenario}", "language": language,
                             "partition": partition, "scenario": scenario, "negative": True,
                             "text": "", "pixels": image})
    preview = output / "previews"
    preview.mkdir(exist_ok=True)
    manifest = []
    for sample in rows:
        pixels = sample["pixels"]
        manifest.append({**{key: value for key, value in sample.items() if key != "pixels"},
                         "shape": list(pixels.shape), "pixel_sha256": tensor_key(pixels)})
        if sample["scenario"] in {"panel-light", "close-lines", "rotated-180"}:
            cv2.imwrite(str(preview / f"{sample['id']}.png"), pixels)
    write_json(output / "corpus.json", manifest)
    return rows, app


def apply_settings(engine, candidate):
    from rapidocr.ch_ppocr_det.utils import DBPostProcess
    config = {**BASE, **candidate["parameters"]}
    for key, value in config.items():
        section, field = key.split(".")
        engine.cfg[section][field] = value
    engine.min_height = config["Global.min_height"]
    engine.width_height_ratio = config["Global.width_height_ratio"]
    engine.min_side_len = config["Global.min_side_len"]
    engine.max_side_len = config["Global.max_side_len"]
    engine.text_det.limit_type = config["Det.limit_type"]
    engine.text_det.limit_side_len = config["Det.limit_side_len"]
    engine.text_det.postprocess_op = DBPostProcess(**{field: config[f"Det.{field}"] for field in
        ("thresh", "box_thresh", "unclip_ratio", "use_dilation", "score_mode")})
    engine.text_cls.cls_thresh = config["Cls.cls_thresh"]
    engine.text_rec.original.rec_image_shape = config["Rec.rec_img_shape"]
    engine.text_rec.original.rec_batch_num = config["Rec.rec_batch_num"]


def transform(image, name):
    if name == "dark-invert":
        border = np.concatenate((image[0], image[-1], image[:, 0], image[:, -1]))
        return 255 - image if float(np.median(border)) < 128 else image
    if name == "gray":
        return cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    if name == "contrast":
        low, high = np.percentile(image, (1, 99))
        if high - low >= 10:
            return np.clip((image.astype(np.float32) - low) * 255 / (high - low), 0, 255).astype(np.uint8)
    return image


def color_checks(samples):
    """Unseen color renderings, with unchanged public ground-truth passages."""
    output = []
    settings = (("blue-light", (180, 80, 25), (250, 250, 250)),
                ("red-light", (25, 35, 180), (250, 250, 250)),
                ("green-dark", (90, 225, 150), (28, 20, 14)))
    for name, foreground, background in settings:
        for source in (sample for sample in samples if sample["scenario"] == "clean-sans"):
            gray = cv2.cvtColor(source["pixels"], cv2.COLOR_BGR2GRAY)
            # Coverage from the antialiased monochrome rendering; preserve layout.
            amount = np.clip((gray.astype(np.float32) - 20) / 230, 0, 1)[..., None]
            pixels = np.round(np.array(foreground) * (1 - amount) + np.array(background) * amount).astype(np.uint8)
            output.append({**source, "id": f"{source['id']}-color-{name}", "scenario": name, "pixels": pixels})
    return output


def candidate(parameters=None, use_cls=True, preprocessing="none"):
    value = {"parameters": parameters or {}, "use_cls": use_cls, "preprocessing": preprocessing}
    value["id"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:12]
    return value


def metric(rows):
    positive = [row for row in rows if not row["negative"]]
    scenarios = sorted({row["scenario"] for row in positive})
    scenario_cer = {name: sum(row["cer"] for row in positive if row["scenario"] == name) /
                    sum(row["scenario"] == name for row in positive) for name in scenarios}
    clean = {"clean-sans", "clean-serif", "monospace", "panel-light", "panel-dark"}
    clean_names = [name for name in scenarios if name in clean] or scenarios
    upright_names = [name for name in scenarios if name != "rotated-180"]
    return {"balanced_cer": sum(scenario_cer.values()) / len(scenarios), "scenario_cer": scenario_cer,
            "upright_cer": sum(scenario_cer[name] for name in upright_names) / len(upright_names),
            "clean_cer": sum(scenario_cer[name] for name in clean_names) / len(clean_names),
            "exact": sum(row["exact"] for row in positive), "positive_samples": len(positive),
            "empty": sum(not row["actual"] for row in positive),
            "false_positive_samples": sum(bool(row["actual"]) for row in rows if row["negative"])}


def evaluate(engine, settings, samples):
    apply_settings(engine, settings)
    rows = []
    for sample in samples:
        started = perf_counter()
        result = engine(transform(sample["pixels"], settings["preprocessing"]), use_det=True,
                        use_cls=settings["use_cls"], use_rec=True, return_word_box=False,
                        return_single_char_box=False, text_score=0.)
        # Same application confidence floor and duplicate suppression.
        floor = max(.45, settings["parameters"].get("Global.text_score", .35))
        lines = [OcrLine(str(text).strip(), float(score), tuple(tuple(float(v) for v in point) for point in box))
                 for box, text, score in zip(result.boxes if result.boxes is not None else [],
                                             result.txts if result.txts is not None else [],
                                             result.scores if result.scores is not None else [])
                 if str(text).strip() and float(score) >= floor]
        ordered = suppress_contained_ocr_fragments(lines, sample["language"])
        actual = bench.normalized(" ".join(line.text for line in ordered))
        reference = bench.normalized(sample["text"])
        edits = bench.distance(reference, actual)
        rows.append({"id": sample["id"], "scenario": sample["scenario"], "negative": sample["negative"],
                     "reference": reference, "actual": actual, "edits": edits, "characters": len(reference),
                     "cer": edits / len(reference) if reference else None, "exact": reference == actual,
                     "lines": len(lines), "milliseconds": round((perf_counter() - started) * 1000, 3)})
    return {"settings": settings, "metric": metric(rows), "rows": rows}


PUBLISHED_PRESETS = {
    "rapidocr-maintainer-v6": {"Det.limit_side_len": 64, "Det.use_dilation": False,
                              "Det.box_thresh": .6, "Det.unclip_ratio": 1.5},
    "paddle-v6-small": {"Det.limit_side_len": 64, "Det.use_dilation": False,
                        "Det.thresh": .2, "Det.box_thresh": .45, "Det.unclip_ratio": 1.4},
    "paddle-v6-small-upscaled": {"Det.limit_side_len": 256, "Det.use_dilation": False,
                                 "Det.thresh": .2, "Det.box_thresh": .45, "Det.unclip_ratio": 1.4},
    "paddle-high-resolution-960": {"Det.limit_side_len": 960, "Det.use_dilation": False,
                                   "Det.box_thresh": .5, "Det.unclip_ratio": 1.5},
    "paddle-high-resolution-1216": {"Det.limit_side_len": 1216, "Det.use_dilation": False,
                                    "Det.box_thresh": .5, "Det.unclip_ratio": 1.5},
}


def coarse_candidates(language):
    result = [candidate()]
    for kind, side in (("max", 736), ("min", 64), ("min", 128), ("min", 256), ("min", 384)):
        for unclip in (1.0, 1.3, 1.6, 2.0):
            result.append(candidate({"Det.limit_type": kind, "Det.limit_side_len": side,
                                     "Det.unclip_ratio": unclip}))
    result.append(candidate({"Det.unclip_ratio": 1.0}))
    result.extend(candidate(parameters) for parameters in PUBLISHED_PRESETS.values())
    if language == "ar":
        # PaddleOCR maintainer guidance for fragmented Arabic line detection.
        result.extend(candidate({"Det.limit_type": "max", "Det.unclip_ratio": value}) for value in (2.5, 3.0))
    return result


def neighbours(best):
    parameters = best["parameters"]
    variations = ({"Det.thresh": .2}, {"Det.thresh": .4}, {"Det.box_thresh": .35},
                  {"Det.box_thresh": .65}, {"Det.use_dilation": False}, {"Det.score_mode": "slow"},
                  {"Global.width_height_ratio": 16}, {"Global.width_height_ratio": -1},
                  {"Global.use_vertical_padding": False}, {"Cls.cls_thresh": .8}, {"Cls.cls_thresh": .98},
                  {"Rec.rec_img_shape": [3, 48, 64]}, {"Rec.rec_img_shape": [3, 48, 640]},
                  {"Global.text_score": .6}, {"Global.text_score": .75})
    return ([candidate({**parameters, **change}, best["use_cls"], best["preprocessing"]) for change in variations]
            + [candidate(parameters, False, best["preprocessing"])]
            + [candidate(parameters, best["use_cls"], transform_name) for transform_name in ("dark-invert", "gray", "contrast")])


def rank(results):
    # Blank hallucinations receive a large penalty during screening, and a
    # separate no-regression gate on the untouched validation partition.
    return sorted(results, key=lambda result: (result["metric"]["balanced_cer"] +
                  .1 * result["metric"]["false_positive_samples"],
                  len(result["settings"]["parameters"]) +
                  int(result["settings"]["preprocessing"] != "none") +
                  int(not result["settings"]["use_cls"]), result["settings"]["id"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-settings"))
    parser.add_argument("--model-cache", type=Path, default=Path("artifacts/ocr-models/models"))
    parser.add_argument("--languages", nargs="*", default=[code for _name, code in LANGUAGES])
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from rapidocr import RapidOCR
    rows, app = make_corpus(args.output, args.languages)
    baseline = candidate()
    summary = {"runtime": {name: version(name) for name in ("rapidocr", "onnxruntime", "python-bidi", "opencv-python", "PySide6")},
               "base_parameters": BASE, "published_presets": PUBLISHED_PRESETS,
               "method": "fixed assigned models; complete pipeline; disjoint text categories; 14 equally weighted positive scenarios",
               "languages": {}}
    for language in args.languages:
        path = args.output / f"{language}.json"
        if args.resume and path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("model") != profile_for(language).name:
                raise ValueError(f"Selected model changed for {language}")
            summary["languages"][language] = record["summary"]
            continue
        params = {**profile_for(language).parameters(), **BASE}
        assets = []
        for section, installed, url, digest, _existing in ocr_models(language):
            model = args.model_cache / installed.name
            if not matches(model, digest):
                raise FileNotFoundError(f"Missing verified {model}")
            params[f"{section}.model_path"] = str(model)
            assets.append({"section": section, "sha256": digest, "file": installed.name, "url": url})
        development = [row for row in rows if row["language"] == language and row["partition"] == "development"]
        validation = [row for row in rows if row["language"] == language and row["partition"] == "validation"]
        # One passage per degradation plus every layout and negative example.
        screen = []
        variants = list(dict.fromkeys(row["scenario"] for row in development))
        for index, variant in enumerate(variants):
            group = [row for row in development if row["scenario"] == variant]
            screen.append(group[index % len(group)])
        record = {"language": language, "model": profile_for(language).name, "assets": assets, "screen": [], "development": []}
        started = perf_counter()
        with no_network():
            engine = RapidOCR(params=params)
            engine.text_det.session = CachedSession(engine.text_det.session, args.output / "detector-cache", capacity=24)
            engine.text_cls.session = CachedSession(engine.text_cls.session, capacity=1024)
            engine.text_rec = CachedRecognizer(engine.text_rec)
            seen = set()
            for settings in coarse_candidates(language):
                record["screen"].append(evaluate(engine, settings, screen))
                seen.add(settings["id"])
                print(json.dumps({"language": language, "stage": "resize-expansion", "candidate": settings["id"],
                                  **record["screen"][-1]["metric"]}), flush=True)
            for round_number in range(2):
                anchor = rank(record["screen"])[0]["settings"]
                for settings in neighbours(anchor):
                    if settings["id"] in seen:
                        continue
                    record["screen"].append(evaluate(engine, settings, screen))
                    seen.add(settings["id"])
                    print(json.dumps({"language": language, "stage": f"other-controls-{round_number + 1}", "candidate": settings["id"],
                                      **record["screen"][-1]["metric"]}), flush=True)
                if rank(record["screen"])[0]["settings"]["id"] == anchor["id"]:
                    break
            finalists = [baseline]
            for result in rank(record["screen"]):
                if result["settings"]["id"] not in {value["id"] for value in finalists}:
                    finalists.append(result["settings"])
                if len(finalists) == 4:
                    break
            for settings in finalists:
                record["development"].append(evaluate(engine, settings, development))
                print(json.dumps({"language": language, "stage": "full-development", "candidate": settings["id"],
                                  **record["development"][-1]["metric"]}), flush=True)
            winner = rank(record["development"])[0]["settings"]
            record["validation_baseline"] = evaluate(engine, baseline, validation)
            record["validation_candidate"] = (copy.deepcopy(record["validation_baseline"]) if winner["id"] == baseline["id"]
                                               else evaluate(engine, winner, validation))
            old = record["validation_baseline"]["metric"]
            new = record["validation_candidate"]["metric"]
            gates = {"cer_improves": new["balanced_cer"] < old["balanced_cer"] - .001,
                     "upright_text_safe": new["upright_cer"] <= old["upright_cer"] + .002,
                     "clean_text_safe": new["clean_cer"] <= old["clean_cer"] + .01,
                     "empty_safe": new["empty"] <= old["empty"],
                     "negatives_safe": new["false_positive_samples"] <= old["false_positive_samples"]}
            accepted = all(gates.values())
            record["summary"] = {"model": record["model"], "screened_settings": len(record["screen"]),
                                 "development_candidates": len(record["development"]), "accepted": accepted, "gates": gates,
                                 "selected": winner if accepted else baseline, "proposed": winner,
                                 "baseline": old, "candidate": new, "selected_metric": new if accepted else old}
            record["cache"] = {"detector_hits": engine.text_det.session.hits, "detector_misses": engine.text_det.session.misses,
                               "recognition_hits": engine.text_rec.hits, "recognition_misses": engine.text_rec.misses,
                               "detector_input_shapes": sorted(engine.text_det.session.shapes)}
            del engine
        record["elapsed_seconds"] = round(perf_counter() - started, 3)
        write_json(path, record)
        summary["languages"][language] = record["summary"]
        write_json(args.output / "summary.json", summary)
        print(json.dumps({"language": language, "stage": "complete", "seconds": record["elapsed_seconds"],
                          **record["summary"]}), flush=True)
        gc.collect()
    write_json(args.output / "summary.json", summary)


if __name__ == "__main__":
    main()
