<p align="center"><img src="docs/assets/language-lens.svg" width="72" alt=""></p>

# Language Lens

**Learn from the text already on your screen.** Select text in a frozen screenshot, explore word translations alongside the full sentence, and hear the original language—all processed on your computer.

[**Download for Windows**](https://github.com/AvDalfsen/LanguageLens/releases) · [Getting started](docs/getting-started.md) · [Languages](docs/languages.md) · [Get help](docs/troubleshooting.md)

Windows x64 · Portable preview · Offline after setup

![Language Lens showing Portuguese text, its English translation, and a pinned word popup](docs/assets/review.png)

*Illustrated example using sample text and supplied translations in the actual app interface. [Watch the short workflow demo](docs/assets/workflow.gif).*

## What you can do

- **Explore individual words.** Hover for a translation, click to pin the popup, and use the arrow keys to move between words.
- **Keep the sentence in view.** Read the whole-selection translation alongside word suggestions for context.
- **Hear the original language.** Download an optional voice for word and sentence playback, with adjustable speed and optional pronunciation notation.
- **Work locally.** Screen images, recognized text, translation, and speech stay on your computer. No cloud API key or paid translation service is needed.

Use it for game dialogue, subtitles, or text in desktop apps where selecting and copying words is inconvenient. This is an on-demand frozen review: the underlying application keeps running.

## Download and make your first capture

1. Open [Releases](https://github.com/AvDalfsen/LanguageLens/releases) and download the **LanguageLens-…-windows-x64-preview.zip** asset. The “Source code” downloads are for developers.
2. Extract the complete ZIP, then open **LanguageLens.exe** inside the extracted folder. Keep the supporting files beside it. Python, Git, and administrator access are not required.
3. Choose **Text language** and **Translate into**, then click **Download required files**. This prepares and verifies the files for that language pair. An internet connection is needed for setup.
4. When Settings says **Ready to capture**, click **Try a capture now**, or **Start listening** to enable the capture hotkey.
5. From another app, press **F8** and drag around the text. Hover over words or click to pin them; the sentence translation appears below.
6. Press **Escape** to close the screenshot and return to the previous app.

Pause a game manually before capturing if needed. Closing Settings leaves Lens running in the tray; choose **Quit** there to exit.

For voices, shortcuts, updates, or uninstalling, follow the [getting-started guide](docs/getting-started.md). Source setup and tests are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Languages and compatibility

The app offers 25 text-language choices, including English, Dutch, French, German, Spanish, Portuguese (Portugal/Brazil), Japanese, Chinese, Korean, Arabic, and Hindi. See the [complete language list and capability notes](docs/languages.md).

Translation models are directional. Some pairs use two local models through English; availability and quality vary by pair. Japanese/Chinese word dictionaries and Japanese pronunciation use additional packs. Settings checks what your chosen pair needs.

The current distribution targets **Windows x64**. Windows 10 22H2 has been exercised during development; Windows 11 is the intended primary target, with clean-machine validation still pending. Native ARM64, Windows 7/8/Vista, macOS, and Linux are not supported by this build. The portable preview is unsigned.

## Things to know

- **Capture works best in ordinary desktop and borderless-windowed apps.** Exclusive fullscreen or protected video can produce a black image.
- **Recognition and translation can be wrong.** Small or decorative text needs a careful selection. A word translated alone can have the wrong meaning; use the sentence for context.
- **Pronunciation is a learning aid.** Voices and phonetic notation are estimates, with different support across languages.
- **Downloads are separate from the app.** Language files and optional voices take additional space. Once prepared, capture, translation, and speech work offline.

[Common problems and fixes](docs/troubleshooting.md) · [Privacy and local files](docs/privacy.md)

## Documentation and contributions

Start with the [documentation index](docs/README.md) for the user guide, pronunciation, language support, and developer references.

[Report a problem](https://github.com/AvDalfsen/LanguageLens/issues/new/choose) with your app version, Windows version, language pair, and steps to reproduce. Documentation improvements and language testing are welcome; see [contributing](CONTRIBUTING.md).

## Licence and credits

Application code is [MIT licensed](LICENSE). Third-party runtimes and downloaded models have their own terms; see [speech and voice notices](THIRD_PARTY_SPEECH.md), and check **Voice details and licence** before using a voice.

Built with [RapidOCR](https://github.com/RapidAI/RapidOCR), [Argos Translate](https://github.com/argosopentech/argos-translate), [Piper](https://github.com/OHF-Voice/piper1-gpl), and PySide6.
