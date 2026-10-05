"""Conventions and losslessness, independent of native libraries/audio models."""
import unicodedata

import pytest

from language_lens.services.ipa import PROFILES, STRESS, format_ipa
from language_lens.services.voices import VOICES


def segments(text):
    return unicodedata.normalize("NFD", "".join(c for c in text if c not in STRESS))


def stress_targets(text):
    """Independent check: stress still refers to the same segment position."""
    raw = unicodedata.normalize("NFD", text)
    vowels = set("aeiouyæɒɑɐɛɔɜəɪʊʌɨɯɤøœɶɵɘɞɚɝᵻᵿ")
    targets = []
    for index, char in enumerate(raw):
        if char not in STRESS:
            continue
        for end in range(index + 1, len(raw)):
            syllabic = end + 1 < len(raw) and raw[end + 1] in "\u0329\u030d"
            if raw[end] in vowels or syllabic:
                targets.append((char, len("".join(c for c in raw[:end] if c not in STRESS))))
                break
        else:
            targets.append((char, None))
    return tuple(targets)


@pytest.mark.parametrize("raw,expected,locale", [
    ("kˌæpɪtəlaɪzˈeɪʃən", "ˌkæpɪtəlaɪˈzeɪʃən", "en-GB"),
    ("mˈɑːks", "mɑːks", "en-GB"),
    ("ænd", "ænd", "en-GB"),
    ("ˈɒflaɪn", "ˈɒflaɪn", "en-GB"),
    ("ˌʌndəstˈænd", "ˌʌndəˈstænd", "en-GB"),
    ("ɹɪkˈɔːd", "ɹɪˈkɔːd", "en-GB"),
    ("ɹˈɛkɔːd", "ˈɹɛkɔːd", "en-GB"),
    ("stɹˈɛŋθ", "stɹɛŋθ", "en-GB"),
    ("bˈjuːtɪfəl", "ˈbjuːtɪfəl", "en-GB"),
    ("bjˈuːtɪfəl", "ˈbjuːtɪfəl", "en-GB"),
    ("lˈɪtəl", "ˈlɪtəl", "en-GB"),
    ("naɪˈiːv", "naɪˈiːv", "en-GB"),
    ("kæfˈeɪ", "kæˈfeɪ", "en-GB"),
    ("mɪstˈeɪk", "mɪˈsteɪk", "en-GB"),
    ("ətɹˈækt", "əˈtɹækt", "en-GB"),
    ("əŋkˈɔː", "əŋˈkɔː", "en-GB"),
    ("bˈʌʔn̩", "ˈbʌʔn̩", "en-US"),
    ("bˈʌʔn̍", "ˈbʌʔn̍", "en-US"),
    ("ənt͡ʃˈænt", "ənˈt͡ʃænt", "en-US"),
    ("ənd͜ʒˈɔɪ", "ənˈd͜ʒɔɪ", "en-US"),
    ("hˈeɪ", "heɪ", "en-US"),
    ("hˈe͡ɪ", "he͡ɪ", "en-US"),
    ("hˈa͜i", "ha͜i", "en-US"),
    ("hˈoʊ", "hoʊ", "en-US"),
    ("hˈəʊ", "həʊ", "en-GB"),
    ("hˈɪə", "hɪə", "en-GB"),
    # Accent-specific nucleus counts: never export the English diphthong rules.
    ("hˈəʊ", "ˈhəʊ", "en-US"),
    ("avˈɔ", "aˈvɔ", "pt-BR"),
    ("ɐvˈo", "ɐˈvo", "pt-PT"),
    ("kˌuɾɐsˈɐ̃ʊ̃", "ˌkuɾɐˈsɐ̃ʊ̃", "pt-PT"),
    ("pˈɐ̃ʊ̃", "pɐ̃ʊ̃", "pt-PT"),
    ("mˈɐ̃j", "mɐ̃j", "pt-BR"),
    ("kˈeɪʒʊ", "ˈkeɪʒʊ", "pt-PT"),
    ("sˌaˈudʒɪ", "ˌsaˈudʒɪ", "pt-BR"),
    ("pɐˈiʃ", "pɐˈiʃ", "pt-PT"),
    ("sˌɐˈidɐ", "ˌsɐˈidɐ", "pt-PT"),
    ("tɾˌɐ̃nspˈɔɾtɨ", "ˌtɾɐ̃nsˈpɔɾtɨ", "pt-PT"),
    ("kɨʃtˈɐ̃ʊ̃", "kɨʃˈtɐ̃ʊ̃", "pt-PT"),
    ("kestˈɐ̃ʊ̃", "kesˈtɐ̃ʊ̃", "pt-BR"),
    ("kˈeɪ", "keɪ", "pt-BR"),
    ("kˈɐ̃ʊ̃", "kɐ̃ʊ̃", "pt-BR"),
    ("əˈi̯", "əˈi̯", "en-GB"),  # malformed: stressed non-syllabic segment stays raw
    ("twˈɛlv pɔɪnt fˈaɪv", "ˈtwɛlv pɔɪnt ˈfaɪv", "en-GB"),
])
def test_conventional_stress_with_segment_quality_intact(raw, expected, locale):
    result = format_ipa(raw, locale)
    assert result.text == unicodedata.normalize("NFC", expected)
    assert segments(result.text) == segments(raw)
    assert format_ipa(result.text, locale).text == result.text
    if any("omitted" in note for note in result.notes):
        assert len(stress_targets(raw)) == 1 and not stress_targets(result.text)
    else:
        assert stress_targets(result.text) == stress_targets(raw)


def test_all_shipping_accents_have_explicit_display_profiles():
    from language_lens.services.pronunciation import LOCALES
    assert set(PROFILES) == {voice.locale for voice in VOICES}
    assert all(LOCALES[voice.locale] == voice.espeak for voice in VOICES)


@pytest.mark.parametrize("raw", [
    "mˈɑːks", "kˌæpɪtəlaɪzˈeɪʃən", "pˈɐ̃ʊ̃", "ənt͡ʃˈænt", "bˈʌʔn̩",
    "nˈĩ", "sɐ̃ˈũ", "ˈɛːi̯", "ˈa̤", "ˈḁ", "ˈa̰", "ˈn̩", "ˈn̍", "ˈaʰ",
])
@pytest.mark.parametrize("locale", PROFILES)
def test_unicode_and_diacritics_never_change_or_disappear(raw, locale):
    composed = format_ipa(unicodedata.normalize("NFC", raw), locale)
    decomposed = format_ipa(unicodedata.normalize("NFD", raw), locale)
    assert composed == decomposed
    assert segments(composed.text) == segments(raw)


@pytest.mark.parametrize("raw", ["kˈɑːt💬", "ˈA", "ɑkˈs", "ˈ", "ˈˌa", "ˈ a", "ˈʰa", "t͡", "̩a", "ˈa⃝", "ˈn̩̯"])
def test_uninterpretable_notation_fails_visibly_without_guessing(raw):
    result = format_ipa(raw, "en-GB")
    assert result.text == unicodedata.normalize("NFC", raw)
    assert result.notation == "engine" and result.notes


def test_unknown_language_and_switching_never_apply_english_rules():
    raw = "kˌæpɪtəlaɪzˈeɪʃən"
    for result in (format_ipa(raw, "ja-JP"), format_ipa(raw, "pt-PT", language_switch=True)):
        assert result.text == raw
        assert result.notation == "engine" and result.notes


def test_weak_vowel_extension_is_not_silently_replaced_or_claimed_as_standard_ipa():
    raw = "kˌæpɪɾəlᵻzˈeɪʃən"
    result = format_ipa(raw, "en-US")
    assert result.text == "ˌkæpɪɾəlᵻˈzeɪʃən"
    assert result.notation == "engine"
    assert "weak-vowel" in " ".join(result.notes)
    assert segments(result.text) == segments(raw)


def test_explicit_component_boundary_prevents_stress_crossing_a_compound_coda():
    raw = "ˈaɪskɹˈiːm"
    result = format_ipa(raw, "en-GB", boundaries=(4,))
    assert result.text == "ˈaɪsˈkɹiːm"
    assert result.text.count("ˈ") == 2
    unverified = format_ipa(raw, "en-GB", compound_unverified=True)
    assert unverified.text == raw and unverified.notation == "engine"


def test_bad_component_boundary_cannot_split_a_diacritic_or_affricate():
    for raw, boundary in [("pˈɐ̃ʊ̃", 3), ("ət͡ʃˈa", 3)]:
        result = format_ipa(raw, "pt-PT", boundaries=(boundary,))
        assert result.text == unicodedata.normalize("NFC", raw)
        assert result.notation == "engine"


def test_stress_omission_is_documented_and_only_for_a_single_nucleus_unit():
    assert "omitted" in " ".join(format_ipa("mˈɑːks", "en-GB").notes)
    assert format_ipa("mˈɑːks mˈɑːks", "en-GB").text == "ˈmɑːks ˈmɑːks"
    assert format_ipa("fˈaɪə", "en-GB").text == "ˈfaɪə"  # do not guess synizesis
    assert format_ipa("ˌaˈa", "en-GB").text == "ˌaˈa"
    assert format_ipa("", "en-GB").text == ""


def test_unsegmented_compound_does_not_turn_icecream_into_ice_scream():
    result = format_ipa("ˈaɪskɹˈiːm", "en-GB")
    assert result.text == "ˈaɪskɹˈiːm" and result.notation == "engine"


def test_verified_initialism_boundary_keeps_the_coda_of_s_out_of_a():
    result = format_ipa("jˌuːˌɛsˈeɪ", "en-US", boundaries=(5, 8))
    assert result.text == "ˌjuːˌɛsˈeɪ"


def test_formatter_preserves_generated_segments_across_many_clusters():
    from itertools import product
    for locale in PROFILES:
        for onset, coda, nucleus, ending in product(
                ("k", "stɹ", "t͡ʃ", "ŋɡ", "pɾ"), ("n", "s", "ʔ"),
                ("ɑː", "ɐ̃ʊ̃", "eɪ", "n̩", "ɜ˞"), ("", "ɐ", "n̩")):
            raw = onset + "ˌɛ" + coda + "ˈ" + nucleus + ending
            result = format_ipa(raw, locale)
            assert segments(result.text) == segments(raw)
            assert result.text.count("ˈ") == raw.count("ˈ")
            assert result.text.count("ˌ") == raw.count("ˌ")
            assert stress_targets(result.text) == stress_targets(raw)
