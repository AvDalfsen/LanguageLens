# Language Lens

Language Lens is a Windows-first, local screen translator for language learning. Press a global hotkey from any application, drag around text in a frozen screenshot, and inspect it without sending the image anywhere. OCR outlines the words; hovering over one shows its translation, while a contextual translation of the whole selection stays visible below.

Screenshots and recognized text remain on the computer. The app uses [RapidOCR](https://github.com/RapidAI/RapidOCR) for OCR and [Argos Translate](https://github.com/argosopentech/argos-translate) for translation. Both need one-time model downloads, but neither needs a cloud API during play.

Optional pronunciation uses [Piper](https://github.com/OHF-Voice/piper1-gpl) to read the original selection aloud locally. No Windows voice packs, API keys or paid speech service are required.

## Current workflow

1. Open the app and choose the language shown on screen and the language you know.
2. Download the local Argos language model once.
3. Select a global capture hotkey and start listening.
4. From any application, press the hotkey and drag around text in the frozen full-screen frame.
5. The full frame remains visible. Hover over OCR words inside the selected region for individual translations; read the whole-selection translation below.
6. Press Escape to close the lens and focus the previously active application.

Hovering over a word shows only the model's **Best match** by default, along with the number of distinct candidates found. The app requests five Argos hypotheses, ranks them by model score, removes terminal-punctuation duplicates, and retains up to four candidates. Capitalization is preserved because it can distinguish meanings. Click **Show N other candidates** when the best match does not fit the sentence; the already-found alternatives then appear numbered **best → worst**. A candidate may contain several target-language words. Results appear progressively, with the whole-selection translation available first.

Word lookup preserves capitalization and combining marks, including Hindi vowel marks and Arabic diacritics. Japanese and Chinese use offline dictionary tokenizers selected by **Text language**, independently of the target language. Their dictionaries are installed with the app; no additional download is needed during capture. Segmentation remains an estimate, especially for names and unfamiliar compounds. OCR character coordinates are retained where the recognizer supplies usable alignment; otherwise outlines use an estimate that respects text direction, proportional font shaping and vertical text. The screenshot's exact font is unknown, so fallback outlines can still be imperfect. Whole-selection translation and pronunciation retain the original text and occurrence offsets.

Word candidates use the word **in isolation**, so the first choice can still have the wrong meaning in context. These are model suggestions, not an exhaustive dictionary of senses, and their ranking is not a percentage confidence. Use the whole-selection translation alongside them. If a model provides only one distinct result, the popup says so; if alternatives fail but the usual translation works, it explicitly shows a single-translation fallback.

After revealing the initial alternatives, click **Search for more candidates** to request a wider local search for that word. It shows every distinct result from **12 model guesses**, in model rank order, including inflections and numerical forms. If only one candidate was initially found, the search button is available immediately. The wider search can change the best match and ranking. The popup stays pinned while loading, and long lists scroll with the mouse wheel. **Show best match only** collapses the list; reopening it within the same screenshot reuses its results. If the search fails, the original result stays available alongside a retry button. This workflow applies to every supported translation route; no new models or language-specific filters are added. Twelve guesses are a bounded search, not all possible meanings.

## Read a selection aloud

1. Restart using `Start Language Lens.bat`. It installs the pinned speech runtime if missing.
2. In Settings, find **Read selected text aloud**, beneath the translation-model controls. Scroll down on smaller screens.
3. Choose a voice for the **Text language** and click **Download voice** (about 63 MB). Progress includes percentage and transferred bytes; the download can be cancelled and retried.
4. Use **Hear sample** to preview it. English offers US and UK voices; Portuguese (Portugal) and Portuguese (Brazil) each have a matching voice. The app remembers your choice for each language. Other text languages remain usable for translation, with pronunciation marked unavailable.
5. Capture some text and click **Read selection** in the review panel. This reads the original OCR text, not the translation, and is available before translation finishes. **Cancel audio** stops preparation; **Stop audio** stops playback. Closing the screenshot also stops speech.

The first playback prepares audio locally; replaying the same text and voice within that window reuses it. Nothing plays automatically. There is a 2,000-character limit per selection. OCR errors and ambiguous words can still cause pronunciation errors, so treat the voice as a learning aid rather than an authoritative pronunciation guide.

Voices live in `%LOCALAPPDATA%\LanguageLens\voices`, independently of translation packs and prototype fixtures. Downloads use a pinned upstream revision and SHA-256 checks. **Download / repair voice** verifies an existing installation and fetches only missing or damaged files. Completed files survive a cancelled download. Temporary job files are removed after completion or cancellation; an abrupt application or Windows crash may leave a `.job-*` folder in that voices directory. Audio is kept in memory for replay and cleared when the review closes; it is not added to a permanent recording history.

## Word pronunciation and optional IPA

In Settings, enable **Show IPA in word popups** to display estimated International Phonetic Alphabet transcriptions. It is off by default and independent of the audio checkbox. IPA uses the selected voice's accent and works without downloading that voice's audio model; it uses the pronunciation components already installed with the app. The initial accents are US/UK English and Portuguese from Portugal/Brazil.

Hover over a word to see its translation, IPA (when enabled), accent and **Pronounce word** button (when audio is enabled and the voice is installed). Move onto the popup to use its controls, or click the highlighted word to keep the popup open. Click another word to switch; click outside or use **×** to dismiss it. IPA can be selected and copied. Escape still closes the entire screenshot, including when a popup button has focus.

Pronunciation is prepared for the whole selection, independently of translation. **From selected sentence** means the word's phonemes have been mapped to that exact occurrence using native source positions and an exact comparison with the sentence phonemes. Repeated words are kept separate: the verb and noun in *I record a record* can have different transcriptions. Where boundaries cannot be mapped safely, **Word in isolation** marks a separately generated fallback. A failed preparation offers **Retry pronunciation** without disabling sentence playback or translation.

The word button synthesizes the exact underlying phonemes shown in the IPA, using the selected local voice. Once preparation is ready, sentence playback uses those prepared sentence phonemes too. Generated IPA is shown in square brackets and labelled **Estimated IPA**: it describes input to the synthesizer, not a phonetic measurement of its output. Mapping from sentence context does not guarantee linguistic correctness. In particular, the tested engine can give the same pronunciation to present and past-tense English *read*, and names, code-switching and OCR mistakes remain difficult.

Pronunciation preparation and playback are cancelled when the screenshot closes. No audio plays on hover, and there is no added download, cloud service or Windows voice-pack requirement for IPA.

The optional Escape helper captures first, then sends Escape to the active application. On exit it focuses that application and sends Escape again. Capturing first keeps any menu opened by Escape out of the frozen image.

## Recommended launcher

Double-click `Start Language Lens.bat` in the project folder. It checks whether the local Python environment and required packages are healthy, runs first-time setup or repair only when necessary, and then starts the app through the hidden launcher. The command window closes once the app starts.

Translation-language models remain managed by the button inside the app and are not downloaded again unnecessarily.

## Run the individual scripts

Use Python 3.10–3.12 on Windows x64. The speech integration has been exercised on Windows 10 22H2; Windows 11 is the intended primary target but has not been tested in this workspace. Windows 7/8/Vista and native ARM64 are not supported by this build.

```powershell
cd "C:\Users\Fillask\Desktop\GitHub repos\LanguageLens"
.\scripts\setup.ps1
.\scripts\run.ps1
```

`run.ps1` launches with `pythonw.exe` and exits immediately, so it does not leave a PowerShell window open.

The first setup is large because the local OCR and translation runtimes include neural-network dependencies. The first capture in a new writing system may download its RapidOCR recognition model. The app's **Download local translation model** button downloads the chosen Argos model; uncommon pairs are automatically routed through English when both legs are available.

Translation-model downloads show a byte-based progress bar, percentage, transferred/total size, recent download speed, and estimated time remaining. If the server does not provide a total size, the app shows transferred bytes and speed without inventing a percentage. A waiting-for-data message flags stalled transfers; connection/read timeouts trigger visible retries. Checking the model archive and installing it are separate stages with elapsed time. Routes needing two models show progress for each model separately, and complete cached downloads are verified and reused.

## Important limits

- Ordinary desktop and borderless-windowed applications are the most dependable. Exclusive fullscreen and DRM-protected video can produce a black capture because of how those programs present frames.
- The app sends ordinary keyboard input only for the optional Escape helper. It does not inject code or inspect another application's memory.
- A word translated alone can be ambiguous. The whole-selection translation is shown alongside it to preserve context.
- Word hit boxes are projected from OCR line boxes. They are accurate for ordinary horizontal subtitles, but curved, vertical, or highly stylized text may need a tighter selection. OCR processes only the crop, while the review keeps showing the full frozen desktop.
- An application may ignore synthetic Escape or use another shortcut. The frozen capture remains usable regardless.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Speech tests cover locale selection, download integrity and progress, cancellation, worker timeouts, late OCR results, and playback state. IPA tests cover exact source offsets (including combining accents), repeated words, explicit boundary fallbacks, opt-in settings, interactive popups, and transcription-to-audio consistency. If the stage-one voice fixtures are present, they also run real sentence and word synthesis for all four accents. Without fixtures, those four tests skip rather than downloading anything. The audio-device check uses muted playback and skips when no output device is available.

Translation-model tests cover streamed byte progress, missing file sizes, truncated or damaged archives, cache reuse, retry/mirror fallback, multi-model routes, and the UI's speed, remaining-time and stalled-transfer displays.

See [third-party speech notices](THIRD_PARTY_SPEECH.md) for runtime and voice provenance. Voice files are downloaded on demand and are not committed to this repository.

## Pronunciation research prototype

The separate [stage-one pronunciation prototype](prototypes/pronunciation/README.md)
tests offline sentence audio, generated IPA, and word audio using the same voice.
It includes a reproducible English/Portuguese corpus and a local listening report.
Its tested source-alignment approach is now integrated into the app for optional
IPA and word pronunciation, alongside sentence playback. The prototype remains
an independent research baseline; its environment, voices, and generated audio
live under the ignored `artifacts/` directory.

## Why this stack

- RapidOCR runs ONNX models locally and supports multilingual recognition, including a Latin-script model suitable for Portuguese, Dutch, English, French, German, Spanish, and related languages.
- Argos Translate is an open-source offline translation library. The model is downloaded once and then invoked in-process; there is no API quota or service refusal during a session.
- PySide6 provides the full-screen selector, frozen review view, system tray, and word-hover interface in one Windows desktop application.

