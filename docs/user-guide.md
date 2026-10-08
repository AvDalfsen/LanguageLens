# User guide

[Documentation](README.md) · [First capture](getting-started.md) · [Troubleshooting](troubleshooting.md)

## Explore the selection

Lens keeps the frozen desktop visible while recognizing the region you selected. Hover over outlined words to see the best translation suggestion. Click a word to pin its popup so you can use its controls. Click another word to switch, or click outside/use × to dismiss the popup. Escape closes the entire screenshot.

The sentence translation supplies context. Word candidates are translated **in isolation** and can choose the wrong meaning. They are model suggestions, not a complete dictionary or confidence percentages.

Use **Show other candidates** to reveal the initial alternatives. **Search for more candidates** requests a wider local search from 12 model guesses. It can change the best match and ranking; it does not find every possible meaning. Results are reused while the current screenshot stays open.

## Inspect, copy, and retry

| Control | Use |
| --- | --- |
| Recognized text | Inspect the original OCR result when a translation looks odd |
| Copy source text | Copy the recognized selection |
| Retry OCR | Scan the same selected region again; old text and audio are cleared |
| Select another area | Choose another region in the same frozen screenshot |
| Retry translation | Repeat translation without recapturing |
| Hide translation / Show translation | Collapse or restore the sentence while keeping controls available |
| Read selection | Speak the original selection when a voice is ready |
| Close and return | Close the screenshot and return to the previous app |

Recognized text and the translation support selection/copying; right-click for **Copy selection** or **Copy all**. These views do not alter the OCR outlines. Long text and candidate lists scroll. Drag the review panel's background to reposition it; placement lasts for that screenshot.

## Keyboard reference

| Key | Action |
| --- | --- |
| F8 by default | Capture from another application after Start listening |
| Escape | Close the selector/review and return |
| Left / right | Browse and pin words |
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

**Manage local files** contains optional checks, translation-model replacement/removal, and language pack controls. **Technical details** explains the route and capability state. Translation removal keeps recoverable backups and may affect pairs sharing a model through English; it does not automatically reclaim their disk space.
