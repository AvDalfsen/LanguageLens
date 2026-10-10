from threading import Event

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QRect
from PySide6.QtGui import QPixmap

from language_lens.config import Settings
from language_lens.domain import OcrLine, WordTranslation, build_word_hits
from language_lens.ui import review


@pytest.fixture
def canvas(qapp):
    widget = review.ImageCanvas(QPixmap(900, 600), QRect(100, 100, 500, 40))
    widget.resize(900, 600)
    widget.selection_display_rect()
    widget.set_hits(build_word_hits([OcrLine(
        "bank watch", .99, ((100, 100), (600, 100), (600, 140), (100, 140)),
    )]))
    widget.set_translations({"bank": WordTranslation(("bank", "banken")),
                             "watch": WordTranslation(("kijken", "horloge"))})
    widget._hovered = widget._hits[0]
    widget._refresh_bubble()
    yield widget
    widget.dismiss_word()
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_expansion_is_on_demand_cached_and_not_overwritten_by_late_compact_results(canvas):
    requested = []
    canvas.more_candidates_requested.connect(requested.append)
    popup = canvas._bubble
    assert not requested and popup.more.text() == "Show 1 other candidate"
    assert popup.translation.text() == "1. bank · Top suggestion"
    assert popup.alternatives.isHidden()
    assert popup.search_status.text() == "2 model suggestions available · showing best match"
    popup.more.click()
    assert not requested
    assert popup.alternatives.text() == "2. banken"
    assert popup.more.text() == "Show best match only"
    assert popup.search_status.text() == "2 model suggestions available · showing all"
    popup.more.click()
    assert popup.alternatives.isHidden() and not requested  # hide is always immediate
    popup.search.click()
    assert requested == ["bank"] and canvas._pinned
    assert not popup.search.isEnabled() and "Finding" in popup.search.text()
    canvas._search_candidates()  # guard duplicate requests even outside the disabled button
    assert requested == ["bank"]
    # A wider beam can change the ranking; its best result must remain the best
    # result even after the expanded list is collapsed.
    expanded = WordTranslation(("oever", "bank", "banken", "bankrekening", "de bank", "bank-"))
    canvas.set_more_candidates("bank", expanded)
    assert popup.more.text() == "Show best match only"
    assert popup.translation.text() == "1. oever · Top suggestion"
    assert "5. de bank" in popup.alternatives.text()
    assert "6 distinct candidates from 12" in popup.search_status.text()
    canvas.set_translations({"bank": WordTranslation(("old compact result",))})
    assert popup.translation.text() == "1. oever · Top suggestion"
    popup.more.click()
    assert popup.alternatives.isHidden()
    assert popup.translation.text() == "1. oever · Top suggestion"
    assert popup.more.text() == "Show 5 other candidates"
    assert popup.search_status.text() == "6 distinct candidates from 12 model guesses"
    popup.more.click()
    assert "5. de bank" in popup.alternatives.text() and requested == ["bank"]


def test_results_for_previous_word_do_not_change_current_popup_or_reopen_dismissed_one(canvas):
    popup = canvas._bubble
    popup.more.click()
    popup.search.click()
    canvas._hovered = canvas._hits[1]
    canvas._refresh_bubble()
    canvas.set_more_candidates("bank", WordTranslation(("bank", "oever")))
    assert popup.word.text() == "watch" and popup.alternatives.isHidden()
    assert popup.more.text() == "Show 1 other candidate"
    canvas.dismiss_word()
    canvas.set_more_candidates("watch", WordTranslation(("kijken", "horloge", "wacht")))
    assert popup.isHidden()
    canvas._hovered = canvas._hits[0]
    canvas._refresh_bubble()
    assert "oever" in popup.alternatives.text()
    assert popup.more.text() == "Show best match only"
    assert "2 distinct candidates" in popup.search_status.text()


def test_expansion_failure_keeps_existing_translation_and_offers_retry(canvas):
    popup = canvas._bubble
    requested = []
    canvas.more_candidates_requested.connect(requested.append)
    popup.more.click()
    assert not requested  # reveal the compact candidates first
    popup.search.click()
    assert requested == ["bank"]
    canvas.set_more_candidates("bank", None, "Test failure")
    assert popup.translation.text() == "1. bank · Top suggestion"
    assert popup.search.text() == "Retry wider search"
    assert popup.search.isEnabled() and "Test failure" in popup.search_status.text()
    popup.search.click()
    assert requested == ["bank", "bank"]


def test_hide_during_search_remains_hidden_when_result_arrives(canvas):
    popup = canvas._bubble
    popup.search.click()
    popup.more.click()
    assert popup.alternatives.isHidden()
    canvas.set_more_candidates("bank", WordTranslation(("oever", "bank", "banken")))
    assert popup.alternatives.isHidden() and popup.translation.text() == "1. oever · Top suggestion"


def test_single_compact_candidate_can_search_for_more(canvas):
    canvas.set_translations({"bank": WordTranslation(("bank",))})
    popup = canvas._bubble
    requested = []
    canvas.more_candidates_requested.connect(requested.append)
    assert popup.translation.text() == "bank"
    assert popup.search_status.text() == "1 model suggestion available · showing best match"
    assert popup.more.isHidden() and popup.search.text() == "Search for more candidates"
    popup.search.click()
    assert requested == ["bank"]


def test_long_expanded_list_scrolls_without_leaving_small_screen(canvas, qapp):
    canvas.resize(640, 400)
    canvas.configure_pronunciation(True, True, "UK English · Alan")
    hit = canvas._hovered
    canvas.set_pronunciations([dict(start=hit.source_start, end=hit.source_end,
        ipa="bæŋk", phonemes="bæŋk", mode="isolated")])
    canvas.set_more_candidates("bank", WordTranslation(tuple(
        f"Candidate {index} with several words wrapping across the available width"
        for index in range(12)
    )))
    canvas.show()
    qapp.processEvents()
    popup = canvas._bubble
    assert canvas.rect().contains(popup.geometry())
    assert popup._scroll.verticalScrollBar().maximum() > 0
    assert "12. Candidate 11" in popup.alternatives.text()
    assert popup.play.isEnabled() and not popup.ipa.isHidden()


def test_worker_respects_close_and_review_ignores_late_result(monkeypatch, qapp):
    calls = []
    class Translator:
        def word_candidates(self, *args, **kwargs):
            calls.append(kwargs)
            return WordTranslation(("bank", "oever"))
    cancel = Event()
    task = review.MoreCandidatesTask("bank", Settings(), Translator(), cancel)
    results = []
    task.signals.result.connect(results.append)
    task.run()
    assert calls == [{"expanded": True}] and results[0][0] == "bank"
    cancel.set()
    task.run()
    assert len(calls) == len(results) == 1
    class IdlePool:
        @staticmethod
        def globalInstance():
            return IdlePool()
        def start(self, task):
            pass
    monkeypatch.setattr(review, "TaskPool", IdlePool)
    window = review.ReviewWindow(QPixmap(900, 600), QRect(100, 100, 300, 40), Settings())
    window.close()
    assert window._translation_cancelled.is_set()
    window._more_candidates_finished(results[0])
    assert not window.canvas._expanded_translations
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
