import wave

import pytest

from prototypes.pronunciation.engine import LOCALES, Pronouncer, VoiceRenderer
from prototypes.pronunciation.run import model_path


@pytest.mark.parametrize("locale", LOCALES)
def test_actual_voice_renders_sentence_and_exact_contextual_word_without_rereading_text(locale, tmp_path, monkeypatch):
    pytest.importorskip("piper.espeakbridge")
    try:
        model = model_path(locale)
    except ValueError:
        pytest.skip("Download prototype voices to run the real audio integration tests.")
    renderer = VoiceRenderer(model, locale)

    def refuse_second_text_conversion(*args, **kwargs):
        pytest.fail("Audio must use prepared phonemes, not reinterpret the spelling.")

    monkeypatch.setattr(renderer.voice, "phonemize", refuse_second_text_conversion)
    text = "I record a record." if locale.startswith("en") else "A avó e o avô bebem café."
    prepared = Pronouncer().prepare(text, locale)
    word = prepared.words[1]
    assert word.mode == "context"
    for filename, phones in [("sentence.wav", prepared.sentence_phonemes), ("word.wav", (word.phonemes,))]:
        result = renderer.render(phones, tmp_path / filename)
        assert 0.05 < result["seconds"] < 20
        assert result["peak"] > 1e-6
        with wave.open(str(tmp_path / filename), "rb") as audio:
            assert audio.getnchannels() == 1
            assert audio.getsampwidth() == 2
            assert audio.getframerate() == renderer.sample_rate
            assert len(audio.readframes(audio.getnframes())) == audio.getnframes() * 2


def test_renderer_rejects_silent_symbol_dropping(tmp_path):
    pytest.importorskip("piper.espeakbridge")
    try:
        model = model_path("en-US")
    except ValueError:
        pytest.skip("Download the en-US prototype voice first.")
    renderer = VoiceRenderer(model, "en-US")
    with pytest.raises(ValueError, match="cannot render"):
        renderer.render(("hello🙂",), tmp_path / "invalid.wav")
    assert not (tmp_path / "invalid.wav").exists()
