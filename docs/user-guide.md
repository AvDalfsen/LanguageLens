# User guide

[Documentation](README.md) · [First capture](getting-started.md) · [Troubleshooting](troubleshooting.md)

## Explore the selection

Lens keeps the frozen desktop visible while recognizing the region you selected. Hover over outlined words to see the best translation suggestion. Click a word to pin its popup so you can use its controls. Click another word to switch, or choose **Unpin**, click outside, or use × to dismiss the popup. Escape closes the entire screenshot. On short screens the selected region gets its own space above the controls. Word details can temporarily replace the controls when both cannot fit; dismiss the word to return to the translation.

The sentence translation supplies context. Word candidates are translated **in isolation** and can choose the wrong meaning. They are model suggestions, not a complete dictionary or confidence percentages.

Use **Show other candidates** to reveal the initial alternatives. **Search for more candidates** requests a wider local search from 12 model guesses. It can change the best match and ranking; it does not find every possible meaning. Results are reused while the current screenshot stays open.

## Inspect, copy, and retry

| Control | Use |
| --- | --- |
| Recognized text | Inspect the original OCR result when a translation looks odd |
| Copy source text | Copy the recognized selection |
| Copy translation | Copy the translation without a heading |
| Edit recognized text | Correct OCR text and translate/read the corrected passage |
| Retry OCR | Appears with a recognition error; scan the same frozen region again |
| Select another area | Choose another region in the same frozen screenshot |
| Retry translation | Appears with a translation error; restart translation using the recognized or edited text |
| Hide translation / Show translation | Collapse or restore the sentence while keeping controls available |
| Read selection | Speak the original selection when a voice is ready |
| Close and return | Close the screenshot and return to the previous app |

Use **More options** for another-area selection and hiding/restoring the translation. A technical recognition or translation failure shows an inline error with its own retry button and diagnostics access. Retry buttons are hidden during normal use. If recognition finds no text, select another area. Recognized text, translations, and pronunciation notation support keyboard selection/copying; right-click for **Copy selection** or **Copy all**. Expanding **Recognized text** also exposes a keyboard-accessible list of words and **Edit recognized text**. Applying corrections clears the original word highlights because their positions no longer reliably match the edited text. Long text and candidate lists scroll. Drag the review panel's background to reposition it; placement lasts for that screenshot.

## Keyboard reference

| Key | Action |
| --- | --- |
| F8 by default | Capture from another application after Start listening |
| Escape | Close the selector/review and return |
| Left / right | Browse and pin words in visual reading order; focused text fields keep their text-selection keys |
| Tab / Shift+Tab | Move between controls |
| Arrow keys on the speed slider | Adjust pronunciation speed |

To change the global shortcut, choose **Pause listening**, click **Capture hotkey**, and press your preferred combination. Leaving the recorder without a new shortcut preserves the previous value. Valid changes are remembered immediately; choose **Start listening** to activate them.

The recorder accepts one supported key with optional Ctrl/Alt/Shift: letters, digits, F1–F24 except F12, and supported navigation/control keys. Windows-reserved combinations, punctuation, mouse buttons, and multi-step sequences are excluded. Prefer a function key or modifiers to avoid interrupting typing. See Settings' shortcut tooltip for details.

## Multiple monitors

**All monitors** freezes the whole desktop. **Monitor under the pointer** uses the screen your pointer occupies when capture starts, leaving other screens uncovered. OCR reads only the selected crop in either mode.

Native pixel resolution is retained on mixed-DPI monitors, including screens left of or above the primary display. A selection spanning screens is read in visual order. Empty gaps are not OCR input, and words split across a monitor boundary may not be reconstructed.

## Listening and local files

Start listening enables the shortcut and hides Settings. Pause listening disables it without quitting the app. Settings, capture, review, and file maintenance temporarily suspend global registration so Lens does not intercept its own controls.

Capture is unavailable during file/voice maintenance or until required files are verified. Changing the language pair or replacing models requires a fresh check and then Start listening again.

**Performance** contains the option to keep translation models loaded between captures. **Manage local files** contains optional checks, selected-file sizes, backup locations, and translation-model replacement/removal. Japanese and Chinese word lookup toggles appear beside **Text language** only for their matching source language. Their tooltips explain the features and required downloads. Disabling them keeps downloaded files. **Enable read aloud** and **Show pronunciation notation (IPA)** control audio and notation independently for every text language, including Japanese. **Technical details** explains the route and capability state. Translation removal keeps recoverable backups and may affect pairs sharing a model; it does not reclaim their disk space.
