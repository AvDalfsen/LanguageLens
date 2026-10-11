"""Opt-in recognizer comparison on identical, rendered multilingual line crops.

Downloads (only with --download) go to the chosen output directory and are
checked against RapidOCR's model catalogue. Inference runs without networking.
No desktop capture, user settings, or installed assets are modified.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
from time import perf_counter
import unicodedata
from urllib.request import Request

import cv2
import numpy as np

from language_lens.config import LANGUAGES, settings_path
from language_lens.services.model_download import urlopen
from language_lens.services.offline import matches, no_network


MODELS = {
    "latin-v3": ("PPOCRV4", "LATIN", "MOBILE"),
    "english-v4": ("PPOCRV4", "EN", "MOBILE"),
    "cyrillic-v3": ("PPOCRV4", "CYRILLIC", "MOBILE"),
    "arabic-v4": ("PPOCRV4", "ARABIC", "MOBILE"),
    "hindi-v4": ("PPOCRV4", "DEVANAGARI", "MOBILE"),
    "korean-v4": ("PPOCRV4", "KOREAN", "MOBILE"),
    "chinese-v4-mobile": ("PPOCRV4", "CH", "MOBILE"),
    "chinese-v4-server": ("PPOCRV4", "CH", "SERVER"),
    "multilingual-v6-tiny": ("PPOCRV6", "CH", "TINY"),
    "latin-v5": ("PPOCRV5", "LATIN", "MOBILE"),
    "english-v5": ("PPOCRV5", "EN", "MOBILE"),
    "cyrillic-v5": ("PPOCRV5", "CYRILLIC", "MOBILE"),
    "east-slavic-v5": ("PPOCRV5", "ESLAV", "MOBILE"),
    "chinese-v5-mobile": ("PPOCRV5", "CH", "MOBILE"),
    "chinese-v5-server": ("PPOCRV5", "CH", "SERVER"),
    "japanese-v4": ("PPOCRV4", "JAPAN", "MOBILE"),
    "multilingual-v6-small": ("PPOCRV6", "CH", "SMALL"),
    "multilingual-v6-medium": ("PPOCRV6", "CH", "MEDIUM"),
    "arabic-v5": ("PPOCRV5", "ARABIC", "MOBILE"),
    "greek-v5": ("PPOCRV5", "EL", "MOBILE"),
    "hindi-v5": ("PPOCRV5", "DEVANAGARI", "MOBILE"),
    "korean-v5": ("PPOCRV5", "KOREAN", "MOBILE"),
}
LATIN = {"cs", "da", "nl", "en", "fi", "fr", "de", "hu", "it", "nb", "pl", "pt", "pb", "ro", "es", "sv", "tr"}
CANDIDATES = {
    **{language: ["latin-v3", "latin-v5", "multilingual-v6-tiny", "multilingual-v6-small", "multilingual-v6-medium"] for language in LATIN},
    "en": ["latin-v3", "latin-v5", "english-v4", "english-v5", "multilingual-v6-tiny", "multilingual-v6-small", "multilingual-v6-medium"],
    "ru": ["cyrillic-v3", "cyrillic-v5", "east-slavic-v5"],
    "uk": ["cyrillic-v3", "cyrillic-v5", "east-slavic-v5"],
    "zh": ["chinese-v4-mobile", "chinese-v4-server", "chinese-v5-mobile", "chinese-v5-server", "multilingual-v6-tiny", "multilingual-v6-small", "multilingual-v6-medium"],
    "ja": ["chinese-v5-mobile", "chinese-v5-server", "japanese-v4", "multilingual-v6-small", "multilingual-v6-medium"],
    "ar": ["arabic-v4", "arabic-v5"], "el": ["greek-v5"], "hi": ["hindi-v4", "hindi-v5"], "ko": ["korean-v4", "korean-v5"],
}
MESSAGE_KEYS = (
    "download_required", "repair_translation", "privacy", "recognized", "select_area", "ipa",
    "hotkey_hint", "ready", "voice_ready", "capture_hint", "files_tip", "source_tip",
    "no_text", "save_failed", "rank_tip", "pronunciation_context", "retry_translation", "ui_tip",
)
HOLDOUT_KEYS = ("ipa_tip", "boundaries", "whole_missing", "hotkey_conflict",
                "quick_capture_instruction", "voice_needed", "pron_mismatch", "pronunciation_sentence_tip")
VARIANTS = (
    ("small-light", 16, False, False, False),
    ("normal-dark", 22, False, True, False),
    ("heading-dark", 30, True, True, False),
    ("serif-light", 22, False, False, True),
)
CHALLENGE_VARIANTS = (
    ("clean-sans", 22, False, False, False),
    ("clean-serif", 22, False, False, True),
    ("monospace", 20, False, False, False),
    ("small-light", 12, False, False, False),
    ("small-dark", 14, False, True, False),
    ("italic-serif", 18, False, False, True),
    ("blurred", 18, False, False, False),
    ("jpeg", 18, False, False, False),
    ("low-contrast", 20, False, False, False),
    ("downscaled", 22, False, False, False),
)


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def distance(first, second):
    if first == second:
        return 0
    # Equal ends do not change edit distance. Most OCR errors are localized;
    # trimming them also keeps multi-line settings sweeps inexpensive.
    prefix = 0
    while prefix < min(len(first), len(second)) and first[prefix] == second[prefix]:
        prefix += 1
    first, second = first[prefix:], second[prefix:]
    suffix = 0
    while suffix < min(len(first), len(second)) and first[-1 - suffix] == second[-1 - suffix]:
        suffix += 1
    if suffix:
        first, second = first[:-suffix], second[:-suffix]
    if not first or not second:
        return max(len(first), len(second))
    previous = list(range(len(second) + 1))
    for i, character in enumerate(first, 1):
        current = [i]
        for j, other in enumerate(second, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (character != other)))
        previous = current
    return previous[-1]


def corpus(output, languages, holdout=False, challenge=False, challenge_path=None):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QTextLayout, QTextOption
    from PySide6.QtWidgets import QApplication
    from language_lens.services.tasks import qimage_to_bgr_array

    app = QApplication.instance() or QApplication([])
    font_files = ("segoeui.ttf", "segoeuib.ttf", "arial.ttf", "arialbd.ttf", "times.ttf", "timesbd.ttf",
                  "msyh.ttc", "msyhbd.ttc", "simsun.ttc", "YuGothR.ttc", "YuGothB.ttc", "msgothic.ttc",
                  "malgun.ttf", "malgunbd.ttf", "Nirmala.ttf", "NirmalaB.ttf")
    for name in font_files:
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    catalog_path = Path(__file__).resolve().parents[1] / "src/language_lens/data/ui-translations.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    challenge_path = challenge_path or Path(__file__).parent / "data/ocr-challenge-texts.json"
    challenge_texts = json.loads(challenge_path.read_text(encoding="utf-8")) if challenge else None
    variants = CHALLENGE_VARIANTS if challenge else VARIANTS
    samples = []
    for language in languages:
        messages = catalog["languages"][language]
        texts = (list(zip(challenge_texts["categories"], challenge_texts["languages"][language])) if challenge else
                 [(key, messages[key]) for key in (HOLDOUT_KEYS if holdout else MESSAGE_KEYS)])
        if not holdout and not challenge:
            texts.append(("mixed-version", "Language Lens v1.2 — 2026-10-11 09:45"))
        if language == "en" and not holdout and not challenge:
            texts.extend([("dependency-heading", "Dependency and download hardening"),
                          ("ambiguous-characters", "I agree: Illusion, download, hardening; 0 O 1 l I.")])
        for key, text in texts:
            text = normalized(text)
            for variant, size, bold, dark, serif in variants:
                family = {"zh": "SimSun" if serif else "Microsoft YaHei",
                          "ja": "MS Gothic" if serif else "Yu Gothic",
                          "ko": "Malgun Gothic", "hi": "Nirmala UI"}.get(language,
                          "Times New Roman" if serif else "Segoe UI")
                if variant == "monospace":
                    family = {"zh": "SimSun", "ja": "MS Gothic", "ko": "Malgun Gothic",
                              "hi": "Nirmala UI", "ar": "Segoe UI"}.get(language, "Consolas")
                font = QFont(family)
                font.setPixelSize(size)
                font.setBold(bold)
                font.setItalic(variant == "italic-serif")
                layout = QTextLayout(text, font)
                option = QTextOption()
                option.setWrapMode(QTextOption.WrapMode.NoWrap)
                option.setTextDirection(Qt.LayoutDirection.LayoutDirectionAuto)
                layout.setTextOption(option)
                layout.beginLayout()
                line = layout.createLine()
                line.setLineWidth(10000)
                layout.endLayout()
                bounds = line.naturalTextRect()
                width, height = int(np.ceil(bounds.width())) + 12, int(np.ceil(line.height())) + 8
                image = QImage(width, height, QImage.Format.Format_RGB888)
                image.fill(QColor(170, 170, 170) if variant == "low-contrast" else
                           QColor(23, 23, 23) if dark else QColor(250, 250, 250))
                painter = QPainter(image)
                painter.setPen(QColor(110, 110, 110) if variant == "low-contrast" else
                               QColor(238, 238, 238) if dark else QColor(20, 20, 20))
                layout.draw(painter, QPointF(6 - bounds.left(), 4))
                painter.end()
                pixels = qimage_to_bgr_array(image)
                if variant == "blurred":
                    pixels = cv2.GaussianBlur(pixels, (3, 3), .65)
                elif variant == "jpeg":
                    ok, compressed = cv2.imencode(".jpg", pixels, [cv2.IMWRITE_JPEG_QUALITY, 35])
                    assert ok
                    pixels = cv2.imdecode(compressed, cv2.IMREAD_COLOR)
                elif variant == "downscaled":
                    pixels = cv2.resize(pixels, None, fx=.65, fy=.65, interpolation=cv2.INTER_AREA)
                sample_id = f"{language}-{key}-{variant}"
                sample = {"id": sample_id, "language": language, "text": text, "variant": variant,
                          "category": key, "font": family, "size": size, "pixels": pixels}
                samples.append(sample)
                if key in {"download_required", "dependency-heading", "no_text", "diacritics", "names", "technical"}:
                    directory = output / "previews"
                    directory.mkdir(exist_ok=True)
                    cv2.imwrite(str(directory / f"{sample_id}.png"), pixels)
    manifest = [{key: value for key, value in sample.items() if key != "pixels"} for sample in samples]
    (output / "corpus.json").write_text(json.dumps({"catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        "challenge_sha256": hashlib.sha256(challenge_path.read_bytes()).hexdigest() if challenge else None,
        "variants": variants, "samples": manifest}, indent=2, ensure_ascii=False), encoding="utf-8")
    return samples, app


def model_config(model_id, output, download, model_cache=None):
    from rapidocr import LangRec, ModelType, OCRVersion
    from rapidocr.main import DEFAULT_CFG_PATH, root_dir
    from rapidocr.utils.parse_parameters import ParseParams
    from rapidocr.inference_engine.base import FileInfo, InferSession
    from rapidocr.utils.typings import EngineType, TaskType

    generation, language, size = MODELS[model_id]
    params = {"Rec.ocr_version": getattr(OCRVersion, generation), "Rec.lang_type": getattr(LangRec, language),
              "Rec.model_type": getattr(ModelType, size), "Global.log_level": "critical",
              "EngineConfig.onnxruntime.intra_op_num_threads": 2,
              "EngineConfig.onnxruntime.inter_op_num_threads": 1}
    cfg = ParseParams.update_batch(ParseParams.load(DEFAULT_CFG_PATH), params)
    rec = cfg.Rec
    info = InferSession.get_model_url(FileInfo(EngineType.ONNXRUNTIME, rec.ocr_version, TaskType.REC,
                                             rec.lang_type, rec.model_type))
    name, digest = Path(info["model_dir"]).name, info["SHA256"]
    directory = model_cache or output / "models"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    if not matches(path, digest):
        existing = next((candidate for candidate in (root_dir / "models" / name,
                         settings_path().parent / "offline/ocr" / name) if matches(candidate, digest)), None)
        temporary = path.with_suffix(".part")
        try:
            if existing:
                shutil.copyfile(existing, temporary)
            elif download:
                print(f"Downloading {model_id}: {name}", flush=True)
                with urlopen(Request(info["model_dir"], headers={"User-Agent": "LanguageLens-OCR-validation"}), timeout=60) as response, temporary.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
            else:
                raise FileNotFoundError(f"Missing {name}; pass --download to fetch into {directory}.")
            if not matches(temporary, digest):
                raise ValueError(f"Model checksum mismatch: {name}")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    rec.engine_cfg = cfg.EngineConfig.onnxruntime
    rec.model_path = str(path)
    rec.model_root_dir = str(directory)
    rec.font_path = None
    return rec, {"file": name, "sha256": digest, "url": info["model_dir"], "bytes": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-models"))
    parser.add_argument("--model-cache", type=Path, help="Reuse verified models across separate result directories.")
    parser.add_argument("--languages", nargs="*", default=[code for _name, code in LANGUAGES])
    parser.add_argument("--models", nargs="*", default=list(MODELS))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--holdout", action="store_true", help="Use disjoint messages to check the initial ranking.")
    parser.add_argument("--challenge", action="store_true", help="Use diverse original language passages with ten clean and degraded renderings.")
    parser.add_argument("--pipeline", action="store_true", help="Check assigned models with detection, rotation and word geometry enabled.")
    parser.add_argument("--neutral-detection", action="store_true", help="In pipeline checks only, use max-side 736 and unclip 1.0 to isolate crop expansion.")
    args = parser.parse_args()
    if args.holdout and args.challenge:
        parser.error("Choose either --holdout or --challenge.")
    args.output.mkdir(parents=True, exist_ok=True)
    from rapidocr.utils.log import logger
    logger.setLevel("CRITICAL")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if args.pipeline:
        verify_pipeline(args)
        return
    configs = {}
    for model_id in args.models:
        configs[model_id] = model_config(model_id, args.output, args.download, args.model_cache)
        print(f"Verified {model_id}", flush=True)
    if args.prepare_only:
        return
    samples, app = corpus(args.output, args.languages, args.holdout, args.challenge)
    from rapidocr.ch_ppocr_rec import TextRecognizer, TextRecInput
    results = {"runtime": {name: version(name) for name in ("rapidocr", "onnxruntime", "python-bidi", "PySide6", "opencv-python")},
               "method": "recognition-only, identical complete row crops; NFC and whitespace normalized; case/punctuation retained",
               "partition": "challenge" if args.challenge else "holdout" if args.holdout else "initial", "models": {}, "summary": {}}
    for model_id, (cfg, info) in configs.items():
        subset = [sample for sample in samples if model_id in CANDIDATES[sample["language"]]]
        if not subset:
            continue
        rows = []
        with no_network():
            started = perf_counter()
            recognizer = TextRecognizer(cfg)
            load_seconds = perf_counter() - started
            recognizer(TextRecInput(img=subset[0]["pixels"], return_word_box=False))
            for language in args.languages:
                selected = [sample for sample in subset if sample["language"] == language]
                if not selected:
                    continue
                start = perf_counter()
                result = recognizer(TextRecInput(img=[sample["pixels"] for sample in selected], return_word_box=False))
                elapsed = perf_counter() - start
                for sample, actual, confidence in zip(selected, result.txts, result.scores):
                    reference, hypothesis = normalized(sample["text"]), normalized(actual)
                    rows.append({"id": sample["id"], "language": language, "variant": sample["variant"],
                                 "category": sample["category"], "reference": reference,
                                 "actual": hypothesis, "edits": distance(reference, hypothesis),
                                 "characters": len(reference), "exact": reference == hypothesis,
                                 "confidence": float(confidence)})
                group = rows[-len(selected):]
                metric = {"samples": len(group), "edits": sum(row["edits"] for row in group),
                          "characters": sum(row["characters"] for row in group),
                          "exact": sum(row["exact"] for row in group),
                          "milliseconds_per_line": round(1000 * elapsed / len(group), 3)}
                metric["cer"] = round(metric["edits"] / metric["characters"], 6)
                metric["mean_line_cer"] = round(sum(row["edits"] / row["characters"] for row in group) / len(group), 6)
                metric["by_variant"] = {variant: {
                    "cer": round(sum(row["edits"] for row in group if row["variant"] == variant) /
                                 sum(row["characters"] for row in group if row["variant"] == variant), 6),
                    "mean_line_cer": round(sum(row["edits"] / row["characters"] for row in group if row["variant"] == variant) /
                                           sum(row["variant"] == variant for row in group), 6),
                    "exact": sum(row["exact"] for row in group if row["variant"] == variant),
                } for variant in sorted({row["variant"] for row in group})}
                results["summary"].setdefault(language, {})[model_id] = metric
                print(json.dumps({"model": model_id, "language": language,
                                  **{key: value for key, value in metric.items() if key != "by_variant"}}), flush=True)
            del recognizer
        gc.collect()
        results["models"][model_id] = {**info, "load_seconds": round(load_seconds, 3), "rows": rows}
        (args.output / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def verify_pipeline(args):
    from language_lens.domain import reading_order
    from language_lens.services.ocr import RapidOcrEngine
    from language_lens.services.offline import ocr_models, ocr_parameters
    from language_lens.services.ocr_profiles import profile_for

    samples, app = corpus(args.output, args.languages)
    directory = args.model_cache or args.output / "models"
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for language in args.languages:
        params = ocr_parameters(language)
        if args.neutral_detection:
            params.update({"Det.limit_type": "max", "Det.limit_side_len": 736, "Det.unclip_ratio": 1.0})
        for section, installed, _url, digest, existing in ocr_models(language):
            path = directory / installed.name
            if not matches(path, digest):
                source = next((item for item in (installed, existing) if matches(item, digest)), None)
                if source is None:
                    raise FileNotFoundError(f"Missing verified pipeline asset {path.name}. Prepare assets first.")
                shutil.copyfile(source, path)
            params[f"{section}.model_path"] = str(path)
        subset = [sample for sample in samples if sample["language"] == language and (
            (sample["id"].endswith("select_area-small-light")) or
            (sample["id"].endswith("select_area-heading-dark")) or
            (sample["id"].endswith("no_text-normal-dark")) or
            ("dependency-heading" in sample["id"]))]
        with no_network():
            engine = RapidOcrEngine(language, params=params)
            for sample in subset:
                start = perf_counter()
                lines = reading_order(engine.recognize(sample["pixels"]), language)
                actual = normalized(" ".join(line.text for line in lines))
                native_spans = sum(len(line.span_boxes) for line in lines)
                rows.append({"id": sample["id"], "language": language,
                             "model": profile_for(language).name, "reference": sample["text"],
                             "actual": actual, "edits": distance(sample["text"], actual),
                             "lines": len(lines), "native_spans": native_spans,
                             "milliseconds": round(1000 * (perf_counter() - start), 3)})
                assert all(0 <= box.start < box.end <= len(line.text)
                           for line in lines for box in line.span_boxes)
                print(json.dumps({key: value for key, value in rows[-1].items()
                                  if key not in {"reference", "actual"}}, ensure_ascii=True), flush=True)
            del engine
        gc.collect()
        (args.output / "pipeline.json").write_text(json.dumps({
            "method": "assigned model; production detection/classification/confidence defaults; offline inference",
            "detection_overrides": {key: value for key, value in params.items() if key.startswith("Det.") and key != "Det.model_path"},
            "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    if any(not row["lines"] for row in rows):
        raise RuntimeError("Pipeline returned no text for a rendered sample; see pipeline.json.")


if __name__ == "__main__":
    main()
