import json
from pathlib import Path
import unicodedata

import pytest

from prototypes.pronunciation.engine import LOCALES, Pronouncer


@pytest.fixture(scope="module")
def engine():
    pytest.importorskip("piper.espeakbridge")
    return Pronouncer()


@pytest.mark.parametrize("locale", LOCALES)
def test_corpus_never_silently_changes_source_or_claims_guessed_phone_spans(engine, locale):
    corpus = json.loads((Path(__file__).parents[1] / "corpus.json").read_text(encoding="utf-8"))
    for case in corpus:
        if locale not in case["locales"]:
            continue
        result = engine.prepare(case["text"], locale)
        assert result.words
        for word in result.words:
            assert case["text"][word.start:word.end] == word.text
            assert word.ipa == unicodedata.normalize("NFC", word.phonemes)
            if word.mode == "context":
                assert result.events_match
                assert word.phonemes == result.sentence_phonemes[word.sentence_index][word.phoneme_start:word.phoneme_end]
                assert not word.reason
            else:
                assert word.reason
                assert word.sentence_index is None


@pytest.mark.parametrize("locale", ["en-US", "en-GB"])
def test_actual_context_selects_different_record_pronunciations(engine, locale):
    result = engine.prepare("I record a record.", locale)
    first, second = result.words[1], result.words[3]
    assert first.text == second.text == "record"
    assert first.phonemes != second.phonemes
    assert first.mode == second.mode == "context"


def test_merged_native_phrase_is_an_explicit_fallback(engine):
    result = engine.prepare("It is kind of a problem.", "en-US")
    assert result.words[3].text == "of" and result.words[4].text == "a"
    assert result.words[3].mode == result.words[4].mode == "isolated"
    assert result.words[5].mode == "context"


@pytest.mark.parametrize("locale", ["pt-PT", "pt-BR"])
def test_portuguese_accents_remain_distinct(engine, locale):
    result = engine.prepare("A avó e o avô bebem café.", locale)
    assert result.words[1].phonemes != result.words[4].phonemes
    assert all(word.mode == "context" for word in result.words)


def test_dialect_changes_do_not_leak_between_calls(engine):
    brazil = engine.prepare("Os cintos de segurança são incríveis.", "pt-BR")
    portugal = engine.prepare(brazil.text, "pt-PT")
    brazil_again = engine.prepare(brazil.text, "pt-BR")
    assert brazil.sentence_phonemes == brazil_again.sentence_phonemes
    assert brazil.sentence_phonemes != portugal.sentence_phonemes


def test_screenshot_brackets_are_not_interpreted_as_piper_phoneme_injection(engine):
    word = engine.prepare("[[hello]]", "en-US").words[0]
    assert word.text == "hello"
    assert word.phonemes != "hello"


@pytest.mark.parametrize("text,locale", [("", "en-US"), ("a\0b", "en-US"), ("a" * 2001, "en-US"), ("word", "xx")])
def test_invalid_requests_do_not_reach_native_synthesis(engine, text, locale):
    with pytest.raises(ValueError):
        engine.prepare(text, locale)
