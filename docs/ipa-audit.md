# IPA audit — 2026-10-05

## Scope and decision

Reviewed the production path: OCR occurrence offsets, voice/accent selection,
Unicode normalization, native phonemization/events, exact contextual alignment,
isolated fallback, popup text/labels/tooltips, word and sentence synthesis, worker
failure/cancellation, and tests. The tracked stage-one prototype/corpus served as
historical evidence, not as the app's implementation. Ignored generated artifacts
and downloaded models were not audited or changed.

IPA is currently offered for **en-US, en-GB, pt-PT and pt-BR** only. Translation's
larger language list does not imply IPA support. Unsupported accents never inherit
an English display profile. Adding a voice/locale requires explicit tests/profile
review; the tests check coverage of every shipping voice.

Keep Piper 1.8.0 and its voice-matched eSpeak frontend. Changing the phonemizer's
symbol inventory or stress input would change what the pinned audio models receive.
Separate conventional display formatting from synthesis instead. No new packages,
voice downloads, dictionary service, API or OS settings changes were required.

## Findings and fixes

| Finding | Resolution |
| --- | --- |
| Raw eSpeak stress sits before a nucleus, not necessarily before its onset. | Display-only accent-specific maximal-onset formatter. Both primary and secondary markers are handled; no dots claiming complete dictionary syllabification are inserted. |
| A one-character shift breaks consonant clusters, affricates and vowel-initial syllables. | Parse phonetic segments/diacritics, recognize diphthongs and syllabic consonants, and choose a licensed onset suffix. Initial syllables start at their word/component boundary. |
| English onset/diphthong rules cannot simply be exported to Portuguese. | Explicit per-accent profiles; Portuguese /s.t/ is not treated as English /st/. Nasalized vowels and glides keep their original marks. |
| Monosyllabic stress is redundant in a standalone lexical-style card, but may convey utterance prominence. | Omit it only in an unexpanded, single-nucleus display. Retain every original stress marker in synthesis and expose the original stream in the tooltip. Multiword expansions, compounds, multiple markers, and uncertain vowel sequences retain stress. |
| Hyphenated compounds and initialisms may have no phonemic spaces. Resyllabification can turn ice-cream into ice-scream or attach the /s/ of S to A in USA. | Probe component readings, accepting boundaries only when all non-stress segments match the original stream exactly. Never substitute those probe readings for contextual sounds. Failed/ambiguous proofs fall back to explicitly labelled engine notation. |
| Unsegmented multiple-primary-stress compounds may also have no source hyphen. | Do not guess a medial component boundary. Preserve raw engine notation where moving stress could cross it. |
| Piper strips language-switch flags before synthesis. A display rule for the surrounding language may then be wrong for the switched language. | Preserve switch metadata separately; do not guess syllabification for switched sentences. Audio's existing transformation is unchanged. |
| The US frontend emits the weak-vowel extension ᵻ; replacing it with ə or ɪ would invent a more specific quality. | Keep the symbol and label the result Engine notation, explaining the non-IPA extension. Recognized stress can still be repositioned without substituting sounds. |
| NFC display alone does not establish proper transcription conventions. | Preserve immutable NFD synthesis input and original source spans. Display may only relocate stress, omit the narrowly defined redundant stress, and apply Unicode NFC. A defensive segment-preservation check rejects any other transformation. |
| Combining marks, tie bars, rhoticity, aspiration and syllabic/non-syllabic marks can be detached by character manipulation. | Keep segment clusters/modifiers together, support both tie-bar forms and syllabic marks above/below, and test NFC/NFD equivalence. Malformed or unknown notation is not silently simplified. |
| An optional component probe could fail after contextual pronunciation was already prepared. | A failed proof leaves the original pronunciation available and uses engine notation; it does not discard contextual audio. |
| The pronunciation module duplicated a weaker Unicode offset normalizer. | Reuse the app's complete-grapheme NFC mapping, including decomposed accents, Hangul composition and emoji sequences. |
| Lone UTF-16 surrogate code points could fail at native UTF-8 conversion. | Reject malformed Unicode before reaching the native adapter or speech worker. |
| UI text implied the display string was passed verbatim to synthesis. | Corrected documentation/tooltips; display notes and original phonemes are inspectable. Engine notation and estimated IPA are visibly distinguished. IPA is explicitly left-to-right and copyable plain text. |

Examples using the engine's segment choices, not a new dictionary pronunciation:

| Source | Old display | New display |
| --- | --- | --- |
| capitalization, UK | [kˌæpɪtəlaɪzˈeɪʃən] | [ˌkæpɪtəlaɪˈzeɪʃən] |
| marks, UK | [mˈɑːks] | [mɑːks] |
| offline, UK | [ˈɒflaɪn] | [ˈɒflaɪn] |
| coração, Portugal | [kˌuɾɐsˈɐ̃ʊ̃] | [ˌkuɾɐˈsɐ̃ʊ̃] |
| questão, Portugal | [kɨʃtˈɐ̃ʊ̃] | [kɨʃˈtɐ̃ʊ̃] |
| ice-cream, UK | [ˈaɪskɹˈiːm] | [ˈaɪsˈkɹiːm] when the component proof succeeds |
| USA, US | [jˌuːˌɛsˈeɪ] | [ˌjuːˌɛsˈeɪ] when the letter proof succeeds |

## Safeguards retained

- Context means exact source-occurrence and sentence-phoneme mapping, not a guess
  from word counts or a promise that the engine resolved grammar correctly.
- Repeated spellings keep separate occurrences. The verb/noun contrast in
  *I record a record* remains intact.
- Merged events such as *of a* use explicitly isolated fallbacks for both words;
  neither receives the combined phrase as its own pronunciation.
- Split OCR units and currency/number fragments cannot claim the pronunciation of
  their entire containing unit.
- Sentence/word rendering consumes original phonemes, not formatted IPA. It never
  reinterprets screenshot `[[text]]` as a user-supplied phoneme instruction.
- Exact accent/model configuration checks and unsupported-model-symbol errors
  remain enabled. Unsupported phonemes must not disappear silently in audio.
- Native libraries stay in disposable, serial worker processes. Closing the review
  cancels preparation/playback; late results are rejected against text, voice and
  source spans. IPA remains independent of translation and optional audio downloads.

## Validation

Regression tests cover all shipping accents, the user's screenshots, primary and
secondary stress, clusters, tied affricates/diphthongs, nasal diphthongs, hiatus,
syllabic consonants, modifiers, composed/decomposed Unicode, expansions,
initialisms/acronyms, compounds, code switching, malformed/unknown notation,
unavailable profiles, optional-probe failures, occurrence alignment, popup labels,
copyable LTR text, and untouched audio input. Generated cluster combinations check
segment order, diacritics, stress-marker counts and unchanged stressed-nucleus
positions independently of the onset formatter.

Real Piper/eSpeak workers exercise all four accents without an audio-model
download. The production worker is tested through its normal JSON protocol, not
only by calling the formatter. Tests assert that every contextual word remains an
exact slice of its stored sentence phonemes. The rendering test captures the
original stress-bearing input at Piper's phoneme-ID conversion boundary.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_ipa.py tests/test_pronunciation.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider -k 'not installed_fixture'
```

The four optional audio-model fixture tests are deliberately excluded: they read
ignored stage-one downloaded artifacts. No claim of new fluent-speaker listening
validation or testing on another Windows version is made.

Results on the current Windows environment: **146 IPA/pronunciation tests passed**;
the broader application run completed with **288 passed, 4 deliberately deselected**.
`git diff --check` reported no whitespace errors. These are technical regression
results, not a certification of linguistic accuracy.

## Remaining limits — do not disguise them as formatting fixes

1. **Syllabification is an estimate.** Maximal onset is a documented convention,
   not a universally correct morphological/dictionary analysis. For example,
   prefix/compound boundaries and ambisyllabicity can yield different defensible
   placements. The tooltip identifies this method. Exact phoneme quality/order
   and stressed nucleus are retained; dictionary-level boundaries need a reviewed
   accent-specific lexical resource. No hand-written word exceptions were added.
2. **Pronunciation disambiguation remains imperfect.** The backend still gives
   present/past *read* the same vowel in the known test phrase. Fixing stress
   typography does not fix this. Arbitrarily overriding phones would also change
   speech quality. Names, invented words and OCR errors still need human judgment.
3. **Context recovery is conservative.** Interface disagreement, particularly
   with Portuguese numbers/currency, can make the entire selection use isolated
   word fallback. Per-clause recovery needs a separate alignment design; it must
   not relax the exact-match guarantee.
4. **The display is not a measurement of generated audio.** Piper predicts timing,
   intonation and acoustic detail. Brackets identify an estimated pronunciation,
   not an audio-verified narrow transcription. Isolated word playback has different
   prosody from the sentence even when its source phones are preserved.
5. **Some cases remain engine notation.** Unsupported extensions, unknown sounds,
   unverified compound boundaries or switching are made explicit, not advertised
   as fully standardized IPA. Switching metadata is conservative at sentence
   level, so an otherwise ordinary word can also receive this label.
6. **Support does not automatically generalize.** Tone, pitch accent, moraic
   systems, languages with different clusters, and additional accents require
   their own frontend/display review. They are not newly enabled by this change.

## Voice-catalogue follow-up — 6 October 2026

Audio now covers all 25 text-language entries (26 voices). This does **not**
extend English/Portuguese syllabification conventions to other languages.
Audited display profiles remain en-US, en-GB, pt-PT and pt-BR. Other supported
eSpeak frontends keep their phones unchanged and are labelled engine notation;
Japanese uses OpenJTalk and explicitly isolated word readings. Its pitch cues
are not claimed as conventional IPA. Exact engine phones, not reformatted
display strings, still drive audio. Native-speaker assessment and additional
language-specific transcription reviews remain separate work.

All 26 voices passed normal-speed and 0.75× real synthesis/integrity checks.
See [audit follow-up](audit-followup.md) for the current full regression result
and the distinction between technical verification and pronunciation quality.

## Primary references

- [Cambridge IPA/stress examples](https://dictionary.cambridge.org/pt/help/phonetics.html): onset-based primary/secondary stress examples.
- [International Phonetic Association chart](https://www.internationalphoneticassociation.org/IPAcharts/IPA_charts_EI/IPA_charts_EI.html): stress, length, syllabicity, non-syllabicity and other IPA symbols.
- [eSpeak 1.52.0 phoneme-output implementation](https://github.com/espeak-ng/espeak-ng/blob/1.52.0/src/libespeak-ng/dictionary.c): stress emitted for syllabic/nuclear entries; there is no public output-mode flag that supplies dictionary syllabification.
- [eSpeak US weak-vowel definition](https://github.com/espeak-ng/espeak-ng/blob/1.52.0/phsource/ph_english_us): the I# phone explicitly emits ᵻ.
- [eSpeak output-mode API](https://github.com/espeak-ng/espeak-ng/blob/1.52.0/src/include/espeak-ng/speak_lib.h): phoneme separators/ties are not syllable-boundary metadata.
- [Pinned Piper phonemizer](https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/src/piper/phonemize_espeak.py): NFD input and removal of language-switch annotations.
- [Pinned Piper synthesis](https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/src/piper/voice.py): separate phonemization and phoneme-ID rendering paths.
- [English stress/syllabification research](https://www.cambridge.org/core/journals/phonology/article/weight-and-final-vowels-in-the-english-stress-system/30EDBFA90E382F68C400EEFCFC0DA31D): ambiguity and limitations of unrestricted maximal onset.
- [European Portuguese syllable-structure study](https://revistas.pucsp.br/delta/article/download/43469/28917/123608): Portuguese onset/coda constraints, rather than English cluster rules.
