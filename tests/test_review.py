import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QRectF, QSize
from PySide6.QtGui import QImage, QPixmap

from language_lens.config import Settings
import language_lens.ui.review as review_module
from language_lens.domain import OcrLine, WordTranslation, build_word_hits
from language_lens.ui.review import OcrTask, ReviewWindow


class IdleThreadPool:
    @staticmethod
    def globalInstance():  # noqa: N802
        return IdleThreadPool()

    def start(self, task):
        pass


def test_ocr_task_can_be_created_without_a_pixmap():
    image = QImage(120, 40, QImage.Format.Format_RGB888)

    task = OcrTask(image, Settings())

    assert task.image.size() == QSize(120, 40)


def test_ocr_task_retries_with_padding_and_maps_results_back(monkeypatch, qapp):
    calls = []

    class RetryEngine:
        def __init__(self, source_language):
            pass

        def recognize(self, image, min_confidence):
            calls.append(image.shape)
            if len(calls) == 1:
                return []
            return [
                OcrLine(
                    "small text",
                    0.95,
                    ((60, 50), (160, 50), (160, 90), (60, 90)),
                ),
                OcrLine(
                    "outside",
                    0.95,
                    ((4, 4), (24, 4), (24, 20), (4, 20)),
                ),
            ]

    monkeypatch.setattr(review_module, "RapidOcrEngine", RetryEngine)
    task = OcrTask(
        QImage(100, 30, QImage.Format.Format_RGB888),
        Settings(),
        retry_image=QImage(140, 70, QImage.Format.Format_RGB888),
        retry_offset=review_module.QPoint(-20, -20),
        selection_size=QSize(100, 30),
        retry_scale=2.0,
    )
    results = []
    progress = []
    task.signals.result.connect(results.append)
    task.signals.progress.connect(progress.append)

    task.run()

    assert calls == [(30, 100, 3), (140, 280, 3)]
    assert [line.text for line in results[0]] == ["small text"]
    assert results[0][0].bounds == review_module.Rect(10, 5, 50, 20)
    assert progress == [
        "Nothing found on the first scan. Retrying with padding and enlargement…"
    ]


def test_ocr_task_does_not_retry_after_a_successful_first_scan(monkeypatch, qapp):
    calls = []
    expected = OcrLine("already found", 0.99, ((1, 1), (20, 1), (20, 10), (1, 10)))

    class SuccessfulEngine:
        def __init__(self, source_language):
            pass

        def recognize(self, image, min_confidence):
            calls.append(image.shape)
            return [expected]

    monkeypatch.setattr(review_module, "RapidOcrEngine", SuccessfulEngine)
    task = OcrTask(
        QImage(100, 30, QImage.Format.Format_RGB888),
        Settings(),
        retry_image=QImage(140, 70, QImage.Format.Format_RGB888),
    )
    results = []
    task.signals.result.connect(results.append)

    task.run()

    assert calls == [(30, 100, 3)]
    assert results == [[expected]]


def test_review_window_tracks_the_full_capture_size(monkeypatch, qapp):
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    pixmap = QPixmap(800, 600)

    window = ReviewWindow(pixmap, QRect(100, 120, 300, 80), Settings())
    window.show()
    qapp.processEvents()

    assert window._pixmap_size == QSize(800, 600)
    assert window.isVisible()
    window.close()
    qapp.processEvents()


def test_control_panel_is_anchored_below_an_upper_selection(monkeypatch, qapp):
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    window = ReviewWindow(
        QPixmap(1000, 800), QRect(200, 100, 300, 80), Settings()
    )
    window.resize(1000, 800)
    window._position_children()

    selection = window.canvas.selection_display_rect()
    panel = window._footer.geometry()

    assert panel.top() > selection.bottom()
    assert abs(panel.center().x() - selection.center().x()) <= 1
    window.close()


def test_control_panel_is_anchored_above_a_lower_selection(monkeypatch, qapp):
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    window = ReviewWindow(
        QPixmap(1000, 800), QRect(500, 620, 250, 60), Settings()
    )
    window.resize(1000, 800)
    window._position_children()

    selection = window.canvas.selection_display_rect()
    panel = window._footer.geometry()

    assert panel.bottom() < selection.top()
    assert abs(panel.center().x() - selection.center().x()) <= 1
    window.close()


def test_control_panel_stays_inside_screen_edges(monkeypatch, qapp):
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    window = ReviewWindow(
        QPixmap(1000, 800), QRect(0, 100, 120, 60), Settings()
    )
    window.resize(1000, 800)
    window._position_children()

    panel = window._footer.geometry()

    assert panel.left() >= 22
    assert panel.right() <= window.width() - 22
    window.close()


def test_word_bubble_uses_review_overlay_and_avoids_panel(monkeypatch, qapp):
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    window = ReviewWindow(
        QPixmap(1000, 800), QRect(300, 600, 300, 60), Settings()
    )
    window.resize(1000, 800)
    window._position_children()
    window.canvas._bubble.translation.setText("Seatbelts\ncintos de segurança")
    window.canvas._bubble.adjustSize()

    position = window.canvas._bubble_position(QRectF(360, 620, 120, 40))
    bubble_rect = QRect(position, window.canvas._bubble.size())

    assert window.canvas._bubble.parentWidget() is window
    assert not bubble_rect.intersects(window.canvas._tooltip_avoid_rect)
    window.close()


def test_translation_task_delivers_sentence_and_words_progressively_even_if_one_fails(monkeypatch, qapp):
    results, calls, errors = [], [], []

    class Translator:
        def translate(self, text, source, target):
            calls.append(text)
            return "Sentence with context"

        def word_candidates(self, text, source, target):
            # The sentence has already been delivered while the word is still pending.
            assert results[0] == ("Sentence with context", {})
            calls.append(text)
            if text == "unknown":
                raise review_module.TranslationUnavailable("No translation")
            return WordTranslation(("pratos", "cursos"))

    monkeypatch.setattr(review_module, "ArgosTranslator", Translator)
    line = OcrLine("courses unknown courses", .99, ((0, 0), (400, 0), (400, 40), (0, 40)))
    task = review_module.TranslationTask([line], ["courses", "unknown", "courses"], Settings())
    task.signals.result.connect(results.append)
    task.signals.error.connect(errors.append)
    task.run()
    assert not errors
    assert calls == [line.text, "courses", "unknown"]
    assert len(results) == 3
    assert list(results[1][1]) == ["courses"]  # earlier snapshots are not mutated
    assert results[-1][1]["courses"].candidates == ("pratos", "cursos")
    assert not results[-1][1]["unknown"].candidates
    assert "unavailable" in results[-1][1]["unknown"].note


def test_ranked_word_popup_updates_pinned_word_and_clears_stale_alternatives(qapp):
    from PySide6.QtCore import QCoreApplication, QEvent
    canvas = review_module.ImageCanvas(QPixmap(900, 700), QRect(100, 100, 500, 40))
    canvas.resize(900, 700)
    canvas.selection_display_rect()
    line = OcrLine("courses other", .99, ((100, 100), (600, 100), (600, 140), (100, 140)))
    canvas.set_hits(build_word_hits([line]))
    canvas._hovered = canvas._hits[0]
    canvas._pinned = True
    canvas._refresh_bubble()
    popup = canvas._bubble
    assert popup.translation.text() == "Translating…"
    canvas.set_translations({"courses": WordTranslation(("pratos", "cursos", "percursos", "rumos"))})
    assert canvas._pinned and canvas._hovered.text == "courses"
    assert popup.translation_order.text() == "Best word translation"
    assert popup.translation.text() == "1. pratos · Best match"
    assert popup.alternatives.isHidden()
    assert popup.search_status.text() == "4 candidates found · showing best match"
    assert popup.more.text() == "Show 3 other candidates"
    assert "Word in isolation" in popup.translation_note.text()
    assert canvas.rect().contains(popup.geometry())
    popup.more.click()
    assert "best → worst" in popup.translation_order.text()
    assert popup.alternatives.text() == "2. cursos\n3. percursos\n4. rumos"
    assert popup.more.text() == "Search for more candidates"
    # A different word is still pending; it must not inherit these alternatives.
    canvas._hovered = canvas._hits[1]
    canvas._refresh_bubble()
    assert popup.translation.text() == "Translating…" and popup.alternatives.isHidden()
    canvas.set_translations({"other": WordTranslation(("outro",), "Alternatives unavailable")})
    assert popup.translation.text() == "outro"
    assert popup.translation_note.text() == "Alternatives unavailable"
    assert popup.alternatives.isHidden()
    assert canvas._hits[0].translation.candidates[0] == "pratos"
    canvas.dismiss_word()
    canvas.close()
    canvas.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_tall_word_popup_uses_space_beside_the_controls(qapp):
    from PySide6.QtCore import QCoreApplication, QEvent
    canvas = review_module.ImageCanvas(QPixmap(1280, 720), QRect(265, 290, 650, 50))
    canvas.resize(1280, 720)
    canvas._bubble.setFixedSize(330, 375)
    canvas.set_tooltip_avoid_rect(QRect(257, 348, 666, 166))
    word = QRectF(770, 290, 130, 40)
    position = canvas._bubble_position(word)
    popup_rect = QRect(position, canvas._bubble.size())
    assert canvas.rect().contains(popup_rect)
    assert not popup_rect.intersects(canvas._tooltip_avoid_rect)
    assert not QRectF(popup_rect).intersects(word)
    canvas.close()
    canvas.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
