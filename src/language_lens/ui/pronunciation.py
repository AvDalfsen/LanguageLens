from __future__ import annotations

from language_lens.i18n import tr, tr_message, language
import html
from time import monotonic

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from language_lens.config import Settings
from language_lens.services.speech import SpeechJob, SpeechPlayer
from language_lens.services.voices import runtime_ready, voice_runtime_ready, selected_voice, voice_present, voices_for
from language_lens.runtime import recovery_instruction
from language_lens.ui.style import set_help
from language_lens.ui.progress import TransferMetrics
from language_lens.services import language_packs as packs


class PronunciationSettings(QFrame):
    preferences_changed = Signal()
    activity_changed = Signal()

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.preferences = dict(settings.speech_voices)
        self.language = settings.source_language
        self.player = SpeechPlayer(self)
        self.player.speed = settings.speech_speed
        self.speech_speed = settings.speech_speed
        self._maintenance_blocked = False
        self.download = SpeechJob(self)
        self._download_phase = "downloading"
        self._transfer_metrics = TransferMetrics(monotonic())
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(self._update_download_metrics)
        self.enabled = QCheckBox(tr("Enable read aloud"))
        self.enabled.setChecked(settings.speech_enabled)
        set_help(self.enabled,
            "Enable buttons to read the original selected text and individual words aloud, not "
            "their translations. Audio uses 'Text language' and the selected accent. It never "
            "plays automatically when you hover. Download a matching voice once for offline "
            "playback; disabling audio does not disable translation or the optional IPA display."
        )
        self.show_ipa = QCheckBox(tr("Show pronunciation notation (IPA)"))
        self.show_ipa.setChecked(settings.show_ipa)
        set_help(self.show_ipa,
            "Show estimated International Phonetic Alphabet transcriptions for the selected accent. "
            "IPA helps identify individual sounds if you know the notation. It is optional and "
            "works without downloading the audio voice. The app tries to use the selected sentence "
            "as context and labels isolated-word fallbacks. Estimates, names, and ambiguous words "
            "can be wrong; IPA is not a measurement of the synthesized audio. English and Portuguese "
            "have audited display conventions. Other languages retain clearly labelled engine notation; "
            "Japanese word readings are isolated and do not claim sentence-context pitch accent."
        )
        self.voices = QComboBox()
        self.voices.setAccessibleName(tr("Pronunciation voice"))
        set_help(self.voices,
            "Choose the accent and voice for the source text, independently of the translation "
            "language. This choice also sets the accent used by estimated IPA. The app remembers "
            "your choice for each text language. Every offered text language has a local voice. "
            "English offers US and UK accents; Portuguese uses Portugal or Brazil according to "
            "'Text language'. Availability does not guarantee native-speaker pronunciation quality."
        )
        self.ipa_accent_note = QLabel(tr("IPA uses this accent."))
        self.ipa_accent_note.setObjectName("note")
        self.ipa_accent_note.setWordWrap(True)
        self.status = QLabel()
        self.status.setAccessibleName(tr("Voice and audio status"))
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.progress.setAccessibleName(tr("Voice download progress"))
        self.download_details = QLabel()
        self.download_details.setObjectName("note")
        self.download_details.setWordWrap(True)
        self.download_details.setTextFormat(Qt.TextFormat.PlainText)
        self.download_details.hide()
        self.install = QPushButton(tr("Download voice"))
        self.preview = QPushButton(tr("Hear sample"))
        set_help(self.install,
            "Download the selected voice for local playback. The button shows its actual download size. Once installed, "
            "this button becomes 'Check voice files': an optional integrity check, not a warning that the voice is broken. "
            "Only missing or damaged files are downloaded. While downloading, this button becomes 'Cancel download'. "
            "Completed verified files are kept "
            "if you cancel, so retrying does not start everything from scratch."
        )
        set_help(self.preview,
            "Listen to a short original-language sample to judge the selected voice and accent. "
            "A downloaded voice and the speech runtime are required. During playback the button "
            "becomes 'Stop sample'. Samples are generated locally; no text is sent to a speech service."
        )
        self.details = QLabel()
        self.details.setOpenExternalLinks(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.details.setAccessibleName(tr("Voice details and licence"))
        self.details.setWordWrap(True)
        self.details.setObjectName("note")
        set_help(self.details,
            "Open the upstream voice's model card in your browser to read about its speaker, "
            "training data, and licence. This external page is not needed for local playback; "
            "opening it does not upload captured text or screenshots."
        )
        note = QLabel(tr("Pronunciation uses 'Text language' above. Audio is generated locally after a one-time voice download."))
        note.setWordWrap(True)
        note.setObjectName("note")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.addWidget(self.enabled)
        layout.addWidget(self.show_ipa)
        layout.addWidget(note)
        layout.addWidget(self.voices)
        layout.addWidget(self.ipa_accent_note)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addWidget(self.download_details)
        row = QHBoxLayout()
        row.addWidget(self.install)
        row.addWidget(self.preview)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self.details)

        self.voices.currentIndexChanged.connect(self._voice_changed)
        self.enabled.toggled.connect(self._enabled_changed)
        self.show_ipa.toggled.connect(self.refresh)
        self.install.clicked.connect(self._install)
        self.preview.clicked.connect(self._preview)
        self.player.changed.connect(self._playback_changed)
        self.download.progress.connect(self._download_progress)
        self.download.stage_changed.connect(self._download_stage_changed)
        self.download.succeeded.connect(lambda _path: self.refresh())
        self.download.cancelled.connect(self.refresh)
        self.download.failed.connect(self._download_failed)
        self.download.activity_changed.connect(self._download_activity_changed)
        self.enabled.toggled.connect(self.preferences_changed)
        self.show_ipa.toggled.connect(self.preferences_changed)
        self.voices.currentIndexChanged.connect(self.preferences_changed)
        self.set_language(self.language)

    @property
    def voice(self):
        return selected_voice(self.language, self.preferences)

    def set_language(self, language: str) -> None:
        self.player.stop()
        if self.download.active:
            self.download.cancel()
        self.language = language
        self.voices.blockSignals(True)
        self.voices.clear()
        for voice in voices_for(language):
            self.voices.addItem(voice.name, voice.id)
        if self.voice:
            self.voices.setCurrentIndex(self.voices.findData(self.voice.id))
        self.voices.blockSignals(False)
        self.refresh()

    def _voice_changed(self) -> None:
        self.player.stop()
        if self.download.active:
            self.download.cancel()
        if self.voices.currentData():
            self.preferences[self.language] = self.voices.currentData()
        self.refresh()

    def _enabled_changed(self) -> None:
        self.player.stop()
        if self.download.active:
            self.download.cancel()
        self.refresh()

    def refresh(self) -> None:
        voice = self.voice
        enabled = self.enabled.isChecked()
        self.ipa_accent_note.setVisible(self.show_ipa.isChecked())
        self.voices.setEnabled((enabled or self.show_ipa.isChecked()) and voice is not None and not self._maintenance_blocked)
        self.progress.setVisible(self.download.active)
        self.download_details.setVisible(self.download.active)
        japanese = voice is not None and voice.phoneme_type == "japanese"
        pronunciation_only = not enabled and self.show_ipa.isChecked() and japanese
        pack_missing = japanese and not packs.ready("ja-speech")
        self.install.setEnabled(self.download.active or ((enabled or pronunciation_only) and voice is not None and not self._maintenance_blocked))
        ready = voice is not None and voice_present(voice)
        self.preview.setEnabled(enabled and ready and runtime_ready() and voice_runtime_ready(voice)
                                and not self.download.active and not self._maintenance_blocked)
        self.preview.setText(tr("Hear sample"))
        size = (voice.total_bytes if voice and not ready and not pronunciation_only else 0)
        size += packs.download_bytes("ja-speech") if pack_missing else 0
        if self.download.active:
            action = tr("Cancel download")
        elif pronunciation_only:
            action = f"{tr('Download pronunciation')} · {size / 1_000_000:.0f} MB" if pack_missing else tr("Check pronunciation files")
        elif ready and not pack_missing:
            action = tr("Check voice files")
        else:
            action = f"{tr('Download voice')} · {size / 1_000_000:.0f} MB" if voice else tr("No voice available")
        self.install.setText(action)
        if not enabled and not self.show_ipa.isChecked():
            message = tr("Pronunciation is turned off.")
        elif voice is None:
            message = tr("No voice is available for this language.")
        elif pack_missing:
            message = tr("Download the Japanese pronunciation pack to enable speech and phonetic notation. The audio voice is a separate file.")
        elif not runtime_ready() or not voice_runtime_ready(voice):
            message = tr("Speech components could not be loaded. ") + recovery_instruction()
        elif not enabled:
            message = tr("Audio is turned off.")
        elif self.download.active:
            message = tr("Checking voice files and downloading any missing files…")
        elif ready:
            message = tr("Voice installed. Use 'Hear sample' to preview it, or read your next selection aloud.")
        else:
            message = tr("Download this voice once to enable pronunciation.")
        self.status.setText(tr(message))
        if self.download.active:
            self._update_download_metrics()
        self.details.setText(
            f'<a style="color:#5eead4" href="{voice.url("MODEL_CARD", view=True)}">{tr("Voice details and licence")}</a>'
            f' · {html.escape(voice.license_note)}'
            if voice else ""
        )
        if self.player.busy:
            self.preview.setText(tr("Stop sample"))
            self.install.setEnabled(False)

    def _install(self) -> None:
        if self.download.active:
            self.install.setEnabled(False)
            self._download_phase = "cancelling"
            self._progress_timer.stop()
            self.status.setText(tr("Cancelling download…"))
            # Cancellation may finish synchronously; let its final refresh win.
            self.download.cancel()
            return
        if self.voice is None or self._maintenance_blocked:
            return
        self.player.stop()
        self._download_stage_changed("checking")
        self.download.start("download" if self.enabled.isChecked() else "download-pronunciation", self.voice)
        if self.download.active:
            self.refresh()

    def set_speech_speed(self, speed: float) -> None:
        self.player.stop()
        self.speech_speed = self.player.speed = speed

    def _download_progress(self, done: int, total: int) -> None:
        if self._download_phase == "downloading":
            self._transfer_metrics.update(done, total, monotonic())
            self.progress.setRange(0, 1000 if total else 0)
            self.progress.setValue(min(1000, done * 1000 // total) if total else 0)
        self._update_download_metrics()

    def _download_stage_changed(self, phase: str) -> None:
        self._download_phase = phase
        self._transfer_metrics.reset(monotonic())
        self.progress.setRange(0, 0)
        self._update_download_metrics()

    def _update_download_metrics(self) -> None:
        labels = {"checking": tr("Checking voice files…"), "downloading": tr("Downloading voice…"),
                  "verifying": tr("Verifying voice files…"), "cancelling": tr("Cancelling download…")}
        self.status.setText(tr(labels[self._download_phase]))
        details = self._transfer_metrics.text(monotonic())
        self.download_details.setText(details)

    def _download_activity_changed(self, active: bool) -> None:
        if active:
            self._progress_timer.start()
        else:
            self._progress_timer.stop()
            self.progress.hide()
            self.download_details.hide()
        self.activity_changed.emit()

    def _download_failed(self, message: str) -> None:
        self.refresh()
        self.status.setText(tr("Voice download failed: {error}", error=message))

    def _preview(self) -> None:
        if self.player.busy:
            self.player.stop()
        elif self.voice is not None and not self._maintenance_blocked:
            self.player.speak(self.voice.sample, self.voice)

    def set_maintenance_blocked(self, blocked: bool) -> None:
        if self._maintenance_blocked != blocked:
            self._maintenance_blocked = blocked
            self.refresh()

    def _playback_changed(self, state: str, message: str) -> None:
        self.refresh()
        if message:
            self.status.setText(tr_message(message) if state != "playing" else tr("Playing voice sample…"))
        self.preview.setEnabled(self.preview.isEnabled() and state != "stopping")

    def shutdown(self) -> None:
        self._progress_timer.stop()
        self.player.shutdown()
        self.download.shutdown()
