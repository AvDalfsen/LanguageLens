"""Opt-in bundled-runtime checks on fixed samples; never captures the desktop."""
import argparse
from dataclasses import asdict
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-models", action="store_true")
    parser.add_argument("--voices", type=Path)
    parser.add_argument("--with-packs", action="store_true")
    parser.add_argument("--sentence-cases", type=Path)
    args = parser.parse_args()
    checks = []
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont, QFontDatabase, QImage, QPainter
        from PySide6.QtWidgets import QApplication
        from PySide6.QtMultimedia import QMediaPlayer
        from language_lens.config import Settings, settings_path
        from language_lens.services.offline import ocr_models, no_network
        from language_lens.services.process_job import ProcessJob
        from language_lens.text import word_spans
        from language_lens.services.voices import VOICES, voice_runtime_ready
        from language_lens.services.pronunciation import Pronouncer, prepare_japanese

        app = QApplication([])
        # Offscreen Qt does not enumerate the Windows font database automatically.
        font_id = QFontDatabase.addApplicationFont(str(Path(os.environ["SystemRoot"]) / "Fonts/segoeui.ttf"))
        assert font_id >= 0, "Could not load the fixed OCR fixture font"
        player = QMediaPlayer()
        assert all(voice_runtime_ready(voice) for voice in VOICES if voice.phoneme_type != "japanese")
        versions = {name: version(name) for name in ("language-lens", "PySide6", "rapidocr",
                    "onnxruntime", "argostranslate", "minisbd", "piper-tts")}
        checks.append("Qt, multimedia, distribution metadata")
        with no_network():
            assert Pronouncer().prepare_for_spans("Hello", "en-US", [[0, 5]]).words[0].phonemes
            from language_lens.services import language_packs as packs
            if args.with_packs:
                assert all(item["ready"] and item["managed"] for item in packs.inventory())
                assert len(list(word_spans("日本語の文章です", "ja"))) > 1
                assert len(list(word_spans("这是一个测试", "zh"))) > 1
                assert prepare_japanese("こんにちは", [[0, 5]]).words[0].phonemes
                checks.append("External Japanese/Chinese dictionaries and native Japanese pronunciation pack")
            else:
                assert not any(item["ready"] for item in packs.inventory()), "Base check must use empty language-pack storage"
                checks.append("Core runtime operates without optional language packs")
            for language in ("pt", "ja", "zh", "ar"):
                assert ocr_models(language)
        checks.append("English pronunciation and OCR catalogues")

        class Probe(ProcessJob):
            def __init__(self):
                super().__init__()
                self.messages, self.errors, self.success = [], [], False
                self.failed.connect(self.errors.append)

            def _handle_message(self, message, process):
                self.messages.append(message)
                self._touch()

            def _succeeded(self, scratch):
                # Read results before the supervisor removes its temporary files.
                self.success = True
                self.files = {p.name: p.stat().st_size for p in Path(scratch.path()).iterdir()}

        def run(module, command, payload, arguments=(), images=None):
            job = Probe()
            job._start(module, command, payload, settings_path().parent, 120000,
                       arguments=arguments, images=images)
            deadline = time.monotonic() + 150
            while job.active and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            if job.active:
                job.shutdown()
                raise RuntimeError(f"Worker timeout: {command}")
            if not job.success:
                raise RuntimeError(f"Worker failed: {command}: {job.errors}")
            return job

        task = "language_lens.services.task_worker"
        speech = "language_lens.services.speech_worker"
        settings = asdict(Settings(source_language="pt", target_language="en", speech_enabled=False))
        status = run(task, "status", {"settings": settings})
        assert any("result" in event for event in status.messages)
        run(task, "ocr", {"settings": settings, "regions": []})
        root = settings_path().parent / "voices"
        result = run(speech, "pronunciation", {"text": "Hello", "spans": [[0, 5]]},
                     ["--voice", "en_US-lessac-medium", "--root", str(root)])
        assert result.files["pronunciation.json"] > 0
        checks.append("Bundled QProcess task/speech dispatch, JSON protocol, results and scratch cleanup")
        assert not any(name in sys.modules for name in ("torch", "stanza", "spacy"))
        from importlib.util import find_spec
        assert all(find_spec(name) is None for name in ("torch", "stanza", "spacy"))
        checks.append("No Torch/Stanza/spaCy modules in the frozen runtime")
        if args.sentence_cases:
            from language_lens.services import sentence_models
            cases = json.loads(args.sentence_cases.read_text(encoding="utf-8"))
            with no_network():
                for item in cases:
                    text = item.get("separator", " ").join(item["sentences"])
                    actual = sentence_models.split(text, item["language"])
                    # The corpus records three known upstream boundary merges.
                    assert actual == item.get("baseline", item["sentences"]), (item, actual)
            checks.append(f"Offline MiniSBD sentence boundaries in {len(cases)} multilingual samples")
        if args.with_models:
            from language_lens.services.offline import offline_ready
            text = "Olá! Este texto funciona sem internet."
            for target in ("en", "nl"):
                settings["target_language"] = target
                # Refresh old markers through the actual maintenance worker.
                run(task, "prepare", {"settings": settings})
                assert offline_ready("pt", target), f"Preparation did not record readiness for pt-{target}"
                result = run(task, "translate", {"settings": settings, "text": text, "words": ["texto"]})
                assert any(e.get("result", {}).get("sentence") for e in result.messages)
                assert any(e.get("result", {}).get("words", {}).get("texto", {}).get("candidates") for e in result.messages)
                result = run(task, "more", {"settings": settings, "word": "texto"})
                assert any(e.get("result", {}).get("candidates") for e in result.messages)
            image = QImage(1000, 120, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            font = QFont("Segoe UI")
            font.setPixelSize(32)
            painter.setFont(font)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(20, 65, text)
            painter.end()
            result = run(task, "ocr", {"settings": settings, "selection_size": [1000, 120], "regions": [
                {"image": "crop.png", "retry": None, "offset": [0, 0], "size": [1000, 120], "mapping": [0, 0, 1, 1]}]},
                images={"crop.png": image})
            recognized = [line["text"] for e in result.messages for line in e.get("result", [])]
            assert any("texto" in text for text in recognized), f"Fixed OCR sample not recognized: {recognized!r}"
            checks.append("Offline native OCR, direct/pivot translation, word candidates and expanded search")
        if args.voices:
            for voice in ("en_US-lessac-medium", "ja_JP-hi_fi_captain-medium"):
                if voice.startswith("ja") and not args.with_packs:
                    continue
                text = "こんにちは" if voice.startswith("ja") else "Hello from Language Lens."
                result = run(speech, "synthesize", {"text": text},
                             ["--voice", voice, "--root", str(args.voices)])
                assert result.files["selection.wav"] > 44
            checks.append("English/Japanese ONNX voice synthesis" if args.with_packs else "English ONNX voice synthesis")
        print(json.dumps({"ok": True, "checks": checks, "versions": versions}), flush=True)
        return 0
    except Exception:
        import traceback
        traceback.print_exc()
        print(json.dumps({"ok": False, "checks": checks}), flush=True)
        return 1
