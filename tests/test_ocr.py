from pathlib import PurePosixPath

import pytest
import rapidocr
from rapidocr.inference_engine.base import FileInfo, InferSession
from rapidocr.utils.typings import EngineType, TaskType

from language_lens.config import LANGUAGES
from language_lens.services.ocr import RapidOcrEngine


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
