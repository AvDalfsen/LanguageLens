"""Measured OCR settings, kept free of native imports for GUI readiness checks."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OcrSettings:
    det_limit_type: str = "min"
    det_limit_side_len: int = 736
    unclip_ratio: float = 1.6
    det_thresh: float = .3
    box_thresh: float = .5
    dilation: bool = True
    score_mode: str = "fast"
    vertical_padding: bool = True
    width_height_ratio: float = 8
    cls_thresh: float = .9
    use_cls: bool = True
    rec_min_width: int = 320
    text_score: float = .35
    preprocessing: str = "none"

    def parameters(self) -> dict:
        return {"Det.limit_type": self.det_limit_type,
                "Det.limit_side_len": self.det_limit_side_len,
                "Det.unclip_ratio": self.unclip_ratio,
                "Det.thresh": self.det_thresh, "Det.box_thresh": self.box_thresh,
                "Det.use_dilation": self.dilation, "Det.score_mode": self.score_mode,
                "Global.use_preprocess_img": True, "Global.min_side_len": 30,
                "Global.max_side_len": 2000, "Global.min_height": 30,
                "Global.use_vertical_padding": self.vertical_padding,
                "Global.width_height_ratio": self.width_height_ratio,
                "Global.use_cls": self.use_cls, "Cls.cls_thresh": self.cls_thresh,
                "Rec.rec_img_shape": [3, 48, self.rec_min_width],
                "Global.text_score": self.text_score}


DEFAULT_SETTINGS = OcrSettings()

# Filled only from accepted independent-validation results. See
# docs/ocr-joint-selection.md and docs/ocr-settings-selection.md for limits.
SETTINGS_BY_LANGUAGE: dict[str, OcrSettings] = {
    "ar": OcrSettings(),
    "zh": OcrSettings(det_limit_side_len=128, unclip_ratio=1.3, preprocessing="dark-invert"),
    "cs": OcrSettings(det_limit_side_len=256, unclip_ratio=1.0, cls_thresh=0.8),
    "da": OcrSettings(det_limit_side_len=128, unclip_ratio=1.0, det_thresh=0.4),
    "nl": OcrSettings(),
    "en": OcrSettings(det_limit_side_len=64, unclip_ratio=1.0, cls_thresh=0.8),
    "fi": OcrSettings(det_limit_side_len=64, unclip_ratio=1.0),
    "fr": OcrSettings(det_limit_side_len=384),
    "de": OcrSettings(),
    "el": OcrSettings(),
    "hi": OcrSettings(det_limit_side_len=64, unclip_ratio=1.4, det_thresh=0.2,
                      box_thresh=0.45, dilation=False, vertical_padding=False,
                      use_cls=False),
    "hu": OcrSettings(det_limit_side_len=128, unclip_ratio=1.0, det_thresh=0.4, cls_thresh=0.8),
    "it": OcrSettings(det_limit_side_len=128, unclip_ratio=1.0),
    "ja": OcrSettings(),
    "ko": OcrSettings(unclip_ratio=1.0, dilation=False, use_cls=False),
    "nb": OcrSettings(det_limit_side_len=128, unclip_ratio=1.3),
    "pl": OcrSettings(det_limit_side_len=128),
    "pt": OcrSettings(),
    "pb": OcrSettings(),
    "ro": OcrSettings(det_limit_side_len=128, unclip_ratio=1.0, det_thresh=0.4, preprocessing="dark-invert"),
    "ru": OcrSettings(det_limit_side_len=128, unclip_ratio=1.0, use_cls=False, preprocessing='dark-invert'),
    "es": OcrSettings(),
    "sv": OcrSettings(),
    "tr": OcrSettings(det_limit_side_len=64, unclip_ratio=1.3, width_height_ratio=16),
    "uk": OcrSettings(),
}


def settings_for(language: str) -> OcrSettings:
    return SETTINGS_BY_LANGUAGE.get(language, DEFAULT_SETTINGS)


def preprocess_image(image, mode: str):
    """Color-only transforms preserve every source coordinate and image size."""
    if mode == "none":
        return image
    import cv2
    import numpy as np

    if mode == "dark-invert":
        border = np.concatenate((image[0], image[-1], image[:, 0], image[:, -1]))
        return 255 - image if float(np.median(border)) < 128 else image
    if mode == "gray":
        return cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    if mode == "contrast":
        low, high = np.percentile(image, (1, 99))
        if high - low >= 10:
            return np.clip((image.astype(np.float32) - low) * 255 / (high - low), 0, 255).astype(np.uint8)
        return image
    raise ValueError(f"Unknown OCR preprocessing mode: {mode}")
