"""Display-only formatting of the pinned eSpeak phoneme stream.

eSpeak attaches stress to nuclei, not syllable onsets. We use an explicitly
estimated, accent-specific maximal-onset convention; this is not a pronunciation
dictionary or a morphological syllabifier. Never feed this output back to Piper.
Unknown notation/locales fail visibly to engine notation rather than deleting or
inventing sounds. All non-stress characters survive, modulo Unicode NFC.
"""
from __future__ import annotations

from dataclasses import dataclass
import unicodedata

import regex


STRESS = frozenset("ˈˌ")
_BREAKS = frozenset(" \t\r\n.,:;!?-|‖‿")
_VOWELS = frozenset("aeiouyæɒɑɐɛɔɜəɪʊʌɨɯɤøœɶɵɘɞɚɝᵻᵿ")
_CONSONANTS = frozenset("pbtdkɡgʔmnŋɲɳɴɱfvθðszʃʒʂʐçʝxɣχʁħʕhɦɹɻrɾɽʀlɭʎʟɫjwɥʋɰcɟɸβɢqɬɮʈɖʍʙɺ")
_MODIFIERS = frozenset("ːˑʰʲʷˠˤ˞ʼ")
_TIES = frozenset("\u0361\u035c")
_SYLLABIC = frozenset("\u0329\u030d")
_NONSYLLABIC = frozenset("\u032f\u0311")
_EXTENSIONS = frozenset("ᵻᵿ")
_DIACRITICS = frozenset("\u0300\u0301\u0302\u0303\u0304\u0306\u0308\u030a\u030b\u030c\u030d"
                        "\u030f\u0311\u0318\u0319\u031a\u031c\u031d\u031e\u031f\u0320\u0324\u0325"
                        "\u0329\u032a\u032c\u032f\u0330\u0334\u0339\u033a\u033b\u033c\u035c\u0361")


@dataclass(frozen=True)
class Profile:
    onsets: frozenset[str]
    diphthongs: frozenset[str]


_EN_SINGLE = frozenset("pbtdkɡgʔmfvθðszʃʒhnɹrljw") | {"tʃ", "dʒ", "t͡ʃ", "d͡ʒ", "t͜ʃ", "d͜ʒ"}
_EN_CLUSTERS = frozenset((
    "pl", "bl", "kl", "ɡl", "gl", "fl", "sl", "pɹ", "bɹ", "tɹ", "dɹ", "kɹ", "ɡɹ", "gɹ", "fɹ", "θɹ", "ʃɹ",
    "pr", "br", "tr", "dr", "kr", "ɡr", "gr", "fr", "θr", "ʃr", "tw", "dw", "kw", "ɡw", "gw", "sw", "θw",
    "sp", "st", "sk", "sm", "sn", "sf", "spl", "skl", "spɹ", "stɹ", "skɹ", "spr", "str", "skr", "skw",
    "pj", "bj", "tj", "dj", "kj", "ɡj", "gj", "fj", "vj", "θj", "sj", "zj", "hj", "mj", "nj", "lj", "spj", "stj", "skj",
))
_PT_SINGLE = frozenset("pbtdkɡgʔmfvszʃʒhnɲʁxɾrlʎjw") | {"tʃ", "dʒ", "t͡ʃ", "d͡ʒ", "t͜ʃ", "d͜ʒ"}
_PT_CLUSTERS = frozenset((
    "pl", "bl", "tl", "dl", "kl", "ɡl", "gl", "fl", "vl", "pɾ", "bɾ", "tɾ", "dɾ", "kɾ", "ɡɾ", "gɾ", "fɾ", "vɾ",
    "pr", "br", "tr", "dr", "kr", "ɡr", "gr", "fr", "vr", "kw", "ɡw", "gw",
))
_PT_DIPHTHONGS = frozenset(("aɪ", "ɐɪ", "eɪ", "ɛɪ", "oɪ", "ɔɪ", "uɪ", "ʊɪ", "aʊ", "ɐʊ", "eʊ", "ɛʊ", "iʊ", "oʊ"))
PROFILES = {
    "en-US": Profile(_EN_SINGLE | _EN_CLUSTERS, frozenset(("eɪ", "aɪ", "ɔɪ", "aʊ", "oʊ"))),
    "en-GB": Profile(_EN_SINGLE | _EN_CLUSTERS, frozenset(("eɪ", "aɪ", "ɔɪ", "aʊ", "əʊ", "ɪə", "ɛə", "ʊə"))),
    "pt-PT": Profile(_PT_SINGLE | _PT_CLUSTERS, _PT_DIPHTHONGS),
    "pt-BR": Profile(_PT_SINGLE | _PT_CLUSTERS, _PT_DIPHTHONGS),
}


@dataclass(frozen=True)
class IpaDisplay:
    text: str
    notation: str = "ipa"
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Atom:
    text: str
    start: int
    end: int

    @property
    def base(self) -> str:
        return "".join(c for c in self.text if c not in _MODIFIERS
                       and (not unicodedata.category(c).startswith("M") or c in _TIES))

    @property
    def nucleus(self) -> bool:
        tied_vowels = self.base.translate(str.maketrans("", "", "".join(_TIES)))
        return bool(_SYLLABIC.intersection(self.text)) or (
            (self.base in _VOWELS or (bool(_TIES.intersection(self.text)) and
                                     all(c in _VOWELS for c in tied_vowels)))
            and not _NONSYLLABIC.intersection(self.text)
        )


def _atoms(text: str) -> list[_Atom]:
    result: list[_Atom] = []
    for match in regex.finditer(r"\X", text):
        value = match.group()
        if result and result[-1].text not in STRESS | _BREAKS and (
                value[0] in _MODIFIERS or result[-1].text[-1] in _TIES):
            previous = result.pop()
            result.append(_Atom(previous.text + value, previous.start, match.end()))
        else:
            result.append(_Atom(value, match.start(), match.end()))
    return result


def format_ipa(phonemes: str, locale: str, *, boundaries: tuple[int, ...] = (),
               language_switch: bool = False, compound_unverified: bool = False) -> IpaDisplay:
    """Format *engine* output; boundary offsets refer to its NFD representation.

    Only an unexpanded, definitely monosyllabic unit loses its redundant display
    stress. Multiword expansions, hiatus, syllabic consonants, and compounds retain
    stress. The source phonemes remain the sole authoritative synthesis input.
    """
    raw = unicodedata.normalize("NFD", phonemes)
    profile = PROFILES.get(locale)
    if profile is None or language_switch:
        reason = ("No IPA display profile exists for this accent." if profile is None else
                  "Language switching detected; retaining engine notation without guessing syllable boundaries.")
        return IpaDisplay(unicodedata.normalize("NFC", raw), "engine", (reason,))
    atoms = _atoms(raw)
    if not atoms:
        return IpaDisplay("")
    known = _VOWELS | _CONSONANTS | STRESS | _BREAKS
    if any(any(c not in known and c not in _MODIFIERS and c not in _DIACRITICS
               for c in atom.text) or atom.text[0] in _MODIFIERS
           or unicodedata.category(atom.text[0]).startswith("M")
           or atom.text[-1] in _TIES or (atom.text[0] in STRESS | _BREAKS and len(atom.text) != 1)
           or (_SYLLABIC.intersection(atom.text) and _NONSYLLABIC.intersection(atom.text))
           for atom in atoms):
        return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                          ("Unrecognized phonetic notation; the engine's output is preserved unchanged.",))

    floors = {i for i, atom in enumerate(atoms) if atom.start in boundaries}
    if len(floors) != len(set(boundaries)):
        return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                          ("A component boundary splits a phonetic segment; retaining engine notation.",))
    nuclei: list[tuple[int, int]] = []
    for i, atom in enumerate(atoms):
        if atom.nucleus:
            # An intervening stress mark always means hiatus, never a diphthong.
            previous = nuclei[-1] if nuclei else None
            if (previous and previous[1] == i and i not in floors
                    and atoms[previous[0]].base + atom.base in profile.diphthongs
                    and previous[1] - previous[0] == 1):
                nuclei[-1] = (previous[0], i + 1)
            else:
                nuclei.append((i, i + 1))
        elif _NONSYLLABIC.intersection(atom.text) and nuclei and nuclei[-1][1] == i and i not in floors:
            nuclei[-1] = (nuclei[-1][0], i + 1)

    marks = [i for i, atom in enumerate(atoms) if atom.text in STRESS]
    if not marks:
        return IpaDisplay(unicodedata.normalize("NFC", raw),
                          "engine" if _EXTENSIONS.intersection(raw) else "ipa",
                          ("Non-IPA weak-vowel engine symbol retained; no vowel quality was guessed.",)
                          if _EXTENSIONS.intersection(raw) else ())
    if not nuclei or any(not any(start > mark for start, _ in nuclei) for mark in marks):
        return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                          ("Stress could not be attached to a syllable nucleus; retaining engine notation.",))

    notes = ["Stress placement uses estimated accent-specific maximal onsets, not dictionary or morphological syllabification."]
    # Conservative: a compound/expansion or several stress markers are not an
    # ordinary one-syllable dictionary entry, even when vowel counting is uncertain.
    omit = (len(nuclei) == 1 and len(marks) == 1 and not boundaries and not compound_unverified
            and not any(atom.text in _BREAKS for atom in atoms))
    insertions: dict[int, str] = {}
    for mark in marks:
        if omit:
            continue
        nucleus = next(start for start, _ in nuclei if start > mark)
        if any(atoms[i].text in _BREAKS for i in range(mark + 1, nucleus)):
            return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                              ("Stress crosses a word boundary; retaining engine notation.",))
        if any(atoms[i].text in STRESS for i in range(mark + 1, nucleus)):
            return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                              ("Several stress marks share a nucleus; retaining engine notation.",))
        # Already onset-based notation is left in place (also makes this formatter
        # idempotent). The pinned engine normally places the mark at the nucleus.
        if mark + 1 != nucleus:
            onset = mark
            word_floor = max([0] + [i + 1 for i in range(mark) if atoms[i].text in _BREAKS]
                             + [i for i in floors if i <= mark])
            if not any(word_floor <= start < mark for start, _ in nuclei):
                onset = word_floor
        else:
            floor = max([0] + [end for start, end in nuclei if end <= mark]
                        + [i + 1 for i in range(mark) if atoms[i].text in _BREAKS]
                        + [i for i in floors if i <= nucleus])
            consonants = [i for i in range(floor, mark) if atoms[i].text not in STRESS]
            # Multiple primary stresses in one uninterrupted engine word can be
            # an unsegmented compound. Do not resyllabify its coda into the next
            # component without a verified boundary (icecream -> ice-scream).
            word_floor = max([0] + [i + 1 for i in range(mark) if atoms[i].text in _BREAKS])
            multiple_primary = sum(atoms[i].text == "ˈ" for i in range(word_floor, mark + 1)) > 1
            if ((compound_unverified or (multiple_primary and not boundaries))
                    and consonants and floor and atoms[floor - 1].text not in _BREAKS):
                return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                                  ("Compound boundary could not be verified; retaining engine notation.",))
            if any(atoms[i].nucleus or any(c not in _CONSONANTS and c not in _TIES
                                         for c in atoms[i].base) for i in consonants):
                return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                                  ("Onset could not be interpreted safely; retaining engine notation.",))
            if floor == 0 or floor in floors or (floor and atoms[floor - 1].text in _BREAKS):
                onset = consonants[0] if consonants else nucleus
            else:
                # Choose the longest licensed onset suffix. Unlike moving a mark
                # left once, this handles e.g. /str/ versus Portuguese /s.t/.
                onset = nucleus
                for position, index in enumerate(consonants):
                    cluster = "".join(atoms[i].base for i in consonants[position:])
                    if cluster in profile.onsets:
                        onset = index
                        break
                if consonants and onset == nucleus:
                    return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                                      ("No licensed onset interpretation; retaining engine notation.",))
        if onset in insertions:
            return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                              ("Ambiguous stress placement; retaining engine notation.",))
        insertions[onset] = atoms[mark].text
    if omit:
        notes.append("Redundant monosyllabic stress is omitted in the word display only; synthesis retains it.")
    notation = "ipa"
    if _EXTENSIONS.intersection(raw):
        notation = "engine"
        notes.append("Non-IPA weak-vowel engine symbol retained; no vowel quality was guessed.")
    formatted = "".join(insertions.get(i, "") + ("" if atom.text in STRESS else atom.text)
                        for i, atom in enumerate(atoms))
    # Defensive quality gate: formatting must never change, drop, or reorder a
    # segment, length, nasalization, tie bar, or other diacritic.
    if unicodedata.normalize("NFC", "".join(c for c in formatted if c not in STRESS)) != \
            unicodedata.normalize("NFC", "".join(c for c in raw if c not in STRESS)):
        return IpaDisplay(unicodedata.normalize("NFC", raw), "engine",
                          ("Display formatting would change phonetic segments; retaining engine notation.",))
    return IpaDisplay(unicodedata.normalize("NFC", formatted), notation, tuple(notes))
