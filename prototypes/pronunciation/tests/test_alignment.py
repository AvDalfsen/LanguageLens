import unicodedata

from prototypes.pronunciation.engine import (
    SpokenUnit, align_units, normalize_with_offsets, tokenize,
)


def test_occurrences_are_preserved_instead_of_deduplicated():
    words = tokenize("I record a record.")
    assert [(w.text, w.start, w.end) for w in words] == [
        ("I", 0, 1), ("record", 2, 8), ("a", 9, 10), ("record", 11, 17),
    ]


def test_exact_source_events_support_one_to_many_number_expansion():
    sentence = "twelve point five"
    aligned, matches, reasons = align_units("12.5", (sentence,), [
        SpokenUnit(0, 4, "twelve"), SpokenUnit(1, 4, "point"), SpokenUnit(1, 4, "five"),
    ])
    assert matches and not reasons
    assert aligned == {0: (0, 0, len(sentence))}


def test_same_word_count_is_not_sufficient_to_claim_alignment():
    aligned, matches, reasons = align_units("cat dog", ("kat dɔɡ",), [
        SpokenUnit(0, 3, "dɔɡ"), SpokenUnit(4, 3, "kat"),
    ])
    assert not matches and not aligned
    assert len(reasons) == 2


def test_merged_phrase_invalidates_both_words():
    aligned, matches, reasons = align_units("of a problem", ("əvə prɑbləm",), [
        SpokenUnit(0, 2, "əvə"), SpokenUnit(5, 7, "prɑbləm"),
    ])
    assert matches
    assert set(aligned) == {2}
    assert set(reasons) == {0, 1}


def test_word_cannot_span_two_synthesized_sentences():
    aligned, matches, reasons = align_units("12.5", ("twelve", "five"), [
        SpokenUnit(0, 4, "twelve"), SpokenUnit(1, 4, "five"),
    ])
    assert matches and not aligned
    assert "across sentences" in reasons[0]


def test_missing_start_event_cannot_claim_full_word():
    aligned, matches, reasons = align_units("cannot", ("nɑt",), [SpokenUnit(3, 3, "nɑt")])
    assert matches and not aligned and reasons


def test_original_unicode_offsets_survive_normalization():
    original = "🙂 A avo\u0301 e o avo\u0302."
    normalized, offsets = normalize_with_offsets(original)
    assert normalized == "🙂 A avó e o avô."
    for token in tokenize(normalized):
        source = original[offsets[token.start][0]:offsets[token.end - 1][1]]
        assert unicodedata.normalize("NFC", source) == token.text


def test_currency_contractions_and_hyphens_are_complete_units():
    assert [w.text for w in tokenize("€12,50 $12.50 don't Don’t re-read d'água")] == [
        "€12,50", "$12.50", "don't", "Don’t", "re-read", "d'água",
    ]
