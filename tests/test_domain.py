from language_lens.domain import (
    OcrLine,
    OcrSpanBox,
    Rect,
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
    assert [hit.lookup_text for hit in hits] == ["Próximas", "d'água", "mestre-bruxo"]
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


def test_normalize_lookup_word_retains_source_case():
    assert normalize_lookup_word("MESTRE!") == "MESTRE"


def box(start, end, x, width, y=20, height=20):
    return OcrSpanBox(start, end, ((x, y), (x + width, y), (x + width, y + height), (x, y + height)))


def test_ocr_coordinates_win_over_character_count_estimates():
    text = "iii WWW"
    source = OcrLine(text, .99, line(text, x=10, width=60).polygon, (
        box(0, 1, 10, 2), box(1, 2, 12, 2), box(2, 3, 14, 2),
        box(4, 5, 22, 12), box(5, 6, 34, 12), box(6, 7, 46, 12),
    ))
    hits = build_word_hits([source])
    assert hits[0].bounds == Rect(10, 20, 6, 20)
    assert hits[1].bounds == Rect(22, 20, 36, 20)


def test_incomplete_character_boxes_do_not_truncate_a_word():
    source = OcrLine("cat dog", .99, line("cat dog").polygon, (box(0, 1, 10, 8), box(4, 7, 100, 45)))
    hits = build_word_hits([source])
    assert hits[0].bounds.width > 8
    assert hits[1].bounds == Rect(100, 20, 45, 20)


def test_geometry_transform_retains_source_spans_and_native_boxes():
    source = OcrLine("किताब", .99, line("किताब").polygon, (box(0, 5, 10, 40),), ((0, 5),))
    moved = source.map_geometry(lambda x, y: (x / 2 + 100, y / 2 + 200))
    assert moved.text == source.text and moved.token_spans == source.token_spans
    assert moved.span_boxes[0].start == 0 and moved.span_boxes[0].end == 5
    assert moved.span_boxes[0].polygon == ((105, 210), (125, 210), (125, 220), (105, 220))


def test_arabic_fallback_places_logical_first_word_on_the_right(qapp):
    hits = build_word_hits([line("هذا كتاب")], "ar")
    assert [hit.text for hit in hits] == ["هذا", "كتاب"]
    assert hits[0].bounds.x > hits[1].bounds.x


def test_arabic_with_numbers_uses_visual_bidi_positions(qapp):
    hits = build_word_hits([line("هذا 123 كتاب")], "ar")
    assert [hit.text for hit in hits] == ["هذا", "123", "كتاب"]
    assert hits[0].bounds.x > hits[1].bounds.x > hits[2].bounds.x


def test_fontless_arabic_fallback_respects_direction(monkeypatch):
    from PySide6.QtGui import QGuiApplication
    monkeypatch.setattr(QGuiApplication, "instance", staticmethod(lambda: None))
    hits = build_word_hits([line("هذا كِتابٌ")], "ar")
    assert hits[0].bounds.x > hits[1].bounds.x
    assert hits[1].lookup_text == "كِتابٌ"


def test_fontless_fallback_counts_combining_sequences_as_graphemes(monkeypatch):
    from PySide6.QtGui import QGuiApplication
    monkeypatch.setattr(QGuiApplication, "instance", staticmethod(lambda: None))
    nfc = build_word_hits([line("avó e avô")])
    nfd = build_word_hits([line("avo\u0301 e avo\u0302")])
    assert [hit.bounds for hit in nfc] == [hit.bounds for hit in nfd]


def test_vertical_chinese_tokens_follow_top_to_bottom_geometry():
    source = OcrLine("我喜欢中文", .99, ((10, 20), (30, 20), (30, 220), (10, 220)))
    hits = build_word_hits([source], "zh")
    assert [hit.text for hit in hits] == ["我", "喜欢", "中文"]
    assert hits[0].bounds.y < hits[1].bounds.y < hits[2].bounds.y
    assert all(hit.bounds.x == 10 and hit.bounds.width == 20 for hit in hits)


def test_japanese_offsets_match_original_text_across_lines_and_emoji():
    lines = [line(" 🙂 私は本を読みます。 "), line("  本と本 ")]
    selection = " ".join(item.text for item in lines)
    hits = build_word_hits(lines, "ja")
    assert all(selection[hit.source_start:hit.source_end] == hit.text for hit in hits)
    assert len({hit.source_start for hit in hits if hit.text == "本"}) == 3


def test_reading_order_respects_arabic_rows_and_small_vertical_offsets():
    ordered = reading_order([
        line("كتاب", x=10, y=19, width=60), line("هذا", x=100, y=17, width=60),
        line("آخر", x=10, y=60, width=60),
    ], "ar")
    assert [item.text for item in ordered] == ["هذا", "كتاب", "آخر"]


def test_parse_windows_hotkey():
    modifiers, key = parse_hotkey("<ctrl>+<shift>+t")
    assert modifiers == MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
    assert key == ord("T")

