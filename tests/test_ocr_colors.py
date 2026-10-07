from types import SimpleNamespace

import numpy as np
import pytest
import rapidocr
from rapidocr.utils.load_image import LoadImage
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QColor, QImage, QPixmap

from language_lens.config import Settings
from language_lens.services.capture import DesktopCapture, ScreenCapture
from language_lens.ui.review import NativeOcrTask, OcrTask, qimage_to_bgr_array


@pytest.mark.parametrize("width", [1, 2, 3, 4, 5, 7])
@pytest.mark.parametrize("image_format", [
    QImage.Format.Format_RGB888,
    QImage.Format.Format_BGR888,
    QImage.Format.Format_RGB32,
    QImage.Format.Format_ARGB32,
    QImage.Format.Format_RGBA8888,
    QImage.Format.Format_ARGB32_Premultiplied,
    QImage.Format.Format_Grayscale8,
])
def test_qimage_conversion_preserves_colours_and_strips_row_padding(width, image_format):
    image = QImage(width, 2, image_format)
    colours = [QColor("red"), QColor("blue"), QColor("green"), QColor(233, 17, 81),
               QColor("black"), QColor("white"), QColor(19, 183, 251)]
    for y in range(2):
        for x in range(width):
            image.setPixelColor(x, y, colours[(x + y) % len(colours)])
    image.setDevicePixelRatio(1.5)
    expected = np.array([
        [[image.pixelColor(x, y).blue(), image.pixelColor(x, y).green(), image.pixelColor(x, y).red()]
         for x in range(width)] for y in range(2)
    ], dtype=np.uint8)

    converted = qimage_to_bgr_array(image)
    assert converted.shape == (2, width, 3)
    assert converted.dtype == np.uint8
    assert converted.flags.c_contiguous and converted.flags.owndata
    np.testing.assert_array_equal(converted, expected)
    # Use the installed backend's real image loader: no second channel swap.
    np.testing.assert_array_equal(LoadImage()(converted), expected)
    assert image.format() == image_format
    assert image.devicePixelRatio() == 1.5


def test_bgr_array_is_independent_of_source_image_lifetime():
    image = QImage(3, 2, QImage.Format.Format_RGB888)
    image.fill(QColor(241, 17, 83))
    converted = qimage_to_bgr_array(image)
    image.fill(QColor("blue"))
    del image
    np.testing.assert_array_equal(converted[0, 0], [83, 17, 241])
    converted[0, 0] = [1, 2, 3]
    np.testing.assert_array_equal(converted[1, 0], [83, 17, 241])


def test_null_image_has_a_clear_error():
    with pytest.raises(ValueError, match="empty image"):
        qimage_to_bgr_array(QImage())


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("retry", [False, True])
def test_ocr_boundary_gets_correct_bgr_on_normal_native_and_retry_paths(monkeypatch, qapp, native, retry):
    calls = []

    def backend(image, **kwargs):
        processed = LoadImage()(image)
        calls.append(processed)
        # Red/blue are intentionally unequal; an RGB input fails this assertion.
        np.testing.assert_array_equal(processed[0, 0], [83, 17, 241])
        assert processed.dtype == np.uint8 and processed.flags.c_contiguous
        found = not retry or len(calls) > 1
        return SimpleNamespace(
            boxes=[((4, 4), (12, 4), (12, 12), (4, 12))] if found else [],
            txts=["colour"] if found else [], scores=[.99] if found else [],
        )

    monkeypatch.setattr(rapidocr, "RapidOCR", lambda **kwargs: backend)
    image = QImage(80, 60, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(241, 17, 83))
    settings = Settings(source_language="en")
    if native:
        frame = QPixmap.fromImage(image)
        capture = DesktopCapture(QPixmap(40, 30), QRect(-40, 0, 40, 30), (
            ScreenCapture(frame, QRect(-40, 0, 40, 30)),
        ))
        task = NativeOcrTask(capture, QRect(0, 0, 40, 30), settings)
    else:
        task = OcrTask(image, settings, retry_image=image, retry_offset=QPoint(), selection_size=QSize(80, 60))
    results, errors = [], []
    task.signals.result.connect(results.append)
    task.signals.error.connect(errors.append)
    task.run()
    assert not errors
    assert [line.text for line in results[0]] == ["colour"]
    assert len(calls) == (2 if retry else 1)
    assert calls[0].shape == (60, 80, 3)
    if retry:
        assert calls[1].shape == (120, 160, 3)
