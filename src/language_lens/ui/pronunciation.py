from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from language_lens.config import Settings
from language_lens.services.speech import SpeechJob, SpeechPlayer
from language_lens.services.voices import runtime_ready, selected_voice, voice_present, voices_for


class PronunciationSettings(QFrame):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.preferences = dict(settings.speech_voices)
        self.language = settings.source_language
        self.player = SpeechPlayer(self)
        self.download = SpeechJob(self)
        self.enabled = QCheckBox("Read selected text aloud")
        self.enabled.setChecked(settings.speech_enabled)
        self.show_ipa = QCheckBox("Show IPA in word popups")
        self.show_ipa.setChecked(settings.show_ipa)
        self.show_ipa.setToolTip(
            "Show estimated International Phonetic Alphabet transcriptions for the selected accent. "
            "Useful if you read IPA; works without downloading an audio voice."
        )
        self.voices = QComboBox()
        self.voices.setAccessibleName("Pronunciation voice")
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.install = QPushButton("Download voice")
        self.preview = QPushButton("Hear sample")
        self.details = QLabel()
        self.details.setOpenExternalLinks(True)
        self.details.setWordWrap(True)
        self.details.setObjectName("note")
        note = QLabel("Pronunciation uses the text language above. Voices work offline after a one-time download.")
        note.setWordWrap(True)
        note.setObjectName("note")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.addWidget(self.enabled)
        layout.addWidget(self.show_ipa)
        layout.addWidget(note)
        layout.addWidget(self.voices)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
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
        self.download.succeeded.connect(lambda _path: self.refresh())
        self.download.cancelled.connect(self.refresh)
        self.download.failed.connect(self._download_failed)
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
        self.voices.setEnabled((enabled or self.show_ipa.isChecked()) and voice is not None)
        self.progress.setVisible(self.download.active)
        self.install.setEnabled(enabled and voice is not None)
        ready = voice is not None and voice_present(voice)
        self.preview.setEnabled(enabled and ready and runtime_ready() and not self.download.active)
        self.preview.setText("Hear sample")
        self.install.setText("Cancel download" if self.download.active else
                             "Download / repair voice" if ready else "Download voice · 63 MB")
        if not enabled and not self.show_ipa.isChecked():
            message = "Pronunciation is turned off."
        elif voice is None:
            message = "No voice is available for this language yet. English and both Portuguese variants are supported."
        elif not runtime_ready():
            message = "Restart with Start Language Lens.bat to install the speech components."
        elif not enabled:
            message = "IPA uses this accent. Audio is turned off."
        elif self.download.active:
            message = "Downloading and verifying the voice…"
        elif ready:
            message = "Voice installed. Hear a sample, or read your next selection aloud."
        else:
            message = "Download this voice once to enable pronunciation."
        self.status.setText(message)
        self.details.setText(
            f'<a style="color:#5eead4" href="{voice.url("MODEL_CARD", view=True)}">Voice details and licence</a>'
            if voice else ""
        )
        if self.player.busy:
            self.preview.setText("Stop sample")
            self.install.setEnabled(False)

    def _install(self) -> None:
        if self.download.active:
            self.download.cancel()
            self.install.setEnabled(False)
            self.status.setText("Cancelling download…")
            return
        if self.voice is None:
            return
        self.player.stop()
        self.progress.setValue(0)
        self.download.start("download", self.voice)
        if self.download.active:
            self.refresh()

    def _download_progress(self, done: int, total: int) -> None:
        percent = min(100, done * 100 // max(1, total))
        self.progress.setValue(percent)
        self.status.setText(f"Downloading voice: {percent}% · {done / 1_000_000:.1f} / {total / 1_000_000:.1f} MB")

    def _download_failed(self, message: str) -> None:
        self.refresh()
        self.status.setText(f"Voice download failed: {message}")

    def _preview(self) -> None:
        if self.player.busy:
            self.player.stop()
        elif self.voice is not None:
            self.player.speak(self.voice.sample, self.voice)

    def _playback_changed(self, state: str, message: str) -> None:
        self.refresh()
        if message:
            self.status.setText(message if state != "playing" else "Playing voice sample…")
        self.preview.setEnabled(self.preview.isEnabled() and state != "stopping")

    def shutdown(self) -> None:
        self.player.shutdown()
        self.download.shutdown()
