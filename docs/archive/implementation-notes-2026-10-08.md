# Implementation notes before the presentation refresh

Historical snapshot from 8 October 2026. See [current documentation](../README.md) for installation and use. The former README is preserved below.

# Language Lens

Windows portable release tooling is available for a local executable preview.
See [building and verifying a release](../release-building.md). The preview
uses ONNX sentence splitting without bundled PyTorch/Stanza and downloads
Japanese/Chinese components as optional language packs. See
[language packs and updates](../language-packs.md) and
[sentence models and validation](../sentence-splitting.md).

Language Lens is a Windows-first, local screen translator for language learning. Press a global hotkey from any application, drag around text in a frozen screenshot, and inspect it without sending the image anywhere. OCR outlines the words; hovering over one shows its translation, while a contextual translation of the whole selection stays visible below.

Screenshots and recognized text remain on the computer. The app uses [RapidOCR](https://github.com/RapidAI/RapidOCR) for OCR and [Argos Translate](https://github.com/argosopentech/argos-translate) for translation. Both need one-time model downloads, but neither needs a cloud API during play.

Optional pronunciation uses [Piper](https://github.com/OHF-Voice/piper1-gpl) to read the original selection aloud locally. No Windows voice packs, API keys or paid speech service are required.

## Current workflow

1. Open the app and choose the language shown on screen and the language you know.
2. Click 'Download required files'. This installs missing translation/OCR assets, prepares auxiliary sentence models, and verifies a fixed sample without networking. Voices are separate optional downloads.
3. Choose 'Capture hotkey' (F8 by default for new settings): click the field and press your preferred key combination, or use 'Reset to F8'. Choose 'Capture area': 'All monitors' (default) or 'Monitor under the pointer'. Click 'Start listening'.
4. From any application, press the hotkey and drag around text in the frozen full-screen frame.
5. The full frame remains visible. Hover over OCR words inside the selected region for individual translations; read the whole-selection translation below. Click a word to pin its details; the left and right arrow keys continue from that word.
6. Use 'Retry OCR', 'Select another area', 'Retry translation', or 'Copy source text' if needed. Reselection and OCR retries reuse the frozen screenshot. An OCR retry clears old text/audio; 'Read selection' stays disabled until new text is recognized. Long translations scroll; 'Hide translation' collapses the sentence without hiding controls.
7. Press Escape to close the lens and focus the previously active application.

The main 'Start listening' button becomes 'Pause listening' while listening is requested. 'Capture hotkey' shows the configured shortcut and is locked while listening; pause first to choose a different shortcut, then click 'Start listening' to resume. The global registration is temporarily suspended while 'Settings', selection, or review owns the keyboard, then restored when returning to another application. A registration conflict on restoration leaves listening inactive with an explanation. Pausing disables the shortcut without closing Lens. 'Try a capture now', 'Start listening' and tray capture require verified OCR and translation files, not merely an installed translation model. Capture and model/voice maintenance exclude one another consistently across Settings, tray and dispatch. Changing language pairs or checking/replacing models invalidates readiness; click 'Start listening' after successful verification to resume. Launching Lens again reopens the existing instance instead of creating another tray app. Use the left and right arrow keys to browse and pin recognized words; Tab reaches popup controls. Nothing is pronounced automatically.

The tray menu also switches between 'Start listening' and 'Pause listening' to match requested listening; the tray tooltip explains temporary shortcut suspension. Starting is disabled until the local files are verified and while a capture or file task is open; pausing requested listening remains available. Enabled menu items highlight on hover or keyboard selection; unavailable actions use muted grey text without a hover highlight.

Clicking 'Capture hotkey' displays 'Listening for new hotkey...'. Leaving the field without entering a new shortcut restores the previous value, including if you only pressed modifiers. The prompt itself never changes the saved shortcut.

Custom shortcuts are remembered immediately, without needing to start listening. Existing saved shortcuts are preserved. The recorder accepts one key combined with optional Ctrl, Alt and Shift: A–Z, 0–9, function keys F1–F24 except F12, Space, Enter, Escape, Backspace, Pause and navigation keys. Tab moves between controls while recording; modified Tab can be recorded. Punctuation, mouse buttons, multi-step sequences and Windows-reserved keys/combinations are not supported. Prefer function keys or modifiers to avoid interfering with typing. Invalid input explains the restriction and disables listening; registration conflicts are reported by Windows without silently changing the shortcut.

'Pronunciation speed' is a slider below the screenshot's action buttons, not a setting you have to leave the screenshot to change. It ranges from 0.5× to 1.5× and applies to words and the whole selection without changing pitch. Changing speed stops current audio; play the word/selection again to hear the new speed. The choice is remembered across captures and restarts, and also applies to voice samples. When the slider has keyboard focus, arrow keys adjust speed instead of browsing words.

Capture retains every monitor's original physical pixels for OCR, independently of Windows display scaling. The selector and review use synchronized native windows on each captured monitor, including monitors to the left of or above the primary display. Each window displays its own portion of the frozen desktop at that monitor's scale; the review is not squeezed onto one monitor. Display rendering uses the original monitor images too. The single-monitor option uses the pointer position when capture starts, before the brief delay that hides Settings.

With mixed-DPI monitors, OCR processes each selected monitor region at its own native resolution and maps line and word boxes back to the frozen screenshot, including padded retries. A selection spanning monitors is read in visual order. Blank gaps between monitors are not OCR input; a selection entirely in a gap remains open so you can choose again. Controls and word popups are anchored on an actual monitor near the selection. Text physically split across monitor boundaries is recognized separately and is not guaranteed to be reconstructed as one word.

The coordinate handling follows Qt's distinction between [logical screen geometry and physical image pixels](https://doc.qt.io/qt-6/highdpi.html), using actual captured dimensions rather than assuming one scale factor for the entire desktop.

Settings tooltips appear after about 50 ms and explain what each option does and its tradeoffs. For example, limiting capture to the monitor under the pointer leaves other screens uncovered and reduces memory and rendering work; it does not change OCR accuracy.

The Settings window initially sizes itself to fit its contents, trying a wider layout before resorting to scrolling, within the current monitor's available desktop area (excluding the taskbar). Scrollbars remain available on smaller screens or if you deliberately shrink the window. Manual sizes and maximized state are remembered across restarts and take precedence over automatic fitting; saved sizes are temporarily clamped when opening on a smaller screen. Valid preferences are autosaved after a short debounce and flushed on hide/shutdown. Changes do not alter the settings snapshot used by an already-started capture. The first close explains that Lens stays running in the tray.

The review panel remains visible and normally anchors above or below the selected area. Drag its background or non-selectable text to reposition it within the current screen; buttons, sliders and scrollbars retain their normal behavior. There is no extra drag toolbar or automatic folding. On narrow screens the buttons reflow and scroll, while the single 'Close and return' button stays outside the scrolling actions. Escape still closes the screenshot. Manual placement lasts for the current screenshot; new captures anchor to their own selection.

Failed model inspections report an unknown installation state, rather than incorrectly claiming files are missing. 'Retry file check' retries inspection without downloading. Categorized worker errors distinguish connection, access, disk-space, verification, unavailable-route and runtime problems. 'Open diagnostics folder' exposes sanitized diagnostic files without including captured text.

The batch launcher validates a supported Windows x64 Python (3.10–3.12) and the installed dependencies before launching. If recovery is needed, it first locates a compatible interpreter, then preserves the exact project environment as a `.venv.backup-*` directory before rebuilding it. It does not remove translation models, voices or preferences. Launch success requires a startup acknowledgement; early exits, reported errors and startup timeouts remain visible in the launcher instead of silently closing it.

See the [workflow audit implementation report](../workflow-ui-fixes-2026-10-06.md) for changes to points 1–12 and validation limits.

'Settings' keeps readiness and any required 'Download required files' action prominent. Once ready, optional 'Check required files', 'Reinstall translation model' and 'Remove translation' actions are under 'Manage local files'. Route, segmentation and notation explanations are under 'Technical details'. Download progress and cancellation remain visible without opening either section; pronunciation controls and the IPA accent explanation retain their existing behavior.

The review panel's optional 'Recognized text' section shows the original OCR output, read-only. Both source and whole-selection translation can be selected and copied; right-click for 'Copy selection' or 'Copy all'. This inspection does not alter word outlines, source offsets or pronunciation. During translation, the existing status shows completed/pending unique word lookups and identifies unavailable results. Repeated words reuse one lookup. Keyboard focus follows visual order, with visible focus highlights and descriptive accessible names. These improvements do not make pointer-based region selection or custom-painted word outlines fully screen-reader-accessible.

OCR input is converted directly from Qt images to owned, contiguous BGR pixel arrays, matching [RapidOCR's NumPy input convention](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/utils/load_image.py). This preserves red/blue channel order on initial scans, native monitor crops, and enlarged retries; screenshot display colours are unchanged.

Hovering over a word shows only the model's 'Best match' by default, along with the number of distinct candidates found. The app requests five Argos hypotheses, ranks them by model score, removes terminal-punctuation duplicates, and retains up to four candidates. Capitalization is preserved because it can distinguish meanings. Click 'Show N other candidates' when the best match does not fit the sentence; the already-found alternatives then appear numbered **best → worst**. A candidate may contain several target-language words. Results appear progressively, with the whole-selection translation available first.

Word lookup preserves capitalization and combining marks, including Hindi vowel marks and Arabic diacritics. Japanese and Chinese use offline dictionary tokenizers selected by 'Text language', independently of the target language. Their dictionaries are optional packs installed by Download required files for those source languages; capture never downloads them. Segmentation remains an estimate, especially for names and unfamiliar compounds. OCR character coordinates are retained where the recognizer supplies usable alignment; otherwise outlines use an estimate that respects text direction, proportional font shaping and vertical text. The screenshot's exact font is unknown, so fallback outlines can still be imperfect. Whole-selection translation and pronunciation retain the original text and occurrence offsets.

Word candidates use the word **in isolation**, so the first choice can still have the wrong meaning in context. These are model suggestions, not an exhaustive dictionary of senses, and their ranking is not a percentage confidence. Use the whole-selection translation alongside them. If a model provides only one distinct result, the popup says so; if alternatives fail but the usual translation works, it explicitly shows a single-translation fallback.

Click 'Search for more candidates' directly in the word popup to request a wider local search; revealing the initial alternatives first is not required. It shows every distinct result from **12 model guesses**, in model rank order, including inflections and numerical forms. The wider search can change the best match and ranking. The popup stays pinned while loading, and long lists scroll with the mouse wheel. 'Show best match only' collapses the list; reopening it within the same screenshot reuses its results. If the search fails, the original result stays available alongside a retry button. This workflow applies to every supported translation route; no new models or language-specific filters are added. Twelve guesses are a bounded search, not all possible meanings.

## Read a selection aloud

1. Restart using 'Start Language Lens.bat'. It installs the pinned speech runtime if missing.
2. In 'Settings', find 'Enable functionality to read selected text aloud', beneath the translation-model controls. Scroll down on smaller screens.
3. Choose a voice for the 'Text language' and click 'Download voice'. 'Settings' shows its download size (roughly 63–114 MB); progress includes percentage, transferred bytes, speed, elapsed time, an estimated remaining time and waiting-for-data feedback. Checking and verification use separate stages, so reaching 100% transferred does not claim the voice is ready before verification completes. The download can be cancelled and retried.
4. Use 'Hear sample' to preview it. All 25 text-language choices have a local voice, with 26 voices including US/UK English. Portuguese (Portugal) and Portuguese (Brazil) each have a matching voice. The app remembers your choice for each language. Japanese also downloads its optional pronunciation pack; no Windows voice pack is required.
5. Capture some text and click 'Read selection' in the review panel. This reads the original OCR text, not the translation, and is available before translation finishes. 'Cancel audio' stops preparation; 'Stop audio' stops playback. Closing the screenshot also stops speech.

The 'Pronunciation speed' slider in the review panel ranges from 0.5× to 1.5×. It changes synthesis duration, not playback pitch, and applies to samples, words and sentences; the choice is remembered. When focused, the slider's left and right arrow keys adjust speed instead of browsing words. The first playback prepares audio locally; replaying the same text, voice and speed within that window reuses it. Nothing plays automatically. There is a 2,000-character limit per selection. OCR errors and ambiguous words can still cause pronunciation errors, so treat the voice as a learning aid rather than an authoritative pronunciation guide. Technical synthesis checks are not native-speaker listening validation.

Read 'Voice details and licence' before downloading or redistributing models. Some catalogue voices have noncommercial terms, and others have incomplete licence information. The repository's MIT licence does not cover these models or the GPL speech runtime. See [speech notices](../../THIRD_PARTY_SPEECH.md).

Voices live in `%LOCALAPPDATA%\LanguageLens\voices`, independently of translation packs and prototype fixtures. Downloads use a pinned upstream revision and SHA-256 checks. 'Check voice files' verifies an existing installation and fetches only missing or damaged files. Completed files survive a cancelled download. Temporary job files are removed after completion or cancellation; an abrupt application or Windows crash may leave a `.job-*` folder in that voices directory. Audio is kept in memory for replay and cleared when the review closes; it is not added to a permanent recording history.

## Word pronunciation and optional IPA

In Settings, enable 'Show IPA in word popups' to display optional phonetic details. It is off by default and independent of the audio checkbox. Notation uses the selected voice's accent and works without downloading that voice's audio model; it uses local pronunciation components, including the optional Japanese pronunciation pack when Japanese is selected. Audited IPA display conventions cover US/UK English and Portuguese from Portugal/Brazil. Other languages preserve the frontend output and explicitly label it 'Engine notation'; English stress/syllabification rules are not imposed on them. Japanese word readings are isolated, and its engine pitch cues are not advertised as conventional IPA or reliable contextual pitch accent.

Hover over a word to see its translation, IPA (when enabled), accent and 'Pronounce word' button (when audio is enabled and the voice is installed). Move onto the popup to use its controls, or click the highlighted word to keep the popup open. Click another word to switch; click outside or use '×' to dismiss it. IPA can be selected and copied. Escape still closes the entire screenshot, including when a popup button has focus.

Pronunciation is prepared for the whole selection, independently of translation. 'From selected sentence' means the word's phonemes have been mapped to that exact occurrence using native source positions and an exact comparison with the sentence phonemes. Repeated words are kept separate: the verb and noun in *I record a record* can have different transcriptions. Where boundaries cannot be mapped safely, 'Word in isolation' marks a separately generated fallback. A failed preparation offers 'Retry pronunciation' without disabling sentence playback or translation.

The word button synthesizes the original prepared phonemes, using the selected local voice. Once preparation is ready, sentence playback uses the prepared sentence phonemes too. Display formatting never changes that synthesis input. In the popup, primary and secondary stress precede estimated syllable onsets, using separate English and Portuguese profiles. Redundant stress is omitted only for an unexpanded, single-nucleus word display; the underlying stress remains available in the IPA tooltip and is retained for audio. Length, vowel quality, nasalization, syllabic consonants, glides and other diacritics are preserved.

Generated IPA is shown in square brackets and labelled 'Estimated IPA', not as a phonetic measurement of the voice's output. Onset placement uses an accent-specific maximal-onset estimate, not an authoritative dictionary or morphological syllabification. Verified hyphenated components and spelled-out initials keep their boundaries. Where a boundary cannot be interpreted safely, language switching is detected, or a non-standard engine symbol occurs (such as the US profile's weak-vowel **ᵻ**), the popup instead says 'Engine notation' and explains why in its tooltip. It preserves the phoneme output rather than guessing a different sound. Hover over the transcription to inspect formatting notes and the original synthesis phonemes.

Mapping from sentence context does not guarantee linguistic correctness. In particular, the tested engine can give the same pronunciation to present and past-tense English *read*, and names, code-switching and OCR mistakes remain difficult. The [IPA audit](../ipa-audit.md) records conventions, safeguards, tests and remaining limitations.

Pronunciation preparation and playback are cancelled when the screenshot closes. No audio plays on hover. Japanese phonetic notation needs its optional pronunciation pack, which can be downloaded with audio turned off. Other languages use the bundled pronunciation runtime; no cloud service or Windows voice pack is required.

Lens does not pause or resume other applications and never sends them synthetic keystrokes. Pause a game manually before capturing if needed; otherwise it continues running behind the frozen screenshot. Escape closes Lens's screenshot only. Closing the selector (including Alt+F4) cancels capture and leaves Lens ready for the next capture.

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

The source setup remains large because local OCR and translation include neural-network dependencies. The portable preview trims that runtime; Japanese/Chinese dictionaries and Japanese pronunciation are optional packs. Capture does not download assets: use 'Download required files' for each source/target pair first. This single setup action handles missing translation, OCR and sentence-boundary files; uncommon pairs are routed through English when both legs are available. An installed translation route is not the same as complete offline readiness.

Translation-model downloads show a byte-based progress bar, percentage, transferred/total size, recent download speed, and estimated time remaining. If the server does not provide a total size, the app shows transferred bytes and speed without inventing a percentage. A waiting-for-data message flags stalled transfers; connection/read timeouts trigger visible retries. Checking the model archive and installing it are separate stages with elapsed time. Routes needing two models show progress for each model separately, and complete cached downloads are verified and reused.

## Offline readiness and recovery

Settings reports translation routes, offline verification, word segmentation and phonetic-display support separately. Voice readiness is independent. 'Check required files' reruns preparation and the fixed-sample check. Changing a relevant runtime version, removing models or changing recorded asset size/mtime invalidates that preparation marker. OCR and voice files are also SHA-256 checked before loading; the translation readiness marker is not a cryptographic signature or protection against malicious model changes.

OCR, translation, status checks and speech run in supervised local processes, so native model crashes do not normally take down the interface. OCR/translation/search have a 120-second inactivity limit; model tasks allow five minutes without meaningful progress. Status checks have a 30-second limit. Speech preparation has separate bounded timeouts. Failed sentence translation does not prevent word lookup; errors stop displaying a perpetual “Translating…” state and offer recovery. Closing review cancels its tasks and audio.

Argos is forced to its local provider. Capture and speech tasks disable Python outbound socket connections and automatic Stanza downloads. This guards against implicit library downloads; it is not an OS firewall/security sandbox. Only explicitly requested preparation/download/repair operations go online, using fixed sample text for preparation rather than screenshots.

'Reinstall translation model' validates replacement packages before publishing them and keeps previous versions as backups. 'Remove translation' moves the active route's packages to recoverable backups beside the Argos packages directory, including shared pivot models after confirmation. Removing shared models can affect other language pairs. Backups are not automatically erased and do not reclaim disk space. Interrupted replacements retain a journal and recover on the next model operation; captures never attempt online recovery. Capture is unavailable during active model/voice downloads or model maintenance.

Replacement validation loads the staged tokenizer and weights and runs a fixed sample with networking disabled before retiring any installed version of that language pair. Replacement/removal handles duplicate versions together. Completed downloads persist under `%LOCALAPPDATA%\LanguageLens\model-cache`, identified by model version and download links and checked before reuse. Older archives are pruned toward a 2 GiB cache limit while retaining the current download; interrupted transfers remain in disposable job directories. Recoverable installed-model backups remain separate from that cache.

Configuration writes are atomic and malformed values fall back to defaults. Rotating diagnostics are in `%LOCALAPPDATA%\LanguageLens\logs`; they record stages, exception types and stack locations, not selected text, screenshot contents or exception messages. OCR workers briefly save only selected/padded regions under `%LOCALAPPDATA%\LanguageLens\jobs` and remove them after completion/cancellation. A hard crash or power loss can leave temporary job files containing sensitive content; do not share them as diagnostics. No permanent screenshot/audio history is created.

## Important limits

- Ordinary desktop and borderless-windowed applications are the most dependable. Exclusive fullscreen and DRM-protected video can produce a black capture because of how those programs present frames.
- The app does not send keyboard input, inject code, suspend processes, or inspect another application's memory.
- A word translated alone can be ambiguous. The whole-selection translation is shown alongside it to preserve context.
- Word hit boxes are projected from OCR line boxes. They are accurate for ordinary horizontal subtitles, but curved, vertical, or highly stylized text may need a tighter selection. OCR processes only the crop, while the review keeps showing the full frozen desktop.
- Returning to the previous application is best-effort: Windows can refuse a focus change. Visible maximized windows retain their size; a minimized window is restored before focusing.

## Tests

For the complete multilingual source suite, install the developer and optional
language dependencies first (`pip install -e ".[dev,language-packs]"`). The normal
launcher installs the core; it does not install optional language packs for tests.

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Speech tests cover locale selection, download integrity and progress, cancellation, worker timeouts, late OCR results, and playback state. IPA tests cover exact source offsets (including combining accents), repeated words, explicit boundary fallbacks, opt-in settings, interactive popups, and transcription-to-audio consistency. Optional sentence/word audio-fixture tests use `artifacts/voice-validation/<voice-id>` with the older prototype locale folders as a fallback, and skip when fixtures are absent rather than downloading anything. Set `LANGUAGE_LENS_TEST_VOICES` to override the fixture root. The separate all-voices verification script exercises normal/slower synthesis. The audio-device check uses muted playback and skips when no output device is available.

Translation-model tests cover streamed byte progress, missing file sizes, truncated or damaged archives, cache reuse, retry/mirror fallback, multi-model routes, and the UI's speed, remaining-time and stalled-transfer displays.

Technical repair regressions cover staged model inference, atomic version replacement and crash recovery, duplicate removal, archive collisions, persistent downloads, runtime readiness changes, incremental translation, OCR worker geometry, background crop staging, cancellation and window destruction. `scripts/verify-model-replacement.py --model PATH` checks real staged inference, rejected broken replacements, version selection and recoverable removal using isolated copies of an existing Argos package. See [technical repair results](../technical-repairs-2026-10-06.md).

The tested Windows x64/Python 3.10 dependency snapshot is in `constraints/windows-python310.txt`. To recreate those installed runtime/dev versions, use `python -m pip install -c constraints/windows-python310.txt -e ".[dev,language-packs]"` in a Python 3.10 environment. This snapshot is not a cross-platform lockfile; the usual setup remains available for other supported Python versions.

OCR colour tests cover screenshot pixel formats, padded image rows, grayscale, buffer ownership, and the installed RapidOCR image loader on normal/native scans and retries.

The opt-in `scripts/verify-voices.py --all` checks every pinned voice with real normal/slower synthesis using ignored development assets (about 1.8 GB for the full catalogue). `scripts/verify-offline.py --models PATH` uses isolated copies of existing Argos packages to check direct/pivot preparation, fresh-process OCR/translation and the actual Qt review/retry/search workflow. Neither installs test models into the user's app directories. `scripts/preview-ui.py` renders synthetic offscreen settings/review examples without capturing the desktop. See [audit follow-up](../audit-followup.md) for exact results and limitations.

See [third-party speech notices](../../THIRD_PARTY_SPEECH.md) for runtime and voice provenance. Voice files are downloaded on demand and are not committed to this repository.

## Pronunciation research prototype

The separate [stage-one pronunciation prototype](../../prototypes/pronunciation/README.md)
tests offline sentence audio, generated IPA, and word audio using the same voice.
It includes a reproducible English/Portuguese corpus and a local listening report.
Its tested source-alignment approach is now integrated into the app for optional
IPA and word pronunciation, alongside sentence playback. The prototype remains
an independent research baseline; its environment, voices, and generated audio
live under the ignored `artifacts/` directory.

## Why this stack

- RapidOCR runs ONNX models locally and supports multilingual recognition, including a Latin-script model suitable for Portuguese, Dutch, English, French, German, Spanish, and related languages.
- Argos Translate is an open-source offline translation library. Prepared models run in a supervised local worker; there is no cloud API quota or service refusal during a session. Its n-best hypotheses are suggestions, not dictionary senses or contextual probabilities.
- PySide6 provides the full-screen selector, frozen review view, system tray, and word-hover interface in one Windows desktop application.

