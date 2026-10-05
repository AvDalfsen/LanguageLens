import unicodedata

import pytest

from language_lens.text import normalize_lookup_word, normalized_offsets, word_spans


@pytest.mark.parametrize("text,expected", [
    ("«किताब!»", "किताब"),
    ("नमस्ते", "नमस्ते"),
    ("كِتاب!", "كِتاب"),
    ("Σίσυφος!", "Σίσυφος"),
    ("Próximas", "Próximas"),
    ("avo\u0301", "avó"),
    ("d'água", "d'água"),
    ("mestre-bruxo", "mestre-bruxo"),
    ("می\u200cروم", "می\u200cروم"),
    ("42", "42"),
])
def test_lookup_retains_complete_unicode_words(text, expected):
    assert normalize_lookup_word(text) == expected


@pytest.mark.parametrize("first,second", [("Polish", "polish"), ("US", "us"), ("Sie", "sie")])
def test_capitalization_remains_meaningful(first, second):
    assert normalize_lookup_word(first) != normalize_lookup_word(second)


@pytest.mark.parametrize("language,text,expected", [
    ("ja", "私は本を読みます。", ["私", "は", "本", "を", "読み", "ます"]),
    ("zh", "我喜欢学习中文。", ["我", "喜欢", "学习", "中文"]),
    ("hi", "यह किताब है।", ["यह", "किताब", "है"]),
    ("ar", "هذا كِتابٌ", ["هذا", "كِتابٌ"]),
    ("ru", "Это новая книга.", ["Это", "новая", "книга"]),
    ("el", "Αυτό είναι βιβλίο.", ["Αυτό", "είναι", "βιβλίο"]),
    ("ko", "이것은 책입니다.", ["이것은", "책입니다"]),
])
def test_source_language_segmentation(language, text, expected):
    spans = list(word_spans(text, language))
    assert [text[start:end] for start, end in spans] == expected
    assert all(first[1] <= second[0] for first, second in zip(spans, spans[1:]))


@pytest.mark.parametrize("language,text", [
    ("ja", "🙂 OpenAIでPythonを学びます。私と私。"),
    ("zh", "🙂 Python和中文，中文和Python。"),
    ("hi", "🙂 किताब किताब नमस्ते"),
])
def test_segmentation_preserves_every_letter_and_original_occurrence(language, text):
    spans = list(word_spans(text, language))
    covered = {index for start, end in spans for index in range(start, end)}
    assert all(index in covered for index, character in enumerate(text)
               if unicodedata.category(character)[0] in "LMN")
    assert all(text[start:end].strip() == text[start:end] for start, end in spans)


def test_normalization_offsets_keep_whole_graphemes_and_emoji():
    text = "🙂 avo\u0301 किताब"
    normalized, offsets = normalized_offsets(text)
    assert normalized == "🙂 avó किताब"
    accent = normalized.index("ó")
    assert text[slice(*offsets[accent])] == "o\u0301"
    assert offsets[0] == (0, 1)
