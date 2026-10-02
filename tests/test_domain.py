from language_lens.domain import (
    OcrLine,
    build_word_hits,
    normalize_lookup_word,
    reading_order,
    suppress_contained_ocr_fragments,
)
from language_lens.services.hotkey import (
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    parse_hotkey,
)


def line(text: str, x: float = 10, y: float = 20, width: float = 200) -> OcrLine:
    return OcrLine(text, 0.9, ((x, y), (x + width, y), (x + width, y + 20), (x, y + 20)))


def test_build_word_hits_preserves_accents_and_apostrophes():
    hits = build_word_hits([line("Próximas d'água — mestre-bruxo!")])
    assert [hit.text for hit in hits] == ["Próximas", "d'água", "mestre-bruxo"]
    assert [hit.lookup_text for hit in hits] == ["próximas", "d'água", "mestre-bruxo"]
    assert all(hit.bounds.width > 0 for hit in hits)


def test_word_rectangles_follow_text_order():
    hits = build_word_hits([line("one two three")])
    assert hits[0].bounds.x < hits[1].bounds.x < hits[2].bounds.x
    assert hits[-1].bounds.right <= 210


def test_reading_order_sorts_lines():
    ordered = reading_order([line("second", y=80), line("first", y=10)])
    assert [item.text for item in ordered] == ["first", "second"]


def test_contained_single_letter_ocr_fragments_are_suppressed():
    lines = [
        line("This", x=10, width=70),
        line("Song", x=90, width=80),
        line("E", x=178, width=14),
        line("Broke", x=176, width=90),
        line("I", x=274, width=10),
        line("My", x=270, width=45),
        line("Heart", x=325, width=90),
    ]

    filtered = suppress_contained_ocr_fragments(lines)

    assert [item.text for item in filtered] == ["This", "Song", "Broke", "My", "Heart"]


def test_real_adjacent_single_letter_word_is_retained():
    lines = [line("I", x=10, width=12), line("agree", x=32, width=80)]

    filtered = suppress_contained_ocr_fragments(lines)

    assert [item.text for item in filtered] == ["I", "agree"]


def test_normalize_lookup_word_is_case_insensitive():
    assert normalize_lookup_word("MESTRE!") == "mestre"


def test_parse_windows_hotkey():
    modifiers, key = parse_hotkey("<ctrl>+<shift>+t")
    assert modifiers == MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
    assert key == ord("T")

