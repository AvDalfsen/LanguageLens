# Language Lens presentation audit

8 October 2026 · Reviewed at source commit f9dedc1

Language Lens communicates the care taken to build it more clearly than it communicates why someone should use it. Its strongest promise is straightforward: inspect unfamiliar on-screen text, translate words alongside the full sentence, and hear the original language, locally. The repository makes that experience unnecessarily difficult to discover and start.

The first priority is to organize the material around a new user's decisions: understand the tool, see it working, check compatibility, download it, and complete one capture. Most existing detail should remain available in supporting documentation.

**Scope and evidence**

Reviewed the README, tracked files, UI source, language catalogue, portable instructions, release-building documentation, and release workflow. Regenerated the existing synthetic previews with scripts/preview-ui.py and inspected Settings with ready/missing files, a small Settings window, and the review overlay. Public metadata and releases were checked through the GitHub API.

This is a presentation and onboarding review. The preview uses mocked states and synthetic text; it does not establish real capture quality, translation accuracy, latency, or clean-machine installation success. No application features or public repository settings were changed.

The README contains approximately 4,300 whitespace-separated words across 183 lines. Almost 2,900 words appear before “Recommended launcher” at line 100. No screenshots, GIFs, logo files, or product icons are tracked. Ignored preview images are development assets, not public documentation.

**Relevant established projects**

These projects were selected for relevant desktop workflows and substantial community interest, using visible GitHub stars as a rough signal. Stars do not measure onboarding quality or establish that a README caused adoption. Counts are rounded observations from the pages inspected on the audit date.

| Project | Visible interest | Useful pattern | Application to Language Lens |
| --- | --- | --- | --- |
| [NormCap](https://github.com/dynobo/normcap) | About 2.7k stars | Short purpose statement, screencast, documentation/FAQ/release links, and Windows installer/portable downloads before Python setup. | Demonstrate the interaction and put the portable download ahead of source installation. |
| [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR/blob/main/README_en.md) | About 47.7k stars on its repository | Product identity, benefits, screenshots, downloads, extraction instructions, and separate developer/API documentation. | Explain the local workflow visually and distinguish using the app from building it. |
| [CopyQ](https://github.com/hluk/CopyQ) | About 12.4k stars | Early download/documentation/bug-report links, clear overview, OS-specific installation, basic use, and deeper references. | Make help and the first successful use discoverable without implementation detail. |
| [PowerToys](https://github.com/microsoft/PowerToys) | About 139k stars | Visual identity, short promise, prominent installation/documentation links, illustrated utilities, and separate release notes. | Use a compact feature overview and visible routes to download and help. |
| [CopyTranslator](https://github.com/CopyTranslator/CopyTranslator) | About 18.1k stars | Recognizable copy-to-translate workflow and separate manual/install pages, but also lengthy promotion and repeated prose. | Keep the concrete workflow and guides. Popularity does not make every presentation choice worth copying. |

My inference: useful entry points and visual proof matter more here than a particular README length, badge count, or decorative style.

**Prioritized findings**

High means a direct obstacle to understanding or trying the application. Medium reduces clarity or confidence after that decision. Later indicates polish with less immediate value.

| Priority | Evidence | Effect on a newcomer | Recommended change |
| --- | --- | --- | --- |
| High | README lines 3–8 describe release tooling, ONNX splitting, omitted dependencies, and optional packs. The product explanation starts at line 10. | The first impression is an engineering preview. | Lead with the benefit, platform, demo, and download. Move packaging architecture to developer documentation. |
| High | [v0.1.2 is publicly downloadable](https://github.com/AvDalfsen/LanguageLens/releases/tag/v0.1.2), with a Windows x64 ZIP and checksum. The README never links to Releases or explains opening LanguageLens.exe; it recommends the source batch launcher at line 100. | Users can conclude they need Python, Git, or a build process. | Give one recommended portable path: download the ZIP, extract the complete folder, open LanguageLens.exe. Separate source setup. |
| High | No embedded visual appears in the README; no product screenshots or demos are tracked. | Hover translation, pinning, sentence context, and pronunciation must be imagined. | Add a representative capture image and short demo near the top, plus one setup image in the guide. |
| High | “Current workflow” begins with seven steps, then continues through long paragraphs about shortcuts, monitor geometry, sizing, errors, OCR arrays, and candidate algorithms. | Normal actions and exceptional behavior have the same apparent importance. | Keep a short first-capture sequence. Move reference, recovery, advanced use, and implementation detail into named pages. |
| High | Public [repository metadata](https://api.github.com/repos/AvDalfsen/LanguageLens) has no description, homepage, or topics. | Search results and the sidebar do little to explain or expose the project. | Add a concise description and relevant topics. Add a homepage when a useful documentation entry page exists. |
| Medium | Portable and source paths are mixed. README line 111 contains the maintainer's absolute checkout path; speech instructions begin with the batch launcher. | Instructions appear machine-specific and do not match the downloadable app. | Write portable-user instructions independently. Use a generic checkout example in a developer guide. |
| Medium | Windows requirements are buried under “Run the individual scripts”; the opening says “Windows-first.” Documentation records limited Windows validation. | The current distribution and tested platforms are unclear. | Put platform/status beside the download. Distinguish intended support from tested systems. |
| Medium | The code offers 25 text-language choices, but the README has no language list or capability overview. | “Will this work for my language?” is difficult to answer. | Add a support page separating OCR, translation routes, voices, and phonetic display. Distinguish selectable languages from verified quality. |
| Medium | Practical limits are dispersed: frozen capture does not pause the app, fullscreen can fail, isolated words can be ambiguous, and IPA support varies. | Readers can form expectations the app does not promise. | Keep a few essential limits beside the quick start and link deeper explanations. |
| Medium | docs/ is dominated by audits, repairs, and historical checkpoints, with no documentation index or task-based user guide. | Development history substitutes for a help route. | Add an index, getting-started, pronunciation, languages, and troubleshooting guides. Group historical reports behind an archive entry. |
| Medium | [v0.1.2 notes](https://github.com/AvDalfsen/LanguageLens/releases/tag/v0.1.2) contain “Minor changes” and a tentative uninstaller fix. The asset says “preview” while the release is not marked as a prerelease. | Installation, user-visible changes, and maturity are unclear. | Add an edited summary, asset to choose, install/update steps, known limits, and checks performed. Express preview/stable status consistently. |
| Medium | No tracked issue templates, contribution guide, or direct support route appear in the README. | Users lack an obvious way to report failures or help. | Link to issues and add a compact bug template requesting version, Windows version, language pair, steps, and sanitized diagnostics. |
| Later | app.py uses Qt's generic computer icon for the tray/window. No product identity asset is tracked. | The running app is less recognizable. | Create one simple icon for the tray, executable, window, README, and repository social preview. |

**What should survive the edit**

- The existing product paragraph describes a distinctive learning workflow. Improve its position before inventing a new pitch.
- Local processing, explicit downloads, no cloud API requirement, and no automatic audio are practical benefits.
- Honest explanations of translation ambiguity, pronunciation estimates, language differences, and compatibility limits should remain at the appropriate depth.
- Optional speech/IPA, pinning, keyboard browsing, and sentence context strengthen the learning use case.
- The UI's consistent dark palette, primary action, readiness feedback, and collapsible maintenance/technical sections provide a reasonable foundation.
- Portable packaging, update/uninstall instructions, checksums, and validation records already exist. Make their user-facing parts easy to reach.

**Recommended README shape**

Aim initially for roughly 600–900 words, excluding a small language table. This is an editorial target, not a rule. The first screen should answer what it does, who it helps, which platform it runs on, and where to try it.

| Order | Content |
| --- | --- |
| 1 | Name, one-sentence promise, Windows x64, release status |
| 2 | Representative screenshot or short demo with a useful caption |
| 3 | Download Windows portable · Getting started · Supported languages · Get help |
| 4 | Four benefits: on-screen word lookup, sentence context, optional pronunciation, local processing |
| 5 | Install and make the first capture |
| 6 | Language support and essential practical limits |
| 7 | Privacy/download summary, licence/notices, documentation and contribution links |

Possible opening:

> Learn from the text already on your screen. Language Lens lets you select text in a frozen screenshot, explore word translations alongside the full sentence, and hear the original language—all processed on your computer.

Possible image caption: “Hover over a word for its translation; keep the full sentence visible for context.” A game dialogue example makes the original use case concrete; an ordinary desktop example in the guide shows broader scope.

First capture: extract and launch; choose languages; download required files once; start listening; press F8 and select text; explore words and press Escape to return. Introduce optional voices after this succeeds. Put the manual-game-pause clarification beside the steps.

**Where the current material should go**

| Material | Destination |
| --- | --- |
| Product promise, local operation, key benefits | README |
| Portable download, launch, first capture | README summary and docs/getting-started.md |
| Hotkeys, pinning, candidates, monitor behavior | docs/user-guide.md |
| Voice setup, speed, IPA meanings and limits | docs/pronunciation.md, linking the existing IPA audit |
| Missing models, conflicts, black captures, retries, diagnostics | docs/troubleshooting.md |
| Languages, routes, OCR/voice/notation differences | docs/languages.md |
| Network behavior, temporary crops, logs, crash leftovers | docs/privacy.md; short README summary |
| Tests, source environment, constraints, worker supervision, OCR buffers | CONTRIBUTING.md and developer/architecture documentation |
| Build recipes and packaged verification | Existing docs/release-building.md |
| Historic audits and implementation checkpoints | Clearly labelled documentation archive; preserve useful links |
| Pronunciation research baseline | Existing prototype README and developer documentation |
| Model/runtime licences | Existing THIRD_PARTY_SPEECH.md and notices, with direct links |

Avoid putting most of the current wall inside collapsed README blocks. Supporting pages give topics clearer names, stable links, and independent maintenance. The proposed guide filenames above are destinations to create, not existing links.

**Interface polish after the repository entry path**

These are design recommendations based on source and synthetic previews, not observed usability-test failures.

1. Shorten labels. “Enable read aloud” can replace “Enable functionality to read selected text aloud”; explain IPA as optional pronunciation notation. Consider “Enable capture hotkey” for “Start listening,” whose wording can require extra explanation.
2. Emphasize the current next step. In the missing-files preview, download is actionable while the visually primary capture button is disabled. Consider emphasizing the required download and placing optional pronunciation after basic capture setup. A multi-page wizard needs evidence that it helps.
3. Improve the review panel's action hierarchy. Retry/reselect/copy/hide controls occupy substantial space and similar visual weight. Make reading/listening easy to scan, group occasional actions, and emphasize retry when something fails. Preserve keyboard access and the fixed close action.
4. Add Help/About with installed version, getting-started/help links, diagnostics, and licence information. The reviewed UI has no such entry; portable users may never revisit GitHub.
5. Use synthetic renders for layout review. Their repeated translation text, pending states, and artificial backgrounds are stress fixtures. Use a representative completed interaction for public presentation.

UI translation is useful if non-English readers are a target audience. [NormCap](https://github.com/dynobo/normcap#contribute-to-ui-translations) and [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR/blob/main/README_en.md#software-localization) provide defined localization contribution routes. Settle English labels and onboarding copy first, then extract strings and add supported interface locales. A translated quick start can accompany that work. Do not imply UI localization already exists because the app translates other languages.

**Suggested order of work**

1. Rewrite the README around the published portable download and first capture. Add a documentation index and move advanced material without losing useful explanations.
2. Add a representative screenshot and short demo. Fill GitHub description/topics and edit release notes.
3. Add troubleshooting, language support, privacy, and contribution routes. Check the complete path with someone who has never used the project.
4. Refine labels and actions, then add Help/About and a consistent icon. Pursue UI localization according to the intended audience.

Suggested repository description: “Offline screen translator for language learning on Windows. Explore words, sentence translations, and pronunciation from a screenshot.”

Suggested topics: language-learning, ocr, screen-translator, offline, windows, translation.

**Completion criteria**

- In 15 seconds, a new visitor can explain the purpose and identify the Windows download.
- Visitors can see word-hover and sentence context without reading the manual.
- The recommended portable path requires neither Python nor Git.
- A language/support page explains pair and feature availability without promising equal quality everywhere.
- A first-time user can complete a capture and find help for black captures, missing files, and shortcut conflicts.
- README, release page, portable instructions, and UI agree on launch steps, status, terminology, and optional downloads.
- Detailed technical evidence remains available to contributors without occupying the introduction.

This audit adds recommendations only. It does not change the README, application, GitHub metadata, or published releases. Runtime work was limited to refreshing ignored synthetic preview images.

