import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QRect, QRectF, QSize
from PySide6.QtGui import QImage, QPixmap

from language_lens.config import Settings
import language_lens.ui.review as review_module
from language_lens.domain import OcrLine, OcrSpanBox, WordTranslation, build_word_hits
from language_lens.ui.review import OcrTask, ReviewWindow
from language_lens.services.capture import DesktopCapture, ScreenCapture


@pytest.fixture(autouse=True)
def local_test_ocr_parameters(monkeypatch):
    # Engines in this module are deterministic doubles; runtime preparation is
    # exercised separately by the service/worker tests.
    monkeypatch.setattr(review_module.domain_tasks, "local_ocr_parameters", lambda _source: {})


def native_capture(*specs):
    screens = []
    for geometry, scale in specs:
        shot = QPixmap(round(geometry.width() * scale), round(geometry.height() * scale))
        shot.fill(review_module.QColor("red"))
        screens.append(ScreenCapture(shot, geometry))
    geometry = QRect(screens[0].geometry)
    for screen in screens[1:]:
        geometry = geometry.united(screen.geometry)
    preview = QPixmap(geometry.size())
    preview.fill(review_module.QColor("black"))
    return DesktopCapture(preview, geometry, tuple(screens))


def test_native_ocr_cross_monitor_mapping_and_reading_order(monkeypatch, qapp):
    capture = native_capture((QRect(0, 0, 1000, 800), 2), (QRect(-800, 0, 800, 600), 1.25))
    calls = []

    class Engine:
        def __init__(self, source, **_params):
            pass

        def recognize(self, image, confidence):
            calls.append(image.shape)
            if image.shape[1] == 200:
                return [OcrLine("right", .99, ((20, 20), (80, 20), (80, 40), (20, 40)), (
                    OcrSpanBox(0, 5, ((20, 20), (80, 20), (80, 40), (20, 40))),
                ), ((0, 5),))]
            return [OcrLine("left", .99, ((10, 10), (40, 10), (40, 20), (10, 20)))]

    monkeypatch.setattr(review_module, "RapidOcrEngine", Engine)
    task = review_module.NativeOcrTask(capture, QRect(700, 100, 200, 40), Settings(source_language="en"))
    results = []
    task.signals.result.connect(results.append)
    task.run()
    assert calls == [(80, 200, 3), (50, 125, 3)]
    left, right = results[0]
    assert (left.text, right.text) == ("left", "right")  # not monitor enumeration order
    assert left.bounds == review_module.Rect(8, 8, 24, 8)
    assert right.bounds == review_module.Rect(110, 10, 30, 10)
    assert right.span_boxes[0].polygon == right.polygon
    assert right.token_spans == ((0, 5),)


def test_native_retry_maps_fractional_crop_padding_and_word_boxes(monkeypatch, qapp):
    capture = native_capture((QRect(0, 0, 640, 480), 1.5))
    calls = []

    class Engine:
        def __init__(self, source, **_params):
            pass

        def recognize(self, image, confidence):
            calls.append(image.shape)
            if len(calls) == 1:
                return []
            polygon = ((108, 68), (168, 68), (168, 98), (108, 98))
            return [OcrLine("word", .99, polygon, (OcrSpanBox(0, 4, polygon),), ((0, 4),)),
                    OcrLine("outside", .99, ((0, 0), (10, 0), (10, 10), (0, 10)))]

    monkeypatch.setattr(review_module, "RapidOcrEngine", Engine)
    task = review_module.NativeOcrTask(capture, QRect(101, 99, 80, 20), Settings())
    results = []
    task.signals.result.connect(results.append)
    task.run()
    assert calls == [(31, 121, 3), (158, 338, 3)]
    assert [line.text for line in results[0]] == ["word"]
    line = results[0][0]
    assert line.bounds.x == pytest.approx(19 + 2 / 3)
    assert line.bounds.y == pytest.approx(6 + 1 / 3)
    assert line.bounds.width == pytest.approx(20)
    assert line.bounds.height == pytest.approx(10)
    assert line.span_boxes[0].polygon == line.polygon


def test_review_uses_per_monitor_windows_and_controls_on_selected_monitor(monkeypatch, qapp):
    tasks = []
    monkeypatch.setattr(review_module, "QThreadPool", type("Pool", (), {
        "globalInstance": staticmethod(lambda: type("Instance", (), {"start": lambda self, task: tasks.append(task)})()),
    }))
    capture = native_capture((QRect(-1000, -200, 1000, 800), 1.25), (QRect(300, 0, 800, 600), 2))
    selection = QRect(1450, 300, 200, 40)
    window = ReviewWindow(capture, selection, Settings(speech_enabled=False))
    window.show()
    qapp.processEvents()
    assert window.geometry() == capture.screens[1].geometry
    assert len(window._tiles) == 1
    assert window._tiles[0].geometry() == capture.screens[0].geometry
    assert window._tiles[0].isWindow()
    assert window._tiles[0].isVisible()
    assert not window.isFullScreen()
    assert window.canvas.size() == capture.screens[1].geometry.size()
    assert isinstance(tasks[0], review_module.NativeOcrTask)
    assert window.rect().contains(window._footer.geometry())
    assert window.canvas.selection_display_rect() == QRectF(150, 100, 200, 40)
    position = window.canvas._bubble_position(QRectF(200, 105, 40, 20))
    assert window.rect().contains(QRect(position, window.canvas._bubble.size()))
    assert len(tasks) == 1  # one OCR job, not one per window
    # Results are shared, while each viewport converts global source hit boxes.
    source = OcrLine("word", .99, ((-800, 10), (-760, 10), (-760, 30), (-800, 30)))
    window._ocr_finished([source])
    assert window.canvas._hits == window._tiles[0].canvas._hits
    window._translation_finished(("translated", {"word": WordTranslation(("woord",))}))
    assert window._tiles[0].canvas._hits[0].translation.candidates == ("woord",)
    word = window._tiles[0].canvas._source_to_display(window._hits[0].bounds)
    assert word == QRectF(650, 310, 40, 20)
    tile = window._tiles[0]
    window.close()
    assert not tile.isVisible()
    window.deleteLater()


def test_current_monitor_review_retains_negative_origin(monkeypatch, qapp):
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    capture = native_capture((QRect(-800, -100, 800, 900), 1.5))
    window = ReviewWindow(capture, QRect(100, 100, 200, 30), Settings(speech_enabled=False))
    window.show()
    qapp.processEvents()
    assert window.geometry() == QRect(-800, -100, 800, 900)
    assert window.canvas.selection_display_rect() == QRectF(100, 100, 200, 30)
    window.close()
    window.deleteLater()


@pytest.mark.parametrize("escape", [True, False])
def test_secondary_review_window_exit_closes_all_windows_once(monkeypatch, qapp, escape):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    capture = native_capture((QRect(0, 0, 800, 600), 1.25), (QRect(800, -100, 1000, 800), 2))
    window = ReviewWindow(capture, QRect(100, 100, 200, 40), Settings(speech_enabled=False))
    finished = []
    window.finished.connect(lambda: finished.append(True))
    window.show()
    tile = window._tiles[0]
    if escape:
        QTest.keyClick(tile, Qt.Key.Key_Escape)
    else:
        tile.close()
    assert finished == [True]
    assert window._closed
    assert not window.isVisible() and not tile.isVisible()
    window.deleteLater()


def test_native_selection_in_gap_never_initializes_ocr(monkeypatch, qapp):
    capture = native_capture((QRect(0, 0, 800, 600), 1.25), (QRect(1000, 0, 800, 600), 2))
    def no_engine(*args):
        pytest.fail("A blank desktop gap must not initialize OCR")
    monkeypatch.setattr(review_module, "RapidOcrEngine", no_engine)
    task = review_module.NativeOcrTask(capture, QRect(850, 100, 100, 40), Settings())
    results = []
    task.signals.result.connect(results.append)
    task.run()
    assert results == [[]]


class IdleThreadPool:
    @staticmethod
    def globalInstance():  # noqa: N802
        return IdleThreadPool()

    def start(self, task):
        pass


def test_click_on_secondary_monitor_synchronizes_navigation_across_monitors(monkeypatch, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    capture = native_capture((QRect(0, 0, 800, 600), 1.25), (QRect(800, 0, 800, 600), 2))
    window = ReviewWindow(capture, QRect(650, 100, 400, 40), Settings(speech_enabled=False))
    window._ocr_finished([
        OcrLine("left first", .99, ((0, 0), (140, 0), (140, 30), (0, 30))),
        OcrLine("right last", .99, ((170, 0), (350, 0), (350, 30), (170, 30))),
    ])
    window.show()
    qapp.processEvents()
    window._navigate_word(-1)  # pin 'last' on the main monitor first
    assert window.canvas._pinned
    tile_canvas = window._tiles[0].canvas
    point = tile_canvas._source_to_display(tile_canvas._hits[1].bounds).center().toPoint()
    QTest.mouseClick(tile_canvas, Qt.MouseButton.LeftButton, pos=point)
    assert window._current_word_index == 1 and tile_canvas._hovered.text == "first"
    assert tile_canvas._pinned and not window.canvas._pinned
    assert window.canvas._bubble.isHidden()
    window._navigate_word(1)
    assert window.canvas._pinned and window.canvas._hovered.text == "right"
    assert tile_canvas._bubble.isHidden() and not tile_canvas._pinned
    window.close()


def test_ocr_task_can_be_created_without_a_pixmap():
    image = QImage(120, 40, QImage.Format.Format_RGB888)

    task = OcrTask(image, Settings())

    assert task.image.size() == QSize(120, 40)


def test_enlarged_retry_transforms_native_boxes_without_changing_word_offsets():
    task = OcrTask(
        QImage(100, 30, QImage.Format.Format_RGB888), Settings(),
        retry_offset=review_module.QPoint(-20, -20), selection_size=QSize(100, 30),
    )
    source = OcrLine("cat", .99, ((60, 50), (160, 50), (160, 90), (60, 90)), (
        OcrSpanBox(0, 3, ((70, 50), (150, 50), (150, 90), (70, 90))),
    ), ((0, 3),))
    mapped = task._map_retry_lines([source])[0]
    assert mapped.token_spans == ((0, 3),)
    assert mapped.span_boxes[0].polygon == ((15, 5), (55, 5), (55, 25), (15, 25))


def test_review_retains_ocr_word_boxes_when_moving_back_to_screenshot(monkeypatch, qapp):
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    window = ReviewWindow(QPixmap(800, 600), QRect(100, 200, 400, 40), Settings(speech_enabled=False))
    source = OcrLine("cat", .99, ((0, 0), (100, 0), (100, 20), (0, 20)), (
        OcrSpanBox(0, 3, ((10, 0), (70, 0), (70, 20), (10, 20))),
    ), ((0, 3),))
    window._ocr_finished([source])
    assert window._hits[0].bounds == review_module.Rect(110, 200, 60, 20)
    assert (window._hits[0].source_start, window._hits[0].source_end) == (0, 3)
    window.close()


@pytest.mark.parametrize("target", ["es", "nl", "en"])
def test_review_segments_japanese_independently_of_translation_target(monkeypatch, qapp, target):
    monkeypatch.setattr(review_module, "QThreadPool", IdleThreadPool)
    window = ReviewWindow(QPixmap(800, 600), QRect(100, 200, 400, 40),
                          Settings(source_language="ja", target_language=target))
    source = OcrLine("私は本を読みます。", .99, ((0, 0), (400, 0), (400, 20), (0, 20)))
    window._ocr_finished([source])
    assert [hit.text for hit in window._hits] == ["私", "は", "本", "を", "読み", "ます"]
    assert all(source.text[hit.source_start:hit.source_end] == hit.text for hit in window._hits)
    window.close()


def test_ocr_task_retries_with_padding_and_maps_results_back(monkeypatch, qapp):
    calls = []

    class RetryEngine:
        def __init__(self, source_language, **_params):
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
        def __init__(self, source_language, **_params):
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
    assert results[1][0] is None and results[-1][0] is None
    assert results[1][1]["courses"].candidates == ("pratos", "cursos")
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
    assert popup.search_status.text() == "4 model suggestions available · showing best match"
    assert popup.more.text() == "Show 3 other candidates"
    assert "Word in isolation" in popup.translation_note.text()
    assert canvas.rect().contains(popup.geometry())
    popup.more.click()
    assert "best → worst" in popup.translation_order.text()
    assert popup.alternatives.text() == "2. cursos\n3. percursos\n4. rumos"
    assert popup.more.text() == "Show best match only"
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
