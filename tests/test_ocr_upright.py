"""Pipeline regression checks for upright profile adoption and native geometry."""
from types import SimpleNamespace
import sys
import json
from pathlib import Path

import numpy as np
import pytest
import rapidocr

from language_lens.config import Settings
from language_lens.domain import build_word_hits
from language_lens.services import offline
from language_lens.services.ocr import RapidOcrEngine, create_engine
from language_lens.services.ocr_settings import confidence_for
from language_lens.services.tesseract_ocr import TesseractOcrEngine, russian_parameters


def test_every_language_uses_its_recorded_adoption_controls():
    from dataclasses import asdict
    from language_lens.config import LANGUAGES
    from language_lens.services.ocr_profiles import profile_for
    from language_lens.services.ocr_settings import OcrSettings, settings_for
    evidence = json.loads((Path(__file__).resolve().parents[1] /
                           "docs/ocr-upright-policy-evidence.json").read_text(encoding="utf-8"))
    assert {row["language"] for row in evidence["languages"]} == {code for name, code in LANGUAGES}
    for row in evidence["languages"]:
        language, recorded = row["language"], row["profile"]
        if recorded["engine"] == "tesseract":
            assert profile_for(language).backend == "tesseract"
            params = russian_parameters()
            assert all(params[key] == recorded[key] for key in ("scale", "psm", "variables", "preprocessing"))
            continue
        assert profile_for(language).name == recorded["model"]
        values = {**asdict(OcrSettings()), **recorded["settings"],
                  "scale": recorded["scale"], "confidence": recorded["floor"],
                  "rec_batch_num": recorded.get("rec_batch_num", 6)}
        for key, value in recorded["parameter_overrides"].items():
            if key == "Global.min_height": values["min_height"] = value
            elif key == "Global.min_side_len": values["min_side_len"] = value
            elif key == "Rec.rec_img_shape": values["rec_min_width"] = value[2]
            else: pytest.fail(f"Unverified adopted override: {key}")
        actual = asdict(settings_for(language))
        for key, expected in values.items():
            if isinstance(expected, float): assert actual[key] == pytest.approx(expected)
            else: assert actual[key] == expected


def test_scaled_recognition_maps_lines_and_character_boxes_to_source(monkeypatch):
    inputs = []
    box = ((4, 6), (44, 6), (44, 26), (4, 26))
    def construct(**_kwargs):
        def recognize(image, **kwargs):
            inputs.append(image)
            return SimpleNamespace(boxes=[box], txts=["كتاب"], scores=[.59], word_results=None)
        return recognize
    monkeypatch.setattr(rapidocr, "RapidOCR", construct)
    engine = RapidOcrEngine("ar")
    image = np.zeros((20, 60, 3), dtype=np.uint8)
    assert engine.recognize(image) == []  # the measured Arabic floor is .6
    line = engine.recognize(image, .5)[0]
    assert inputs[0].shape == (40, 120, 3)
    assert line.polygon == ((2, 3), (22, 3), (22, 13), (2, 13))


def test_native_character_geometry_is_scaled_with_its_line(monkeypatch):
    box = ((4, 6), (44, 6), (44, 26), (4, 26))
    result = SimpleNamespace(boxes=[box], txts=["Hej"], scores=[.99],
                             word_results=[(("Hej", .99, box),)])
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda **kw: lambda *a, **k: result)
    line = RapidOcrEngine("sv").recognize(np.zeros((20, 60, 3), dtype=np.uint8))[0]
    assert line.span_boxes[0].polygon == line.polygon
    assert line.bounds.width == 20


@pytest.mark.parametrize("language,expected", [("ar", .6), ("en", .6), ("ko", .3), ("fr", .45)])
def test_default_floor_is_per_language_and_custom_floor_is_preserved(language, expected):
    assert confidence_for(language, Settings().min_ocr_confidence) == expected
    assert confidence_for(language, .7) == .7


def test_tesseract_assets_are_verified_before_backend_construction(monkeypatch, tmp_path):
    from language_lens.services.errors import KnownTaskError
    monkeypatch.setattr(offline, "assets_root", lambda: tmp_path)
    assets = offline.ocr_models("ru")
    assert {section for section, *_rest in assets} == {"rus", "eng"}
    assert all("tessdata_best/" in url for _section, _path, url, _hash, _existing in assets)
    with pytest.raises(KnownTaskError):
        offline.local_ocr_parameters("ru")
    monkeypatch.setattr(offline, "matches", lambda path, digest: True)
    params = offline.local_ocr_parameters("ru")
    assert params["tessdata_path"] == str(tmp_path / "ocr" / "tessdata-best")
    assert params["language"] == "rus+eng"


def test_russian_backend_preserves_native_order_and_punctuated_word_hover(monkeypatch):
    records = [("Привет,", (20, 60, 100, 80)), ("мир!", (140, 10, 180, 30))]
    class Iterator:
        index = 0
        def GetUTF8Text(self, level): return records[self.index][0]
        def BoundingBox(self, level): return records[self.index][1]
        def Next(self, level):
            self.index += 1
            return self.index < len(records)
    configuration, images = [], []
    class Native:
        def __init__(self, **kwargs): configuration.append(kwargs)
        def ClearAdaptiveClassifier(self): pass
        def SetImage(self, image): images.append(np.asarray(image))
        def GetUTF8Text(self): return "Привет,\nмир!\n"
        def GetIterator(self): return Iterator()
        def MeanTextConf(self): return 95
    monkeypatch.setitem(sys.modules, "tesserocr", SimpleNamespace(
        PyTessBaseAPI=Native, OEM=SimpleNamespace(LSTM_ONLY=1), RIL=SimpleNamespace(WORD=3)))
    params = {**russian_parameters(), "tessdata_path": "fixture"}
    engine = create_engine("ru", params=params)
    assert isinstance(engine, TesseractOcrEngine)
    image = np.full((50, 100, 3), (240, 180, 40), dtype=np.uint8)
    lines = engine.recognize(image, .99)
    assert lines[0].text == "Привет,\nмир!"  # geometry must not reorder native sparse text
    assert configuration[0]["variables"]["thresholding_method"] == "2"
    assert tuple(images[0][0, 0]) == (40, 180, 240)  # BGR input -> RGB native pixels
    assert images[0].shape == (100, 200, 3)
    hits = build_word_hits(lines, "ru")
    assert [hit.text for hit in hits] == ["Привет", "мир"]
    assert (hits[0].bounds.x, hits[0].bounds.y, hits[0].bounds.width) == (10, 30, 40)
    assert (hits[1].bounds.x, hits[1].bounds.y, hits[1].bounds.width) == (70, 5, 20)


def test_native_blank_policy_does_not_run_unmeasured_padded_fallback(qapp):
    from PySide6.QtGui import QImage
    from language_lens.services.tasks import OcrTask
    image = QImage(50, 20, QImage.Format.Format_RGB888)
    image.fill(0)
    calls = []
    class EmptyNative:
        supports_empty_retry = False
        def recognize(self, image, confidence):
            calls.append(image.shape)
            return []
    task = OcrTask(image, Settings(source_language="ru"), retry_image=image)
    assert task.recognize(EmptyNative(), lambda message: pytest.fail(message)) == []
    assert len(calls) == 1
