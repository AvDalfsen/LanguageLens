from __future__ import annotations

from language_lens.i18n import tr, tr_message, language, ui_text, ui_widget

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStyle, QVBoxLayout, QWidget

from language_lens.domain import WordTranslation
from language_lens.services.translation import EXPANDED_HYPOTHESES


class WordPopup(QFrame):
    entered = Signal()
    left = Signal()
    dismissed = Signal()
    play_requested = Signal()
    retry_requested = Signal()
    more_requested = Signal()
    search_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("wordPopup")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedWidth(330)
        self._available_height = 560
        self.setStyleSheet("""
            QFrame#wordPopup { background:#07111f; border:1px solid #5eead4; border-radius:7px; }
            QFrame#wordPopup QLabel { background:transparent; border:0; }
            QFrame#wordPopup QScrollArea, QWidget#popupBody { background:transparent; border:0; }
            QLabel#popupWord { font-weight:700; font-size:16px; }
            QLabel#popupBestTranslation { font-weight:600; color:#a7f3d0; }
            QLabel#popupIpa { font-family:'Segoe UI', 'Arial'; font-size:21px; color:#a7f3d0; }
            QLabel#popupDetail, QLabel#popupVoice, QLabel#popupTranslationOrder,
            QLabel#popupTranslationNote, QLabel#popupSearchStatus { font-size:12px; color:#b8c6da; }
            QPushButton#dismissWord { padding:0; border:0; background:transparent; font-size:18px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        header = QHBoxLayout()
        self.word = self._label("popupWord")
        close = ui_widget(QPushButton, "×")
        close.setObjectName("dismissWord")
        ui_text(close, tr("Dismiss word details"), property="accessibleName")
        close.setFixedSize(24, 24)
        close.clicked.connect(self.dismissed)
        header.addWidget(self.word, 1)
        header.addWidget(close)
        layout.addLayout(header)
        self._body = QWidget()
        self._body.setObjectName("popupBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(7)
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._body)
        layout.addWidget(self._scroll)
        self.translation_order = self._label("popupTranslationOrder")
        self.translation = self._label("popupBestTranslation")
        self.alternatives = self._label()
        self.translation_note = self._label("popupTranslationNote")
        ui_text(self.translation_note, tr("Ranked by the translation model for this word alone. The selected sentence is not "
            "used to rank these candidates. These are suggestions, not all dictionary meanings "
            "or confidence percentages. A word can translate to several words in another language."), property="toolTip")
        for label in (self.translation, self.alternatives):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.ipa = self._label("popupIpa")
        self.ipa.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.ipa.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ui_text(self.ipa, tr("Estimated pronunciation with display-only stress formatting; not a measurement of the voice's audio."), property="toolTip")
        self.detail = self._label("popupDetail")
        self.voice = self._label("popupVoice")
        for label in (self.word, self.translation, self.alternatives, self.ipa):
            label._lens_untranslated_text = True
        for label, name in ((self.word, tr("Selected source word")), (self.translation, tr("Top suggestion · isolated word")),
                            (self.alternatives, tr("Other translation candidates")), (self.ipa, tr("Estimated pronunciation")),
                            (self.detail, tr("Pronunciation context")), (self.voice, tr("Pronunciation voice"))):
            ui_text(label, name, property="accessibleName")
        self.more = ui_widget(QPushButton, tr("More candidates"))
        self.more.clicked.connect(self.more_requested)
        self.search = ui_widget(QPushButton, tr("Search for more candidates"))
        self.search.clicked.connect(self.search_requested)
        ui_text(self.search, tr("Suggestions are model guesses for this word alone, not dictionary meanings."), property="toolTip")
        ui_text(self.more, tr("Show or hide alternatives already found for this word; no new search or download is needed. "
            "'Show best match only' collapses the list. Use 'Search for more candidates' for a separate, "
            "wider model search. These suggestions are not an exhaustive dictionary."), property="toolTip")
        self.search_status = self._label("popupSearchStatus")
        for widget in (self.translation_order, self.translation, self.alternatives,
                       self.more, self.search, self.search_status, self.translation_note, self.ipa, self.detail, self.voice):
            self._body_layout.addWidget(widget)
        buttons = QHBoxLayout()
        self.play = ui_widget(QPushButton, tr("Pronounce word"))
        self.play.clicked.connect(self.play_requested)
        self.retry = ui_widget(QPushButton, tr("Retry pronunciation"))
        self.retry.clicked.connect(self.retry_requested)
        buttons.addWidget(self.play)
        buttons.addWidget(self.retry)
        buttons.addStretch()
        self._body_layout.addLayout(buttons)
        self.set_translation(None)
        self.set_expansion_state(available=False)
        self.fit_to_height(self._available_height)
        self.hide()

    def set_translation(self, result: WordTranslation | None, *, show_all: bool = True) -> None:
        all_candidates = result.candidates if result else ()
        candidates = all_candidates if show_all else all_candidates[:1]
        multiple = len(all_candidates) > 1
        ui_text(self.translation_order, tr("Top suggestion · isolated word") if not show_all else
            tr("Possible translations · model order") if multiple else tr("Word translation"))
        self.translation_order.setVisible(bool(candidates))
        ui_text(self.translation, f"1. {candidates[0]} · {tr('Top suggestion')}" if multiple else
            candidates[0] if candidates else
            tr("Translation unavailable") if result is not None else tr("Translating…"))
        ui_text(self.alternatives, "\n".join(
            f"{rank}. {value}" for rank, value in enumerate(candidates[1:], 2)
        ))
        self.alternatives.setVisible(show_all and len(candidates) > 1)
        note = tr("Word in isolation · model ranking") if multiple else tr("Only one distinct candidate · word in isolation")
        ui_text(self.translation_note, tr(result.note or note) if result else "")
        self.translation_note.setVisible(result is not None)

    def set_expansion_state(self, *, available: bool, loading: bool = False,
                            showing: bool = False, searched: bool = False,
                            count: int | None = None, error: str = "") -> None:
        self.more.setVisible(available and (count or 0) > 1)
        self.more.setEnabled(True)
        self.search.setVisible(available and not searched)
        self.search.setEnabled(not loading)
        ui_text(self.search, tr("Finding more…") if loading else tr("Retry wider search") if error else tr("Search for more candidates"))
        others = max(0, (count or 0) - 1)
        ui_text(self.more, tr("Show best match only") if showing else
            f"Show {others} other {'candidate' if others == 1 else 'candidates'}" if language() == "en" else tr("Show {count} other candidates", count=others))
        ui_text(self.search_status, tr("Searching locally…") if loading else tr_message(error) if error else
            ((f"{count} distinct {'candidate' if count == 1 else 'candidates'} from {EXPANDED_HYPOTHESES} model guesses" if language() == "en" else tr("{count} distinct candidates from {guesses} model guesses", count=count, guesses=EXPANDED_HYPOTHESES)) if searched and count is not None else
             (f"{count} model {'suggestion' if count == 1 else 'suggestions'} available · {'showing all' if showing else 'showing best match'}" if language() == "en" else tr("{count} model suggestions available", count=count)) if count is not None else ""))
        self.search_status.setVisible(bool(self.search_status.text()))

    def fit_to_height(self, available: int) -> None:
        """Keep the header visible and make long result lists scroll on small screens."""
        self._available_height = min(560, available)
        margins = self.layout().contentsMargins()
        overhead = margins.top() + margins.bottom() + max(24, self.word.sizeHint().height()) + 7
        budget = max(40, self._available_height - overhead)
        width = self.width() - margins.left() - margins.right()
        self._body_layout.invalidate()
        desired = max(self._body_layout.minimumSize().height(), self._body_layout.heightForWidth(width))
        if desired > budget:
            width -= self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
            desired = max(desired, self._body_layout.heightForWidth(width))
        self._body.setFixedWidth(width)
        self._body.setMinimumHeight(desired)
        self._scroll.setFixedHeight(min(desired, budget))
        self.layout().activate()
        self.adjustSize()

    def reset_scroll(self) -> None:
        self._scroll.verticalScrollBar().setValue(0)

    @staticmethod
    def _label(name: str = "") -> QLabel:
        label = QLabel()
        label.setObjectName(name)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        return label

    def enterEvent(self, event) -> None:  # noqa: N802
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.left.emit()
        super().leaveEvent(event)
