from __future__ import annotations

from language_lens.i18n import tr, tr_message, language, voice_name, catalogs, ui_text, ui_widget, runtime_message
import html
from time import monotonic

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSlider, QVBoxLayout,
)
from language_lens.ui.controls import ChoiceBox

from language_lens.config import Settings
from language_lens.services.speech import SpeechJob, SpeechPlayer
from language_lens.services.voices import runtime_ready, voice_runtime_ready, selected_voice, voice_present, voices_for
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
        self._download_error = None
        self.download = SpeechJob(self)
        self._download_phase = "downloading"
        self._transfer_metrics = TransferMetrics(monotonic())
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(self._update_download_metrics)
        self.enabled = ui_widget(QCheckBox, tr("Enable read aloud"))
        self.enabled.setChecked(settings.speech_enabled)
        set_help(self.enabled,
            "Enable buttons to read the original selected text and individual words aloud, not "
            "their translations. Audio uses 'Text language' and the selected accent. It never "
            "plays automatically when you hover. Download a matching voice once for offline "
            "playback; disabling audio does not disable translation or the optional IPA display."
        )
        self.show_ipa = ui_widget(QCheckBox, tr("Show pronunciation notation (IPA)"))
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
        self.voices = ChoiceBox()
        self.voices._lens_untranslated_items = True
        ui_text(self.voices, tr("Pronunciation voice"), property="accessibleName")
        set_help(self.voices,
            "Choose the accent and voice for the source text, independently of the translation "
            "language. This choice also sets the accent used by estimated IPA. The app remembers "
            "your choice for each text language. Every offered text language has a local voice. "
            "English offers US and UK accents; Portuguese uses Portugal or Brazil according to "
            "'Text language'. Availability does not guarantee native-speaker pronunciation quality."
        )
        self.ipa_accent_note = ui_widget(QLabel, tr("IPA uses this accent."))
        self.ipa_accent_note.setObjectName("note")
        self.ipa_accent_note.setWordWrap(True)
        self.status = QLabel()
        ui_text(self.status, tr("Voice and audio status"), property="accessibleName")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        ui_text(self.progress, tr("Voice download progress"), property="accessibleName")
        self.download_details = QLabel()
        self.download_details.setObjectName("note")
        self.download_details.setWordWrap(True)
        self.download_details.setTextFormat(Qt.TextFormat.PlainText)
        self.download_details.hide()
        self.install = ui_widget(QPushButton, tr("Download voice"))
        self.preview = ui_widget(QPushButton, tr("Hear sample"))
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
        ui_text(self.details, tr("Voice details and licence"), property="accessibleName")
        self.details.setWordWrap(True)
        self.details.setObjectName("note")
        set_help(self.details,
            "Open the upstream voice's model card in your browser to read about its speaker, "
            "training data, and licence. This external page is not needed for local playback; "
            "opening it does not upload captured text or screenshots."
        )
        note = ui_widget(QLabel, tr("Pronunciation uses 'Text language' above. Audio is generated locally after a one-time voice download."))
        note.setWordWrap(True)
        note.setObjectName("note")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        heading = ui_widget(QLabel, tr("Pronunciation"))
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        layout.addWidget(self.enabled)
        layout.addWidget(self.show_ipa)
        layout.addWidget(note)
        voice_label = ui_widget(QLabel, tr("Pronunciation voice"))
        voice_label.setBuddy(self.voices)
        layout.addWidget(voice_label)
        layout.addWidget(self.voices)
        layout.addWidget(self.ipa_accent_note)
        self.speed_label = QLabel()
        self.speed_label.setObjectName("note")
        self.speed_label.setWordWrap(True)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        ui_text(self.speed_slider, tr("Pronunciation speed"), property="accessibleName")
        speed_help = catalogs()["english"]["speech_speed_tip"]
        set_help(self.speed_slider, speed_help)
        self.speed_label.setBuddy(self.speed_slider)
        self.speed_slider.setRange(50, 150)
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setValue(round(self.speech_speed * 100))
        self.speed_slider.valueChanged.connect(self._speed_changed)
        speed_row = QHBoxLayout()
        speed_row.addWidget(self.speed_label)
        speed_row.addWidget(self.speed_slider, 1)
        layout.addLayout(speed_row)
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
        self.download.succeeded.connect(lambda _path: self._download_succeeded())
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
        self._download_error = None
        self.voices.blockSignals(True)
        self.voices.clear()
        for voice in voices_for(language):
            self.voices.addItem(voice_name(voice), voice.id)
        if self.voice:
            self.voices.setCurrentIndex(self.voices.findData(self.voice.id))
        self.voices.blockSignals(False)
        self.refresh()

    def _voice_changed(self) -> None:
        self.player.stop()
        self._download_error = None
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
        notation = self.show_ipa.isChecked()
        blocked = self.voices.blockSignals(True)
        for index in range(self.voices.count()):
            selected = next((v for v in voices_for(self.language) if v.id == self.voices.itemData(index)), None)
            if selected:
                self.voices.setItemText(index, voice_name(selected))
        self.voices.blockSignals(blocked)
        ui_text(self.speed_label, f"{tr('Pronunciation speed')}: {self.speech_speed:g}×")
        self.speed_label.setFixedWidth(min(260, self.speed_label.fontMetrics().horizontalAdvance(self.speed_label.text()) + 12))
        self.speed_slider.setEnabled(enabled and not self._maintenance_blocked)
        self.ipa_accent_note.setVisible(notation)
        self.voices.setEnabled((enabled or notation) and voice is not None and not self._maintenance_blocked)
        self.progress.setVisible(self.download.active)
        self.download_details.setVisible(self.download.active)
        japanese = voice is not None and voice.phoneme_type == "japanese"
        pronunciation_only = not enabled and notation and japanese
        pack_missing = japanese and not packs.ready("ja-speech")
        self.install.setEnabled(self.download.active or ((enabled or pronunciation_only) and voice is not None and not self._maintenance_blocked))
        ready = voice is not None and voice_present(voice)
        self.preview.setEnabled(enabled and ready and runtime_ready() and voice_runtime_ready(voice)
                                and not self.download.active and not self._maintenance_blocked)
        ui_text(self.preview, tr("Hear sample"))
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
        ui_text(self.install, action)
        if not enabled and not notation:
            message = tr("Pronunciation is turned off.")
        elif voice is None:
            message = tr("No voice is available for this language.")
        elif pack_missing:
            message = tr("Download the Japanese pronunciation pack to enable speech and phonetic notation. The audio voice is a separate file.")
        elif not runtime_ready() or not voice_runtime_ready(voice):
            message = runtime_message("Speech components could not be loaded. ")
        elif not enabled:
            message = tr("Audio is turned off.")
        elif self.download.active:
            message = tr("Checking voice files and downloading any missing files…")
        elif ready:
            message = tr("Voice installed. Use 'Hear sample' to preview it, or read your next selection aloud.")
        else:
            message = tr("Download this voice once to enable pronunciation.")
        ui_text(self.status, tr(message))
        if self._download_error:
            ui_text(self.status, tr("Voice download failed: {error}", error=self._download_error))
        if self.download.active:
            self._update_download_metrics()
        license_note = voice.license_note.replace("(non-commercial)", f"({tr('non-commercial')})") if voice else ""
        ui_text(self.details, f'<a style="color:#5eead4" href="{voice.url("MODEL_CARD", view=True)}">{tr("Voice details and licence")}</a>'
            + (f' · {html.escape(license_note)}' if not license_note.startswith("See upstream") else '')
            if voice else "")
        if self.player.busy:
            ui_text(self.preview, tr("Stop sample"))
            self.install.setEnabled(False)

    def _install(self) -> None:
        if self.download.active:
            self.install.setEnabled(False)
            self._download_phase = "cancelling"
            self._progress_timer.stop()
            ui_text(self.status, tr("Cancelling download…"))
            # Cancellation may finish synchronously; let its final refresh win.
            self.download.cancel()
            return
        if self.voice is None or self._maintenance_blocked:
            return
        self.player.stop()
        self._download_stage_changed("checking")
        self._download_error = None
        self.download.start("download" if self.enabled.isChecked() else "download-pronunciation", self.voice)
        if self.download.active:
            self.refresh()

    def set_speech_speed(self, speed: float) -> None:
        self.player.stop()
        self.speech_speed = self.player.speed = speed
        blocked = self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(round(speed * 100))
        self.speed_slider.blockSignals(blocked)
        ui_text(self.speed_label, f"{tr('Pronunciation speed')}: {speed:g}×")

    def _speed_changed(self, value: int) -> None:
        self.set_speech_speed(value / 100)
        self.preferences_changed.emit()

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
        if self._download_error:
            return
        labels = {"checking": tr("Checking voice files…"), "downloading": tr("Downloading voice…"),
                  "verifying": tr("Verifying voice files…"), "cancelling": tr("Cancelling download…")}
        ui_text(self.status, tr(labels[self._download_phase]))
        details = self._transfer_metrics.text(monotonic())
        ui_text(self.download_details, details)

    def _download_activity_changed(self, active: bool) -> None:
        if active:
            self._progress_timer.start()
        else:
            self._progress_timer.stop()
            self.progress.hide()
            self.download_details.hide()
        self.activity_changed.emit()

    def _download_failed(self, message: str) -> None:
        self._download_error = message
        self._progress_timer.stop()
        self.refresh()

    def _download_succeeded(self) -> None:
        self._download_error = None
        self.refresh()

    def _preview(self) -> None:
        if self.player.busy:
            self.player.stop()
        elif self.voice is not None and not self._maintenance_blocked and self.enabled.isChecked():
            self.player.speak(self.voice.sample, self.voice)

    def set_maintenance_blocked(self, blocked: bool) -> None:
        if self._maintenance_blocked != blocked:
            self._maintenance_blocked = blocked
            self.refresh()

    def _playback_changed(self, state: str, message: str) -> None:
        self.refresh()
        if message:
            ui_text(self.status, tr_message(message) if state != "playing" else tr("Playing voice sample…"))
        self.preview.setEnabled(self.preview.isEnabled() and state != "stopping")

    def shutdown(self) -> None:
        self._progress_timer.stop()
        self.player.shutdown()
        self.download.shutdown()
