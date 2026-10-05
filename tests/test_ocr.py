from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest
import rapidocr
from rapidocr.inference_engine.base import FileInfo, InferSession
from rapidocr.utils.typings import EngineType, TaskType

from language_lens.config import LANGUAGES
from language_lens.services.ocr import RapidOcrEngine, _attach_boxes
from language_lens.domain import OcrLine, build_word_hits


@pytest.mark.parametrize("source_language", [code for _name, code in LANGUAGES])
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


def test_japanese_uses_the_multilingual_ppocrv5_recognizer(monkeypatch):
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
    assert PurePosixPath(model["model_dir"]).name == "ch_PP-OCRv5_rec_mobile.onnx"


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
    lines = RapidOcrEngine("en").recognize(object())
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
    lines = RapidOcrEngine("ar").recognize(object())
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
    recognized = RapidOcrEngine(source).recognize(object())[0]
    assert recognized.token_spans is not None
    assert [text[start:end] for start, end in recognized.token_spans] == expected
