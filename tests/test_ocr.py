from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest
import rapidocr
import numpy as np
from rapidocr.inference_engine.base import FileInfo, InferSession
from rapidocr.utils.typings import EngineType, TaskType

from language_lens.config import LANGUAGES
from language_lens.services.ocr import RapidOcrEngine, _attach_boxes
from language_lens.services import offline
from language_lens.services.ocr_profiles import PROFILES_BY_LANGUAGE
from language_lens.services.ocr_settings import OcrSettings, SETTINGS_BY_LANGUAGE
from language_lens.domain import OcrLine, build_word_hits


@pytest.mark.parametrize("source_language", [code for _name, code in LANGUAGES
                                          if PROFILES_BY_LANGUAGE[code].backend == "rapidocr"])
def test_offered_language_resolves_to_an_available_recognition_model(
    monkeypatch, source_language
):
    resolved = []

    def validate_configuration(*, params):
        # Exercise the installed model catalogue without downloading models or
        # constructing inference sessions.
        resolved.append(
            InferSession.get_model_url(
                FileInfo(
                    engine_type=EngineType.ONNXRUNTIME,
                    ocr_version=params["Rec.ocr_version"],
                    task_type=TaskType.REC,
                    lang_type=params["Rec.lang_type"],
                    model_type=params["Rec.model_type"],
                )
            )
        )

    monkeypatch.setattr(rapidocr, "RapidOCR", validate_configuration)

    RapidOcrEngine(source_language)

    assert resolved[0]["model_dir"].endswith(".onnx")
    prepared = next(model for model in offline.ocr_models(source_language) if model[0] == "Rec")
    assert prepared[2:4] == (resolved[0]["model_dir"], resolved[0]["SHA256"])


def test_every_offered_language_has_an_explicit_model_assignment():
    assert set(PROFILES_BY_LANGUAGE) == {code for _name, code in LANGUAGES}
    assert set(SETTINGS_BY_LANGUAGE) == {code for _name, code in LANGUAGES}


def test_language_settings_reach_both_inference_and_offline_preparation(monkeypatch):
    from language_lens.services import ocr_settings
    selected = OcrSettings(det_limit_type="max", unclip_ratio=1.0,
                           cls_thresh=.8, use_cls=False, rec_min_width=64,
                           preprocessing="dark-invert")
    monkeypatch.setitem(ocr_settings.SETTINGS_BY_LANGUAGE, "en", selected)
    configurations, calls, inputs = [], [], []
    def construct(*, params):
        configurations.append(params)
        def recognize(image, **kwargs):
            calls.append(kwargs)
            inputs.append(image)
            return SimpleNamespace(boxes=None, txts=None, scores=None)
        return recognize
    monkeypatch.setattr(rapidocr, "RapidOCR", construct)
    image = np.full((32, 96, 3), 20, dtype=np.uint8)
    RapidOcrEngine("en").recognize(image)
    assert all(configurations[0][key] == value for key, value in selected.parameters().items())
    assert configurations[0] == offline.ocr_parameters("en")
    assert calls[0]["use_cls"] is False
    assert np.array_equal(inputs[0], 255 - image)


def test_preprocessing_keeps_original_coordinates_and_bgr_layout():
    from language_lens.services.ocr_settings import preprocess_image
    dark = np.full((32, 96, 3), 20, dtype=np.uint8)
    dark[10:20, 10:80] = (220, 210, 200)
    inverted = preprocess_image(dark, "dark-invert")
    assert inverted.shape == dark.shape and inverted.dtype == dark.dtype
    assert np.array_equal(inverted, 255 - dark)
    light = 255 - dark
    assert preprocess_image(light, "dark-invert") is light
    for mode in ("gray", "contrast"):
        result = preprocess_image(dark, mode)
        assert result.shape == dark.shape and result.dtype == np.uint8
    assert preprocess_image(dark, "none") is dark
    with pytest.raises(ValueError):
        preprocess_image(dark, "invalid")


def test_japanese_uses_the_tested_multilingual_ppocrv6_recognizer(monkeypatch):
    configurations = []
    monkeypatch.setattr(
        rapidocr, "RapidOCR", lambda *, params: configurations.append(params)
    )

    RapidOcrEngine("ja")

    params = configurations[0]
    model = InferSession.get_model_url(
        FileInfo(
            engine_type=EngineType.ONNXRUNTIME,
            ocr_version=params["Rec.ocr_version"],
            task_type=TaskType.REC,
            lang_type=params["Rec.lang_type"],
            model_type=params["Rec.model_type"],
        )
    )
    assert PurePosixPath(model["model_dir"]).name == "PP-OCRv6_rec_small.onnx"


def polygon(x, y, width, height=20):
    return ((x, y), (x + width, y), (x + width, y + height), (x, y + height))


def test_native_boxes_are_requested_and_kept_for_proportional_text(monkeypatch):
    calls = []
    result = SimpleNamespace(
        boxes=[polygon(10, 20, 70)], txts=["iii WWW"], scores=[.99],
        word_results=[tuple((text, .99, polygon(x, 20, width)) for text, x, width in [
            ("i", 10, 2), ("i", 12, 2), ("i", 14, 2),
            ("W", 22, 12), ("W", 34, 12), ("W", 46, 12),
        ])],
    )
    def recognize(_image, **kwargs):
        calls.append(kwargs)
        return result
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda **kwargs: recognize)
    lines = RapidOcrEngine("en").recognize(np.zeros((32, 96, 3), dtype=np.uint8))
    assert calls[0]["return_word_box"] and calls[0]["return_single_char_box"]
    hits = build_word_hits(lines, "en")
    assert hits[0].bounds.width == 6 and hits[1].bounds.width == 36


def test_box_groups_are_matched_by_geometry_when_line_indexes_are_missing():
    lines = [OcrLine("same", .99, polygon(10, 20, 80)),
             OcrLine("same", .99, polygon(10, 100, 80))]
    mapped = _attach_boxes(lines, [(('same', .99, polygon(10, 100, 80)),)])
    assert not mapped[0].span_boxes
    assert mapped[1].span_boxes[0].polygon == polygon(10, 100, 80)


def test_mismatched_or_partial_native_text_uses_the_fallback():
    line = OcrLine("same same", .99, polygon(10, 20, 180))
    assert not _attach_boxes([line], [(('same', .99, polygon(110, 20, 60)),)])[0].span_boxes
    assert not _attach_boxes([line], [(('different', .99, polygon(10, 20, 180)),)])[0].span_boxes


def test_native_alignment_maps_composed_glyph_to_decomposed_source():
    line = OcrLine("e\u0301", .99, polygon(10, 20, 20))
    mapped = _attach_boxes([line], [(('é', .99, polygon(10, 20, 20)),)])[0]
    assert [(box.start, box.end) for box in mapped.span_boxes] == [(0, 2)]


def test_rtl_source_does_not_use_upstream_ltr_character_projection(monkeypatch, qapp):
    calls = []
    def recognize(_image, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(boxes=[polygon(10, 20, 200)], txts=["هذا كتاب"], scores=[.99],
                               word_results=[(('هذا كتاب', .99, polygon(10, 20, 200)),)])
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda **kwargs: recognize)
    lines = RapidOcrEngine("ar").recognize(np.zeros((32, 96, 3), dtype=np.uint8))
    assert not calls[0]["return_word_box"] and not lines[0].span_boxes
    hits = build_word_hits(lines, "ar")
    assert hits[0].bounds.x > hits[1].bounds.x


@pytest.mark.parametrize("source,text,expected", [
    ("ja", "私は本を読みます。", ["私", "は", "本", "を", "読み", "ます"]),
    ("zh", "我喜欢学习中文。", ["我", "喜欢", "学习", "中文"]),
])
def test_ocr_prepares_dictionary_spans_before_ui_work(monkeypatch, source, text, expected):
    result = SimpleNamespace(boxes=[polygon(10, 20, 300)], txts=[text], scores=[.99])
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda **kwargs: lambda *a, **kw: result)
    recognized = RapidOcrEngine(source).recognize(np.zeros((32, 96, 3), dtype=np.uint8))[0]
    assert recognized.token_spans is not None
    assert [text[start:end] for start, end in recognized.token_spans] == expected


@pytest.mark.parametrize("source,text", [("ja", "私は本を読みます。"), ("zh", "我喜欢学习中文。")])
def test_ocr_skips_dictionary_when_lookup_is_disabled(monkeypatch, source, text):
    from language_lens.services import language_packs
    result = SimpleNamespace(boxes=[polygon(10, 20, 300)], txts=[text], scores=[.99])
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda **kwargs: lambda *a, **kw: result)
    monkeypatch.setattr(language_packs, "activate", lambda *_: pytest.fail("Disabled lookup loaded a dictionary"))
    recognized = RapidOcrEngine(source, dictionary_lookup=False).recognize(np.zeros((32, 96, 3), dtype=np.uint8))[0]
    assert [text[start:end] for start, end in recognized.token_spans] == [text[:-1]]
