# Language Lens

Language Lens is a Windows-first, local screen translator for language learning. Press a global hotkey from any application, drag around text in a frozen screenshot, and inspect it without sending the image anywhere. OCR outlines the words; hovering over one shows its translation, while a contextual translation of the whole selection stays visible below.

Screenshots and recognized text remain on the computer. The app uses [RapidOCR](https://github.com/RapidAI/RapidOCR) for OCR and [Argos Translate](https://github.com/argosopentech/argos-translate) for translation. Both need one-time model downloads, but neither needs a cloud API during play.

## Current workflow

1. Open the app and choose the language shown on screen and the language you know.
2. Download the local Argos language model once.
3. Select a global capture hotkey and start listening.
4. From any application, press the hotkey and drag around text in the frozen full-screen frame.
5. The full frame remains visible. Hover over OCR words inside the selected region for individual translations; read the whole-selection translation below.
6. Press Escape to close the lens and focus the previously active application.

The optional Escape helper captures first, then sends Escape to the active application. On exit it focuses that application and sends Escape again. Capturing first keeps any menu opened by Escape out of the frozen image.

## Recommended launcher

Double-click `Start Language Lens.bat` in the project folder. It checks whether the local Python environment and required packages are healthy, runs first-time setup or repair only when necessary, and then starts the app through the hidden launcher. The command window closes once the app starts.

Translation-language models remain managed by the button inside the app and are not downloaded again unnecessarily.

## Run the individual scripts

Python 3.10–3.12 and Windows 10/11 are supported.

```powershell
cd "C:\Users\Fillask\Desktop\GitHub repos\LanguageLens"
.\scripts\setup.ps1
.\scripts\run.ps1
```

`run.ps1` launches with `pythonw.exe` and exits immediately, so it does not leave a PowerShell window open.

The first setup is large because the local OCR and translation runtimes include neural-network dependencies. The first capture in a new writing system may download its RapidOCR recognition model. The app's **Download local translation model** button downloads the chosen Argos model; uncommon pairs are automatically routed through English when both legs are available.

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

## Why this stack

- RapidOCR runs ONNX models locally and supports multilingual recognition, including a Latin-script model suitable for Portuguese, Dutch, English, French, German, Spanish, and related languages.
- Argos Translate is an open-source offline translation library. The model is downloaded once and then invoked in-process; there is no API quota or service refusal during a session.
- PySide6 provides the full-screen selector, frozen review view, system tray, and word-hover interface in one Windows desktop application.

