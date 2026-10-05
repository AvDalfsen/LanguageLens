import json
from pathlib import Path
import time
import unicodedata

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest

from language_lens.config import Settings, load_settings, save_settings
from language_lens.domain import OcrLine, WordTranslation, build_word_hits
from language_lens.services.pronunciation import SpokenUnit, align_units
from language_lens.services.ipa import STRESS, format_ipa
from language_lens.services.speech import SpeechJob, SpeechPlayer
from language_lens.services.voices import VOICES
from language_lens.ui import review


def line(text):
    return OcrLine(text, .99, ((0, 0), (600, 0), (600, 40), (0, 40)))


def wait_for_job(app, job, timeout=20):
    deadline = time.monotonic() + timeout
    while job.active and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    if job.active:
        job.shutdown()
        pytest.fail("Pronunciation worker did not finish")


def test_ipa_is_opt_in_and_saved_separately_from_audio(tmp_path):
    assert not Settings().show_ipa
    path = tmp_path / "settings.json"
    expected = Settings(show_ipa=True, speech_enabled=False)
    save_settings(expected, path)
    assert load_settings(path) == expected


def test_occurrence_offsets_preserve_whitespace_emoji_and_combining_accents():
    lines = [line(" 🙂 I record a record. "), line(""), line("  avo\u0301 e avo\u0302. ")]
    text = " ".join(item.text for item in lines)
    hits = build_word_hits(lines)
    assert all(text[hit.source_start:hit.source_end] == hit.text for hit in hits)
    repeated = [hit for hit in hits if hit.text == "record"]
    assert len(repeated) == 2 and repeated[0].source_start != repeated[1].source_start
    assert [hit.lookup_text for hit in hits[-3:]] == ["avó", "e", "avô"]


def test_ambiguous_native_word_boundaries_are_never_claimed_as_context():
    aligned, matches, reasons = align_units("of a problem", ("əvə prɑbləm",), [
        SpokenUnit(0, 2, "əvə"), SpokenUnit(5, 7, "prɑbləm"),
    ])
    assert matches and set(aligned) == {2} and set(reasons) == {0, 1}
    aligned, matches, _ = align_units("cat dog", ("kat dɔɡ",), [
        SpokenUnit(0, 3, "dɔɡ"), SpokenUnit(4, 3, "kat"),
    ])
    assert not matches and not aligned


@pytest.mark.parametrize("voice", VOICES, ids=lambda voice: voice.locale)
def test_real_worker_maps_each_occurrence_without_an_audio_model(qapp, tmp_path, voice):
    pytest.importorskip("piper.espeakbridge")
    text = ("I record a record. It is kind of a problem. [[hello]]"
            if voice.language == "en" else "🙂 A avo\u0301 e o avo\u0302 bebem café. Custou €12,50.")
    hits = build_word_hits([line(text)])
    spans = [[hit.source_start, hit.source_end] for hit in hits]
    job = SpeechJob(root=tmp_path)
    results, errors = [], []
    job.succeeded.connect(lambda path: results.append(json.loads(
        (path / "pronunciation.json").read_text(encoding="utf-8"))))
    job.failed.connect(errors.append)
    job.start("pronunciation", voice, text, spans=spans)
    wait_for_job(qapp, job)
    assert not errors
    result = results[0]
    assert result["voice_id"] == voice.id
    assert result["text"] == text
    assert [[word["start"], word["end"]] for word in result["words"]] == spans
    for hit, word in zip(hits, result["words"]):
        assert hit.text == word["text"] == text[word["start"]:word["end"]]
        assert unicodedata.normalize("NFD", "".join(c for c in word["ipa"] if c not in STRESS)) == \
            unicodedata.normalize("NFD", "".join(c for c in word["phonemes"] if c not in STRESS))
        assert word["ipa_notation"] in ("ipa", "engine")
        if word["mode"] == "context":
            assert result["events_match"]
            assert word["phonemes"] == result["sentence_phonemes"][word["sentence_index"]][word["phoneme_start"]:word["phoneme_end"]]
        else:
            assert word["reason"] and word["sentence_index"] is None
    if voice.language == "en":
        first, second = (word for word in result["words"] if word["text"] == "record")
        assert first["phonemes"] != second["phonemes"]
        assert first["mode"] == second["mode"] == "context"
        of_index = next(index for index, word in enumerate(result["words"]) if word["text"] == "of")
        assert [word["text"] for word in result["words"][of_index:of_index + 2]] == ["of", "a"]
        assert all(word["mode"] == "isolated" for word in result["words"][of_index:of_index + 2])
        assert result["words"][-1]["phonemes"] != "hello"
    else:
        assert result["words"][1]["phonemes"] != result["words"][4]["phonemes"]
        assert all(word["mode"] == "isolated" for word in result["words"] if word["text"] in ("12", "50"))
    assert not list(tmp_path.glob(".job-*"))


def test_prepared_audio_never_reinterprets_ipa_as_text(monkeypatch, tmp_path):
    pytest.importorskip("piper")
    import numpy as np
    import onnxruntime
    from types import SimpleNamespace
    from piper.config import PiperConfig
    from piper.phonemize_espeak import EspeakPhonemizer
    from piper.voice import PiperVoice
    from language_lens.services import speech_worker
    voice = VOICES[0]
    model = tmp_path / "model.onnx"
    model.with_suffix(".onnx.json").write_text("{}", encoding="utf-8")
    phones = "mˈɑːks sɐ̃w"
    config = SimpleNamespace(espeak_voice=voice.espeak, phoneme_type=SimpleNamespace(value="espeak"),
                             vowel_clusters=None, phoneme_id_map=dict.fromkeys(phones), sample_rate=22050)
    monkeypatch.setattr(speech_worker, "verified_model", lambda *_: model)
    monkeypatch.setattr(PiperConfig, "from_dict", lambda *_: config)
    monkeypatch.setattr(onnxruntime, "InferenceSession", lambda *a, **kw: object())
    def no_text(*args, **kwargs):
        raise AssertionError("Prepared phonemes must not be phonemized again")
    monkeypatch.setattr(EspeakPhonemizer, "phonemize", no_text)
    received = []
    monkeypatch.setattr(PiperVoice, "phonemes_to_ids", lambda self, value: received.append(value) or [1])
    monkeypatch.setattr(PiperVoice, "phoneme_ids_to_audio", lambda *_: np.array([.1, -.1], dtype=np.float32))
    speech_worker.synthesize(voice, tmp_path, "DO NOT READ THIS", tmp_path / "word.wav", [phones])
    assert received == [list(phones)]


@pytest.fixture
def word_window(qapp, monkeypatch, tmp_path):
    class IdlePool:
        @staticmethod
        def globalInstance():
            return IdlePool()
        def start(self, task):
            pass
    monkeypatch.setattr(review, "QThreadPool", IdlePool)
    monkeypatch.setattr(review, "runtime_ready", lambda: True)
    monkeypatch.setattr(review, "voice_present", lambda _: True)
    window = review.ReviewWindow(QPixmap(1000, 800), QRect(200, 300, 600, 40),
                                 Settings(source_language="en", show_ipa=True))
    window.pronunciation_job.root = tmp_path
    monkeypatch.setattr(window.pronunciation_job, "start", lambda *args, **kw: None)
    window.resize(1000, 800)
    window._ocr_finished([line("I record a record.")])
    words = []
    for index, hit in enumerate(window._hits):
        phones = "ɹɪkˈɔːd" if index == 1 else "ɹˈɛkɔːd"
        display = format_ipa(phones, "en-GB")
        words.append(dict(start=hit.source_start, end=hit.source_end, text=hit.text,
                          ipa=display.text, phonemes=phones, mode="context", reason=None,
                          ipa_notation=display.notation, ipa_notes=display.notes))
    window._prepared = dict(words=words, sentence_phonemes=["aɪ ɹɪkˈɔːd ə ɹˈɛkɔːd."])
    window.canvas.set_pronunciations(words)
    window.canvas._hovered = window.canvas._hits[1]
    window.canvas._refresh_bubble()
    yield window
    window.close()


def test_popup_plays_the_selected_occurrence_and_keeps_ipa_during_translation(word_window, monkeypatch):
    window = word_window
    popup = window.canvas._bubble
    calls = []
    monkeypatch.setattr(window.speech, "speak_phonemes", lambda phones, voice, context: calls.append((phones, context)))
    popup.play.click()
    window.canvas.set_translations({"record": WordTranslation(("registo",))})
    assert popup.translation.text() == "registo"
    assert popup.ipa.text() == "[ɹɪˈkɔːd]"
    assert not popup.isHidden()
    window.canvas._hovered = window.canvas._hits[3]
    window.canvas._refresh_bubble()
    popup.play.click()
    assert [call[0] for call in calls] == [("ɹɪkˈɔːd",), ("ɹˈɛkɔːd",)]
    assert calls[0][1] != calls[1][1]


def test_popup_stays_accessible_and_can_be_pinned(word_window, monkeypatch):
    window = word_window
    # Show only this offscreen test window so visibility checks model real hover.
    window.show()
    popup = window.canvas._bubble
    window.canvas._refresh_bubble()
    monkeypatch.setattr(review.QCursor, "pos", lambda: popup.mapToGlobal(popup.play.geometry().center()))
    window.canvas._hide_if_outside()
    assert popup.isVisible()
    point = window.canvas._source_to_display(window.canvas._hits[1].bounds).center().toPoint()
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=point)
    assert window.canvas._pinned
    monkeypatch.setattr(review.QCursor, "pos", lambda: window.mapToGlobal(QPoint(0, 0)))
    window.canvas._hide_if_outside()
    assert popup.isVisible()
    popup.dismissed.emit()
    assert popup.isHidden() and not window.canvas._pinned


def test_ipa_can_be_hidden_without_removing_word_audio_and_fallback_is_visible(word_window):
    canvas = word_window.canvas
    canvas.configure_pronunciation(False, True, VOICES[0].name)
    entry = dict(word_window._prepared["words"][1], mode="isolated", reason="Ambiguous native boundary")
    canvas.set_pronunciations([entry])
    assert canvas._bubble.ipa.isHidden()
    assert not canvas._bubble.play.isHidden()
    assert canvas._bubble.play.isEnabled()
    assert canvas._bubble.detail.text() == "Word in isolation"
    canvas.configure_pronunciation(True, False, VOICES[0].name)
    canvas._refresh_bubble()
    assert not canvas._bubble.ipa.isHidden()
    assert canvas._bubble.play.isHidden()


def test_ipa_failure_leaves_translation_and_sentence_audio_available(word_window):
    window = word_window
    window._pronunciation_failed("Test worker crash")
    window._translation_finished(("Translated sentence", {"record": WordTranslation(("registo",))}))
    assert window.read_button.isEnabled()
    assert window.canvas._bubble.translation.text() == "registo"
    assert not window.canvas._bubble.retry.isHidden()
    window.close()
    window._pronunciation_failed("Late error")
    assert window.canvas._bubble.isHidden()


def test_escape_from_popup_button_closes_review_and_cancels_pronunciation(word_window, monkeypatch):
    window = word_window
    stopped = []
    monkeypatch.setattr(window.pronunciation_job, "shutdown", lambda: stopped.append(True))
    window.show()
    window.canvas._refresh_bubble()
    window.canvas._bubble.play.setFocus()
    QTest.keyClick(window.canvas._bubble.play, Qt.Key.Key_Escape)
    assert window._closed and stopped
    assert window.canvas._bubble.isHidden()


def test_engine_notation_and_original_stress_are_explained_in_popup(word_window):
    canvas = word_window.canvas
    entry = dict(word_window._prepared["words"][1], ipa="ˈɹᵻkɔːd", ipa_notation="engine",
                 ipa_notes=["Non-IPA weak-vowel engine symbol retained."])
    canvas.set_pronunciations([entry])
    popup = canvas._bubble
    assert popup.detail.text() == "Engine notation · from selected sentence"
    assert "weak-vowel" in popup.ipa.toolTip()
    assert entry["phonemes"] in popup.ipa.toolTip()
    assert popup.ipa.layoutDirection() == Qt.LayoutDirection.LeftToRight
    assert popup.play.isEnabled()
    entry = dict(entry, ipa_notation="ipa", ipa="ɹɪˈkɔːd", ipa_notes=[])
    canvas.set_pronunciations([entry])
    assert "Engine notation" not in popup.detail.text()
    assert "weak-vowel" not in popup.ipa.toolTip()


def test_ipa_normalization_preserves_entire_original_graphemes():
    from language_lens.services.pronunciation import normalize_with_offsets
    from language_lens.text import normalized_offsets
    for original in ("🙂 avo\u0301", "\u1100\u1161", "👩\u200d💻 café", "a\u0323\u0301"):
        assert normalize_with_offsets(original) == normalized_offsets(original)


@pytest.mark.parametrize("text", [None, "\ud800", "a\0b", "", "a" * 2001])
def test_bad_unicode_and_invalid_input_never_reach_native_adapter(text):
    from language_lens.services.pronunciation import Pronouncer
    from language_lens.services.speech_worker import validate_text
    # Invalid input is rejected before accessing any native state.
    with pytest.raises(ValueError):
        Pronouncer.prepare(object.__new__(Pronouncer), text, "en-GB")
    with pytest.raises(ValueError):
        validate_text(text)


def test_component_proof_never_substitutes_standalone_sounds():
    from language_lens.services.pronunciation import Pronouncer
    instance = object.__new__(Pronouncer)
    instance._component_cache = {}
    readings = {"ice": "ˈaɪs", "cream": "kɹˈiːm", "U": "jˈuː", "S": "ˈɛs", "A": "ˈeɪ"}
    def standalone(text, voice):
        instance._last_switches = (False,)
        return (readings[text],)
    instance._sentences = standalone
    assert instance._display_word("ˈaɪskɹˈiːm", "en-GB", "ice-cream", False).text == "ˈaɪsˈkɹiːm"
    assert instance._display_word("jˌuːˌɛsˈeɪ", "en-US", "USA", False).text == "ˌjuːˌɛsˈeɪ"
    mismatch = instance._display_word("ˈaɪskɹˈɪm", "en-GB", "ice-cream", False)
    assert mismatch.text == "ˈaɪskɹˈɪm" and mismatch.notation == "engine"


def test_optional_boundary_probe_failure_keeps_the_contextual_phones():
    from language_lens.services.pronunciation import Pronouncer
    instance = object.__new__(Pronouncer)
    instance._component_cache = {}
    def failure(*args):
        raise RuntimeError("Optional component phonemization failed")
    instance._sentences = failure
    display = instance._display_word("ˈaɪskɹˈiːm", "en-GB", "ice-cream", False)
    assert display.text == "ˈaɪskɹˈiːm" and display.notation == "engine"


def test_code_switching_is_retained_as_metadata_without_changing_piper_phones():
    from types import SimpleNamespace
    from language_lens.services.pronunciation import Pronouncer
    instance = object.__new__(Pronouncer)
    instance.bridge = SimpleNamespace(set_voice=lambda _: None,
        get_phonemes=lambda _: [("(en)kˈæt(pt)", ".", True), ("kˈa", ".", True)])
    assert instance._sentences("text", "pt") == ("kˈæt.", "kˈa.")
    assert instance._last_switches == (True, False)
    instance._display_word("kˈæt", "pt-PT", "cat", True)
    assert instance._last_switches == (True, False)


@pytest.mark.parametrize("voice", VOICES, ids=lambda voice: voice.locale)
def test_native_ipa_audit_corpus_preserves_every_sound_and_context_slice(qapp, tmp_path, voice):
    pytest.importorskip("piper.espeakbridge")
    # Includes hiatus, nasal diphthongs, consonant clusters, syllabic consonants,
    # acronyms/initialisms, compounds, number expansion, accents and loanwords.
    text = ("capitalization marks and offline. I record a record. "
            "Understand street beautiful fire hour button rhythm ice-cream co-operate re-enter. "
            "USA NASA naïve café 12.50 2026."
            if voice.language == "en" else
            "A avó e o avô bebem café. Coração pão mãe língua saúde país saída Coimbra muito. "
            "Transporte psicologia ritmo questão guarda-chuva EUA wifi online 12,50 2026.")
    hits = build_word_hits([line(text)])
    job = SpeechJob(root=tmp_path)
    results, errors = [], []
    job.succeeded.connect(lambda path: results.append(json.loads(
        (path / "pronunciation.json").read_text(encoding="utf-8"))))
    job.failed.connect(errors.append)
    job.start("pronunciation", voice, text, spans=[[h.source_start, h.source_end] for h in hits])
    wait_for_job(qapp, job)
    assert not errors
    result = results[0]
    assert len(result["words"]) == len(hits)
    for word, hit in zip(result["words"], hits):
        assert word["text"] == hit.text == text[word["start"]:word["end"]]
        for display_key in ("ipa", "phonemes"):
            assert isinstance(word[display_key], str)
        assert unicodedata.normalize("NFD", "".join(c for c in word["ipa"] if c not in STRESS)) == \
            unicodedata.normalize("NFD", "".join(c for c in word["phonemes"] if c not in STRESS))
        assert word["ipa_notation"] in ("ipa", "engine")
        if word["ipa_notation"] == "engine":
            assert word["ipa_notes"]
        if word["mode"] == "context":
            assert word["phonemes"] == result["sentence_phonemes"][word["sentence_index"]][word["phoneme_start"]:word["phoneme_end"]]
        else:
            assert word["reason"] and word["sentence_index"] is None
    if voice.locale == "en-GB":
        words = {word["text"]: word for word in result["words"]}
        assert words["capitalization"]["ipa"] == "ˌkæpɪtəlaɪˈzeɪʃən"
        assert words["marks"]["ipa"] == "mɑːks"
        assert words["offline"]["ipa"] == "ˈɒflaɪn"
        assert words["ice-cream"]["ipa"] == "ˈaɪsˈkɹiːm"
        assert words["USA"]["ipa"] == "ˌjuːˌɛsˈeɪ"
