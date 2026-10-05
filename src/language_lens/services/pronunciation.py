"""Source-position-based IPA preparation for the pinned Piper/eSpeak worker.

Native eSpeak state is process-global. Instantiate only in a disposable worker.
Promoted from the tested pronunciation prototype; alignment requires exact
phoneme equality and unambiguous source coverage, never word-count matching.
"""
from __future__ import annotations

import ctypes as ct
from dataclasses import asdict, dataclass, replace
from importlib.metadata import version
from pathlib import Path
import re
import threading
import unicodedata


# Use the exact phonemizer each pinned voice was trained with. Alan's configuration
# requests RP, not eSpeak's generic English default.
from language_lens.services.voices import MAX_TEXT_LENGTH, PIPER_VERSION, VOICES
from language_lens.services.ipa import STRESS, format_ipa
from language_lens.text import normalized_offsets

LOCALES = {voice.locale: voice.espeak for voice in VOICES}
_LOCK = threading.RLock()
_SEPARATORS = frozenset(" \t\r\n.,:;!?-")


@dataclass(frozen=True)
class Token:
    start: int
    end: int
    text: str


@dataclass
class SpokenUnit:
    start: int
    length: int
    phones: str = ""


@dataclass(frozen=True)
class WordPronunciation:
    index: int
    start: int
    end: int
    text: str
    ipa: str
    phonemes: str
    mode: str
    reason: str | None
    sentence_index: int | None = None
    phoneme_start: int | None = None
    phoneme_end: int | None = None
    ipa_notation: str = "ipa"
    ipa_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pronunciation:
    text: str
    locale: str
    espeak_version: str
    sentence_phonemes: tuple[str, ...]
    words: tuple[WordPronunciation, ...]
    events_match: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_with_offsets(text: str) -> tuple[str, list[tuple[int, int]]]:
    """NFC for the engine; maintain offsets into the unmodified OCR text."""
    return normalized_offsets(text)


def tokenize(text: str) -> list[Token]:
    """Latin-language prototype units, keeping decimals and currency together."""
    tokens: list[Token] = []
    index = 0
    number = re.compile(r"[£$€]?\d+(?:[.,]\d+)*(?:%)?")

    def is_letter(char: str) -> bool:
        return unicodedata.category(char)[0] in "LMN"

    while index < len(text):
        match = number.match(text, index)
        if match:
            end = match.end()
        elif is_letter(text[index]):
            end = index + 1
            while end < len(text):
                if is_letter(text[end]):
                    end += 1
                elif text[end] in "'-’" and end + 1 < len(text) and is_letter(text[end + 1]):
                    end += 1
                else:
                    break
        else:
            index += 1
            continue
        tokens.append(Token(index, end, text[index:end]))
        index = end
    return tokens


def sound_chars(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if c not in _SEPARATORS)


def align_units(
    text: str, sentences: tuple[str, ...], units: list[SpokenUnit]
) -> tuple[dict[int, tuple[int, int, int]], bool, dict[int, str]]:
    """Only accept exact phoneme equality plus unambiguous source coverage.

    No edit-distance guess or one-word/one-space assumption is used. A missing
    word event can mean a multiword contraction; its neighbouring unit is rejected
    too, so the combined pronunciation never gets attributed to just one word.
    """
    tokens = tokenize(text)
    locations: list[tuple[int, int]] = []
    expected = []
    for sentence_index, sentence in enumerate(sentences):
        for char_index, char in enumerate(sentence):
            if char not in _SEPARATORS:
                expected.append(char)
                locations.append((sentence_index, char_index))
    actual = "".join(sound_chars(unit.phones) for unit in units)
    if actual != "".join(expected):
        return {}, False, {i: "Native events differ from Piper's sentence phonemes." for i in range(len(tokens))}

    if any(a.start > b.start for a, b in zip(units, units[1:])):
        return {}, True, {i: "Engine source positions are not in reading order." for i in range(len(tokens))}

    spans: dict[int, list[tuple[int, int]]] = {}
    reasons: dict[int, str] = {}
    cursor = 0
    for unit_index, unit in enumerate(units):
        size = len(sound_chars(unit.phones))
        owner = next((i for i, t in enumerate(tokens) if t.start <= unit.start < t.end), None)
        next_start = next((u.start for u in units[unit_index + 1:] if u.start > unit.start), len(text))
        covered = [i for i, t in enumerate(tokens) if unit.start <= t.start < next_start or i == owner]
        if len(covered) > 1:
            for index in covered:
                reasons[index] = "One engine word event covers multiple source words."
        if owner is not None and size:
            spans.setdefault(owner, []).append((cursor, cursor + size))
        cursor += size

    aligned: dict[int, tuple[int, int, int]] = {}
    for index, token in enumerate(tokens):
        owned = [unit for unit in units if token.start <= unit.start < token.end]
        ranges = spans.get(index, [])
        if index in reasons:
            continue
        if not owned or owned[0].start != token.start or not ranges:
            reasons[index] = "No complete, unambiguous source event for this word."
            continue
        if any(left[1] != right[0] for left, right in zip(ranges, ranges[1:])):
            reasons[index] = "Word phonemes are not a contiguous part of the sentence."
            continue
        sentence_index, start = locations[ranges[0][0]]
        last_sentence, last = locations[ranges[-1][1] - 1]
        if sentence_index != last_sentence:
            reasons[index] = "The engine split this unit across sentences."
            continue
        aligned[index] = (sentence_index, start, last + 1)
    return aligned, True, reasons


class _EventId(ct.Union):
    _fields_ = [("number", ct.c_int), ("name", ct.c_void_p), ("string", ct.c_char * 8)]


class _Event(ct.Structure):
    _fields_ = [
        ("type", ct.c_int), ("unique_identifier", ct.c_uint),
        ("text_position", ct.c_int), ("length", ct.c_int),
        ("audio_position", ct.c_int), ("sample", ct.c_int),
        ("user_data", ct.c_void_p), ("id", _EventId),
    ]


_Callback = ct.CFUNCTYPE(ct.c_int, ct.POINTER(ct.c_short), ct.c_int, ct.POINTER(_Event))


class Pronouncer:
    """Serial native adapter. Use in a disposable worker, never on a GUI thread."""
    def __init__(self) -> None:
        if version("piper-tts") != PIPER_VERSION:
            raise RuntimeError(f"Pronunciation requires piper-tts=={PIPER_VERSION}.")
        import piper.espeakbridge as bridge

        self.bridge = bridge
        self.lib = ct.CDLL(bridge.__file__)
        self.lib.espeak_Initialize.argtypes = [ct.c_int, ct.c_int, ct.c_char_p, ct.c_int]
        self.lib.espeak_Initialize.restype = ct.c_int
        self.lib.espeak_SetSynthCallback.argtypes = [_Callback]
        self.lib.espeak_SetSynthCallback.restype = None
        self.lib.espeak_Synth.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_uint, ct.c_int,
                                        ct.c_uint, ct.c_uint, ct.c_void_p, ct.c_void_p]
        self.lib.espeak_Synth.restype = ct.c_int
        self.lib.espeak_Info.argtypes = [ct.c_void_p]
        self.lib.espeak_Info.restype = ct.c_char_p
        self.engine_version = self.lib.espeak_Info(None).decode("ascii")
        self._last_switches: tuple[bool, ...] = ()
        self._component_cache: dict[tuple[str, str], str] = {}
        data = Path(bridge.__file__).parent / "espeak-ng-data"
        # Synchronous retrieval, IPA events, and failure rather than process exit.
        with _LOCK:
            if self.lib.espeak_Initialize(2, 0, str(data).encode("utf-8"), 0x8003) <= 0:
                raise RuntimeError("Could not initialise Piper's bundled eSpeak data.")

    def _sentences(self, text: str, voice: str) -> tuple[str, ...]:
        self.bridge.set_voice(voice)
        sentences: list[str] = []
        switches: list[bool] = []
        pending = ""
        switched = False
        for phonemes, terminator, ended in self.bridge.get_phonemes(text):
            # Same transformation as Piper 1.8.0's eSpeak phonemizer. Call the
            # bridge directly to avoid Piper interpreting OCR [[text]] as phones.
            switched |= bool(re.search(r"\([^)]+\)", phonemes))
            pending += re.sub(r"\([^)]+\)", "", phonemes) + terminator
            if terminator in (",", ":", ";"):
                pending += " "
            if ended:
                sentences.append(unicodedata.normalize("NFD", pending))
                switches.append(switched)
                pending = ""
                switched = False
        if pending:
            sentences.append(unicodedata.normalize("NFD", pending))
            switches.append(switched)
        self._last_switches = tuple(switches)
        return tuple(sentences)

    def _display_word(self, phones: str, locale: str, source: str, switched: bool):
        """Verify hyphen component boundaries by exact segment equality only.

        Isolated component readings are never substituted for contextual phones.
        A mismatch (sandhi, vowel reduction, language switching) is not guessed.
        """
        raw = unicodedata.normalize("NFD", phones)
        parts = re.split(r"[-‐‑]+", source)
        boundaries: tuple[int, ...] = ()
        unverified = len(parts) > 1
        # Initialisms can lose spaces too: USA is /juː ɛs eɪ/, not /juː ɛ seɪ/.
        # A lexical acronym such as NASA must not be replaced by letter readings.
        initialism = source.isalpha() and source.isupper() and len(source) > 1 and raw.count("ˈ") + raw.count("ˌ") > 1
        if initialism and not unverified:
            parts = list(source)
        if len(parts) > 1 and all(parts) and not switched:
            def key(value):
                return "".join(c for c in unicodedata.normalize("NFD", value)
                               if c not in STRESS and c not in _SEPARATORS)
            component_keys = []
            for part in parts:
                cache_key = (locale, part)
                if cache_key not in self._component_cache:
                    try:
                        component = " ".join(self._sentences(part, LOCALES[locale]))
                    except (RuntimeError, ValueError, UnicodeError):
                        # A failed optional boundary probe must not discard an
                        # already prepared contextual pronunciation or its audio.
                        component = ""
                    self._component_cache[cache_key] = "" if not component or any(self._last_switches) else key(component)
                component_keys.append(self._component_cache[cache_key])
            if all(component_keys) and "".join(component_keys) == key(raw):
                positions = [i for i, c in enumerate(raw) if c not in STRESS and c not in _SEPARATORS]
                length = 0
                located = []
                for component in component_keys[:-1]:
                    length += len(component)
                    located.append(positions[length])
                boundaries, unverified = tuple(located), False
            elif initialism:
                unverified = True
        return format_ipa(raw, locale, boundaries=boundaries, language_switch=switched,
                          compound_unverified=unverified)

    def _events(self, text: str, voice: str) -> list[SpokenUnit]:
        units: list[SpokenUnit] = []
        errors: list[str] = []

        @_Callback
        def collect(_audio, _count, events):
            try:
                index = 0
                while events[index].type:
                    event = events[index]
                    if event.type == 1:
                        units.append(SpokenUnit(event.text_position - 1, event.length))
                    elif event.type == 7:
                        phone = event.id.string.decode("utf-8")
                        if phone:
                            if not units or event.text_position - 1 != units[-1].start:
                                errors.append("Phoneme event has no matching word position.")
                            else:
                                units[-1].phones += phone
                    index += 1
                return 0
            except Exception as exc:
                errors.append(str(exc))
                return 1

        self.bridge.set_voice(voice)
        self.lib.espeak_SetSynthCallback(collect)
        raw = text.encode("utf-8") + b"\0"
        try:
            result = self.lib.espeak_Synth(raw, len(raw), 0, 1, 0, 1, None, None)
        finally:
            # The library must not retain a pointer to a collected Python callback.
            self.lib.espeak_SetSynthCallback(_Callback())
        if result != 0 or errors:
            raise RuntimeError("; ".join(errors) or f"eSpeak synthesis failed ({result}).")
        return units

    def prepare(self, text: str, locale: str) -> Pronunciation:
        if locale not in LOCALES:
            raise ValueError(f"Unsupported pronunciation locale: {locale}")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"Use a non-empty selection of at most {MAX_TEXT_LENGTH:,} characters.")
        if any(unicodedata.category(c) == "Cs" or
               (unicodedata.category(c) == "Cc" and c not in "\n\r\t") for c in text):
            raise ValueError("Invalid Unicode or control characters are not supported in screenshot text.")
        normalized, offsets = normalize_with_offsets(text)
        voice = LOCALES[locale]
        warnings: list[str] = []
        with _LOCK:
            sentences = self._sentences(normalized, voice)
            sentence_switches = self._last_switches
            try:
                units = self._events(normalized, voice)
                aligned, matches, reasons = align_units(normalized, sentences, units)
            except RuntimeError as exc:
                aligned, matches, reasons = {}, False, {}
                warnings.append(str(exc))
            words = []
            for index, token in enumerate(tokenize(normalized)):
                start, end = offsets[token.start][0], offsets[token.end - 1][1]
                if index in aligned:
                    sentence, phone_start, phone_end = aligned[index]
                    phones = sentences[sentence][phone_start:phone_end]
                    switched = sentence_switches[sentence]
                    mode, reason = "context", None
                else:
                    # Standalone fallback is explicit, never represented as contextual.
                    phones = " ".join(self._sentences(token.text, voice)).strip(" .,:;!?")
                    switched = any(self._last_switches)
                    sentence = phone_start = phone_end = None
                    mode = "isolated" if sound_chars(phones) else "unavailable"
                    reason = reasons.get(index, "Native source alignment unavailable.")
                display = self._display_word(phones, locale, token.text, switched)
                words.append(WordPronunciation(
                    index, start, end, text[start:end], display.text,
                    phones, mode, reason, sentence, phone_start, phone_end,
                    display.notation, display.notes,
                ))
        if not matches:
            warnings.append("Context mapping was not verified; word results use isolated fallback.")
        return Pronunciation(text, locale, self.engine_version, sentences, tuple(words), matches, tuple(warnings))

    def prepare_for_spans(self, text: str, locale: str, spans: list) -> Pronunciation:
        """Map to the exact OCR occurrences; use explicit isolation for split units.

        OCR may split a currency/decimal into several hover targets. Never assign
        the pronunciation of that whole unit to one of its smaller targets.
        """
        previous_end = 0
        if not isinstance(spans, list) or len(spans) > 2000:
            raise ValueError("Invalid pronunciation word positions.")
        for span in spans:
            if (not isinstance(span, (tuple, list)) or len(span) != 2
                    or any(type(value) is not int for value in span)):
                raise ValueError("Invalid pronunciation word positions.")
            start, end = span
            if not previous_end <= start < end <= len(text) or not text[start:end].strip():
                raise ValueError("Pronunciation word positions must be ordered and non-overlapping.")
            previous_end = end
        prepared = self.prepare(text, locale)
        by_span = {(word.start, word.end): word for word in prepared.words}
        words = []
        with _LOCK:
            for index, (start, end) in enumerate(spans):
                matched = by_span.get((start, end))
                if matched is not None:
                    words.append(replace(matched, index=index))
                    continue
                phones = " ".join(self._sentences(
                    unicodedata.normalize("NFC", text[start:end]), LOCALES[locale]
                )).strip(" .,:;!?")
                display = self._display_word(phones, locale, text[start:end], any(self._last_switches))
                words.append(WordPronunciation(
                    index, start, end, text[start:end], display.text,
                    phones, "isolated" if sound_chars(phones) else "unavailable",
                    "The highlighted word does not match a complete engine word boundary.",
                    ipa_notation=display.notation, ipa_notes=display.notes,
                ))
        return replace(prepared, words=tuple(words))
