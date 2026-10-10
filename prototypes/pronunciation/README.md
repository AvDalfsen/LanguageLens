# Pronunciation prototype — stage one

This is a reproducible experiment, not an application feature. The screenshot UI,
launcher, translation service, and main Python environment are unchanged. It proves
local sentence synthesis and word synthesis from the same prepared phonemes, with
source-position checks before claiming a word came from its sentence context.

This directory is a frozen, independent reference for the experiment. Its copied
phoneme helpers deliberately preserve the original baseline; application fixes
belong in `src/language_lens`, with separate prototype tests checking this reference.

## Results from 2026-10-03

Tested on Windows 10 22H2 x64, Python 3.10.6, Piper 1.8.0, bundled eSpeak NG
1.52.0.1, ONNX Runtime 1.23.2. Windows 11 is not yet tested.

| Check | Result |
| --- | --- |
| Locales | en-US, en-GB, pt-PT, pt-BR |
| Corpus | 28 selections, 182 word/unit occurrences |
| Word-to-sentence phoneme mapping | 168 verified, 14 explicitly isolated fallbacks |
| Sentence/native-event phoneme agreement | 26 of 28 selections |
| Audio output | 210 valid WAV files; no generation errors |
| Prototype tests, including native engine and real voice synthesis | 32 passed |
| Existing application tests | 24 passed |
| Word audio reinterprets the spelling | No; synthesis consumes the exact prepared phonemes |
| Linguistic correctness | Not certified; known past-tense **read** failures |

The generated [listening report](../../artifacts/pronunciation/verified-prototype/index.html)
contains all sentence/word audio, IPA, source offsets, fallback reasons, and contrast
checks. The adjacent `report.json` contains timings and full provenance. These files
are local ignored artifacts, not committed test fixtures. Reproduce them using the
commands below if they are missing.

On this machine, loading a voice took approximately 1.4–1.6 seconds. Preparing all
selections for each locale took approximately 0.06–0.07 seconds; rendering all its
sentence and word samples took approximately 2.0–3.3 seconds. These are observed
prototype timings, not a benchmark while a game is running. CPU inference uses two
threads and needs no GPU. The report produces files; it does not test audio-device
playback or claim that a listener has evaluated the voices.

## What the experiment establishes

- eSpeak's word events carry source positions; its phoneme events carry IPA, including
  stress. The adapter uses the DLL already bundled with the pinned Piper wheel.
- Sentence phonemes follow Piper's eSpeak conversion. Native event phonemes must
  match that entire sequence exactly (ignoring boundary punctuation/spacing).
- A contextual word must map to a contiguous slice of a single sentence's actual
  phoneme sequence, with unambiguous source-word coverage. Word counts alone are
  never used to establish the mapping.
- The word audio and sentence audio both use the same Piper model. Word rendering
  receives the stored slice directly; it does not re-run text-to-phoneme conversion.
- Case, repeated occurrences, original Unicode offsets, decomposed accents, numbers,
  contractions, punctuation, multiple sentences, and literal markup are exercised.
- Unsupported voice phonemes cause a visible error rather than Piper's normal
  warning-and-drop behaviour. User screenshot text cannot request Piper's `[[raw
  phonemes]]` feature or SSML processing through this adapter.
- A parent process supervises disposable locale workers with a timeout. An engine
  failure cannot take down the current application because this prototype is separate.

`context` in the JSON/HTML means **the mapping was verified**, not that the word's
pronunciation is linguistically correct. Displayed IPA is NFC for readability;
the engine's NFD sequence is retained unchanged for synthesis.

## Limits found, with actual examples

1. **Grammar is approximate.** `I record a record.` produces distinct verb/noun
   pronunciations. `The Polish artist will polish the table.` preserves the relevant
   case distinction. But `I read books. Yesterday I read a book.` uses the present
   vowel for both instances in both English profiles. The listening report marks
   this contrast as FAILED. Structural test success must not hide this result.
2. **Merged words need fallback.** In `It is kind of a problem.`, eSpeak combines
   `of a`. Both word cards use clearly labelled isolated pronunciations; neither is
   presented as the combined contextual pronunciation. Four fallbacks in the corpus
   arise here, across the two English locales.
3. **Some number expressions disagree between engine interfaces.** For Portuguese
   `Custou €12,50 às 10:30.`, native phoneme events and Piper's phoneme text disagree.
   The conservative prototype falls back for all five units in each accent (ten
   fallbacks). Sentence audio still works. Per-clause recovery is a future refinement.
   Number and currency readings also require listening review even when mapping passes.
4. **A voice's exact phonemizer matters.** The Alan model uses `en-gb-x-rp`, not generic
   `en`. The model configuration is checked, and this exact profile is used by both
   paths. This identifies the model's pronunciation configuration, not a certification
   of the recorded speaker's accent.
5. **Single-word prosody differs.** Reusing the phones retains the generated sounds
   and stress, but a separately synthesized word has its own timing/intonation. It is
   not a clipped segment of the sentence. Especially reduced function words need
   listening evaluation as standalone learning examples.
6. **Linguistic review remains necessary.** The corpus is small, the Latin-language
   tokenizer is prototype-only, and no fluent-speaker quality assessment is claimed.
   Names, game terminology, code-switching, and unseen ambiguities can still be wrong.

Decision: the technical approach is suitable for proceeding to sentence playback
and settings. Contextual word guides can use this verified mapping with explicit
fallbacks, but the engine cannot be presented as reliably resolving all grammar.
Fluent-speaker listening review and distribution licensing remain release gates.

## Reproduce

Run from the repository root. Setup uses the existing app's Python to create a
separate virtual environment under the already ignored `artifacts/` directory.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-pronunciation-prototype.ps1
```

Download the four pinned research voices once (about 253 MB combined):

```powershell
.\artifacts\pronunciation\.venv\Scripts\python.exe -m prototypes.pronunciation.run download
```

To download just one voice, append `--locale pt-PT`, `pt-BR`, `en-GB`, or `en-US`.
Only this command accesses the network. Each file is checked against the pinned
upstream catalogue's size and MD5 integrity digest; MD5 is not claimed to authenticate
publisher identity. The upstream revision and HTTPS origin are fixed in `voices.json`.
Model cards are retained alongside the models. Failed partial downloads are removed;
existing verified files are reused.

Generate a fresh listening report offline (its path is printed when complete):

```powershell
.\artifacts\pronunciation\.venv\Scripts\python.exe -m prototypes.pronunciation.run suite
```

Use `--locale pt-PT` to run one accent, or `--output artifacts\pronunciation\my-run`
to select an empty output directory. Non-empty report directories are refused.
Open the generated `index.html` in a browser; it has local audio controls and no
external scripts, fonts, or network dependencies. Nothing plays automatically.

Try arbitrary text or one word occurrence (zero-based index):

```powershell
.\artifacts\pronunciation\.venv\Scripts\python.exe -m prototypes.pronunciation.run render --locale en-US --text "I record a record." --word 3
```

Run technical tests, including real audio tests when the models are installed:

```powershell
.\artifacts\pronunciation\.venv\Scripts\python.exe -m pytest prototypes\pronunciation\tests -q
.\.venv\Scripts\python.exe -m pytest -q
```

Each supervised locale has a 180-second timeout, configurable with `--timeout`.
Selections are limited to 2,000 characters. Long selections may exceed the timeout;
the parent terminates that worker and records an error. `suite` exits unsuccessfully
for worker/audio failures. Linguistic contrast failures are reported separately in
`failed_contrasts`, since a working pipeline does not establish linguistic accuracy.

## Boundaries and distribution

- No Windows language settings, voices, registry keys, or privileges are changed.
- No production voice manager, playback UI, word popover, or settings migration is
  included in this stage. There is no service/API dependency during rendering.
- The tests use Piper's exported native ABI in a pinned Windows wheel. That ABI is
  version-sensitive; other platforms and future engine releases need new validation.
- Treat `Pronouncer` and `VoiceRenderer` as experimental worker-only components.
  eSpeak is globally stateful. Calls are serialized and callbacks unregistered after
  use; do not mix this adapter with independent eSpeak consumers in the same process.
- Keep downloaded runtimes, model weights, and audio reports out of Git. They already
  live under the project's ignored `artifacts/` directory. The existing app's MIT
  licence has not been changed.
- Piper and eSpeak have GPL obligations. Model cards for the Portuguese fixtures
  describe CC0 datasets; the English cards refer to separate dataset licence pages.
  Dataset labels are not a completed licence review of every model and its training
  provenance. No permission to redistribute these fixtures is asserted here.

Primary implementation references:

- [Piper 1.8.0 synthesis](https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/src/piper/voice.py)
- [Piper 1.8.0 phonemizer](https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/src/piper/phonemize_espeak.py)
- [eSpeak native API](https://github.com/espeak-ng/espeak-ng/blob/master/src/include/espeak-ng/speak_lib.h)
- [eSpeak contextual pronunciation rules](https://github.com/espeak-ng/espeak-ng/blob/master/docs/dictionary.md)
- [Pinned upstream voice catalogue](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/voices.json)
- [Piper licence](https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/COPYING)
- [eSpeak licence](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING)
