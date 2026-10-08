# Troubleshooting

[Documentation](README.md) · [Getting started](getting-started.md)

| Problem | What to try |
| --- | --- |
| Capture buttons are disabled | Choose the language pair, then Download required files and wait for Ready to capture. An installed translation model alone is insufficient. Finish/cancel file or voice maintenance first. |
| Installed files appear unverified | Open Manage local files → Check required files. If inspection failed, use Retry file check; an unknown state does not mean files are missing. |
| F8 does nothing | Choose Start listening, then switch to another app. Settings/review temporarily suspend the shortcut. If Windows reports a conflict, Pause listening and choose a different combination. |
| The capture is black | Switch the application to borderless-windowed mode. Exclusive fullscreen and protected video can prevent capture. |
| The game kept running | Pause it manually before capture. The screenshot is frozen; the underlying app is not paused. |
| Recognition missed a word | Select a tighter, clearer region, then Retry OCR. Very small, decorative, curved, or vertical text can remain difficult. |
| The translation looks wrong | Open Recognized text to check OCR first. Use the whole sentence for context, other candidates, or Search for more candidates. Isolated-word suggestions can be ambiguous. |
| Translation fails or stalls | Use Retry translation. If failures continue, Check required files; Reinstall translation model is a later recovery option. Sentence failure does not necessarily prevent word lookup. |
| No route exists for my pair | Inspect Technical details. Some pairs need two models through English; not every possible direction has available models. Try another target language. |
| Audio is unavailable | Enable reading aloud and download a voice for Text language. Japanese also needs its pronunciation pack. Try Hear sample and check the selected audio output. |
| The app is still running after closing Settings | This is the tray behavior. Reopen Settings there, or choose Quit to exit. |
| The portable app is missing runtime files | Quit and extract a fresh complete ZIP. Do not move only LanguageLens.exe or mix files from different releases. |

## Downloads and recovery

Downloads show stages, transferred bytes, speed, and waiting feedback. 100% transferred is followed by validation/installing; wait for readiness. Cancel and retry if needed. Completed cached files can be reused.

**Reinstall translation model** validates replacements before switching and preserves old models as backups. **Remove translation** moves packages to recoverable backups, including shared pivot models after confirmation. It does not erase backups or immediately reclaim their space. Other pairs can depend on the same pivot models.

## Report a problem

Use [GitHub Issues](https://github.com/AvDalfsen/LanguageLens/issues/new/choose). Include:

- App version and whether you use the portable or source build.
- Windows version, language pair, and relevant display scaling/monitor setup.
- Steps, expected behavior, and what happened.
- Sanitized diagnostic files if useful.

**Open diagnostics folder** appears with relevant errors, and the next build also includes it in Help/About. Logs live in %LOCALAPPDATA%/LanguageLens/logs and omit captured text and images.

Do not attach temporary jobs folders: a crash can leave image crops containing private content. Sharing a screenshot is optional; use a non-sensitive reproduction if possible. See [privacy](privacy.md).
