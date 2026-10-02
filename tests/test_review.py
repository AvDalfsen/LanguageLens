import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QRectF, QSize
from PySide6.QtGui import QImage, QPixmap

from language_lens.config import Settings
import language_lens.ui.review as review_module
from language_lens.domain import OcrLine
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
    window.canvas._bubble.setText("<b>Seatbelts</b><br>cintos de segurança")
    window.canvas._bubble.adjustSize()

    position = window.canvas._bubble_position(QRectF(360, 620, 120, 40))
    bubble_rect = QRect(position, window.canvas._bubble.size())

    assert window.canvas._bubble.parentWidget() is window
    assert not bubble_rect.intersects(window.canvas._tooltip_avoid_rect)
    window.close()
