"""Reproduce adopted upright policies through production inference, offline.

Requires the separately retained benchmark corpus/assets, never downloads them.
Writes a workspace-local asset cache, leaving the user's prepared files alone.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(text):
    import unicodedata
    return " ".join(unicodedata.normalize("NFC", text).split())


def frozen_hash(path):
    """Verify the benchmark's canonical JSON seal (excluding its own seal)."""
    value = load(path)
    payload = {key: item for key, item in value.items() if key != "frozen_sha256"}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert digest == value["frozen_sha256"], path
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--languages", nargs="+")
    args = parser.parse_args()
    root, output = args.benchmark.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(output / "appdata")
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QGuiApplication
    from language_lens.config import Settings
    from language_lens.domain import reading_order, build_word_hits
    from language_lens.services import offline
    from language_lens.services.tasks import OcrTask, create_ocr_engine
    from language_lens.services.ocr_profiles import policy_identity, profile_for
    from language_lens.services.ocr_settings import settings_for

    app = QGuiApplication.instance() or QGuiApplication(["upright-production-audit"])
    evidence = load(Path(__file__).resolve().parents[1] / "docs/ocr-upright-policy-evidence.json")
    assert frozen_hash(root / "final-policy.json") == evidence["benchmark_policy_sha256"]
    assert frozen_hash(root / "full-v6-manifest.json") == evidence["corpus_sha256"]
    adoption = {row["language"]: row for row in evidence["languages"]}
    samples = load(root / "full-v6-manifest.json")["samples"]
    asset_records = load(root / "comparison-assets.json")
    tess_records = load(root / "tesseract-models.json")["models"]
    # comparison-assets is the RapidOCR catalogue list; some unused rows have no path.
    assets = {row["sha256"]: Path(row["path"]) for row in asset_records if row.get("path")}
    assets.update({row["sha256"]: root / row["path"] for row in tess_records})
    result = {"policy_sha256": policy_identity(), "languages": {}, "differences": []}
    for language in args.languages or adoption:
        selected = adoption[language]["selected"]
        recorded = load(root / "predictions" / "final" / f"{language}-final-{selected}.json")
        expected = {row["id"]: row for row in recorded["rows"]}
        for _section, destination, _url, digest, _existing in offline.ocr_models(language):
            source = assets[digest]
            assert offline.matches(source, digest), source
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not offline.matches(destination, digest):
                shutil.copyfile(source, destination)
        counts = {"rows": 0, "matched": 0, "native_word_boxes": 0,
                  "native_hover_verified": 0,
                  "model": profile_for(language).name, "settings": asdict(settings_for(language))}
        with offline.no_network():
            engine = create_ocr_engine(Settings(source_language=language))
            for sample in samples:
                if sample["id"] not in expected:
                    continue
                crop = root / sample["crop"]
                assert hashlib.sha256(crop.read_bytes()).hexdigest() == sample["crop_sha256"]
                image = QImage(str(crop))
                retry, offset = None, QPoint()
                if sample.get("image") and sample.get("selection_xyxy"):
                    source = QImage(str(root / sample["image"]))
                    x, y, right, bottom = sample["selection_xyxy"]
                    padding = max(16, min(48, round(min(right-x, bottom-y) * .35)))
                    px, py = max(0, x-padding), max(0, y-padding)
                    pr, pb = min(source.width(), right+padding), min(source.height(), bottom+padding)
                    retry = source.copy(px, py, pr-px, pb-py)
                    offset = QPoint(px-x, py-y)
                task = OcrTask(image, Settings(source_language=language), retry_image=retry,
                               retry_offset=offset)
                lines = reading_order(task.recognize(engine, lambda _message: None), language)
                actual = normalized(" ".join(line.text for line in lines))
                reference = normalized(expected[sample["id"]]["actual"])
                counts["rows"] += 1
                counts["native_word_boxes"] += sum(len(line.span_boxes) for line in lines)
                # Exercise the actual hover builder as well as native geometry.
                hits = build_word_hits(lines, language)
                if profile_for(language).backend == "tesseract":
                    offset = 0
                    for line in lines:
                        for span in line.span_boxes:
                            hit = next(h for h in hits if h.source_start == offset + span.start
                                       and h.source_end == offset + span.end)
                            xs, ys = zip(*span.polygon)
                            assert abs(hit.bounds.x - min(xs)) < 1e-6
                            assert abs(hit.bounds.y - min(ys)) < 1e-6
                            assert abs(hit.bounds.width - (max(xs)-min(xs))) < 1e-6
                            assert abs(hit.bounds.height - (max(ys)-min(ys))) < 1e-6
                            counts["native_hover_verified"] += 1
                        offset += len(line.text) + 1
                if actual == reference:
                    counts["matched"] += 1
                else:
                    result["differences"].append({"language": language, "id": sample["id"],
                                                  "expected": reference, "actual": actual})
            del engine
        result["languages"][language] = counts
        (output / "audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(language, counts["matched"], "/", counts["rows"], flush=True)
    assert not result["differences"], result["differences"]
    assert app is not None


if __name__ == "__main__":
    main()
