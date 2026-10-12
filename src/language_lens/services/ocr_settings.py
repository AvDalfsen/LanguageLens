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
    rec_batch_num: int = 6
    min_side_len: int = 30
    min_height: int = 30
    scale: float = 1
    confidence: float = .45

    def parameters(self) -> dict:
        return {"Det.limit_type": self.det_limit_type,
                "Det.limit_side_len": self.det_limit_side_len,
                "Det.unclip_ratio": self.unclip_ratio,
                "Det.thresh": self.det_thresh, "Det.box_thresh": self.box_thresh,
                "Det.use_dilation": self.dilation, "Det.score_mode": self.score_mode,
                "Global.use_preprocess_img": True, "Global.min_side_len": self.min_side_len,
                "Global.max_side_len": 2000, "Global.min_height": self.min_height,
                "Global.use_vertical_padding": self.vertical_padding,
                "Global.width_height_ratio": self.width_height_ratio,
                "Global.use_cls": self.use_cls, "Cls.cls_thresh": self.cls_thresh,
                "Rec.rec_img_shape": [3, 48, self.rec_min_width],
                "Rec.rec_batch_num": self.rec_batch_num,
                "Global.text_score": self.text_score}


DEFAULT_SETTINGS = OcrSettings()

# Upright screen benchmark adoption. Chinese, Dutch, German and Italian
# retain the existing profiles after final regressions; see docs/ocr-upright-selection.md.
SETTINGS_BY_LANGUAGE: dict[str, OcrSettings] = {
    "ar": OcrSettings(det_limit_side_len=256, unclip_ratio=1.8, vertical_padding=False,
        width_height_ratio=16, use_cls=False, rec_min_width=640, text_score=0.3,
        preprocessing='contrast', scale=2, confidence=0.6),
    "zh": OcrSettings(det_limit_side_len=128, unclip_ratio=1.3, preprocessing='dark-invert'),
    "cs": OcrSettings(det_limit_side_len=64, unclip_ratio=1.8, det_thresh=0.4, box_thresh=0.6,
        vertical_padding=False, width_height_ratio=16, rec_min_width=160, text_score=0.3,
        preprocessing='dark-invert', scale=1.5, rec_batch_num=1),
    "da": OcrSettings(det_limit_side_len=128, unclip_ratio=1.0, det_thresh=0.4, rec_batch_num=1),
    "nl": OcrSettings(),
    "en": OcrSettings(det_limit_side_len=256, unclip_ratio=1.8, det_thresh=0.4, box_thresh=0.6,
        dilation=False, width_height_ratio=16, cls_thresh=0.8, use_cls=False, text_score=0.3,
        preprocessing='gray', confidence=0.6, rec_batch_num=1),
    "fi": OcrSettings(det_limit_type='max', unclip_ratio=1.5, box_thresh=0.6, dilation=False,
        use_cls=False),
    "fr": OcrSettings(det_limit_side_len=384),
    "de": OcrSettings(),
    "el": OcrSettings(),
    "hi": OcrSettings(det_limit_side_len=64, unclip_ratio=1.4, det_thresh=0.2, box_thresh=0.45,
        dilation=False, vertical_padding=False, use_cls=False),
    "hu": OcrSettings(unclip_ratio=1.4, text_score=0.5),
    "it": OcrSettings(det_limit_side_len=128, unclip_ratio=1.0),
    "ja": OcrSettings(det_limit_side_len=128, unclip_ratio=1.5, dilation=False, use_cls=False),
    "ko": OcrSettings(det_limit_side_len=64, unclip_ratio=1.3, det_thresh=0.4, box_thresh=0.6,
        dilation=False, vertical_padding=False, cls_thresh=0.8, use_cls=False, rec_min_width=160,
        text_score=0.3, preprocessing='contrast', scale=1.5, confidence=0.3, min_height=60,
        min_side_len=60),
    "nb": OcrSettings(det_limit_side_len=64, unclip_ratio=2.0, det_thresh=0.2,
        width_height_ratio=16, cls_thresh=0.8, use_cls=False, rec_min_width=640, text_score=0.3,
        confidence=0.6, min_height=60, min_side_len=60),
    "pl": OcrSettings(det_limit_side_len=128),
    "pt": OcrSettings(det_limit_side_len=256, unclip_ratio=1.8, det_thresh=0.4, box_thresh=0.6,
        dilation=False, vertical_padding=False, width_height_ratio=16, use_cls=False,
        text_score=0.3, confidence=0.6),
    "pb": OcrSettings(det_limit_side_len=64, unclip_ratio=1.8, det_thresh=0.4, box_thresh=0.6,
        dilation=False, vertical_padding=False, cls_thresh=0.8, use_cls=False, rec_min_width=160,
        text_score=0.3, scale=2, confidence=0.6, min_height=60, min_side_len=60),
    "ro": OcrSettings(det_limit_type='max', unclip_ratio=1.5, use_cls=False),
    "ru": OcrSettings(preprocessing='dark-invert', scale=2),
    "es": OcrSettings(det_limit_side_len=128, unclip_ratio=1.3, dilation=False, use_cls=False),
    "sv": OcrSettings(det_limit_side_len=256, unclip_ratio=1.3, det_thresh=0.2, box_thresh=0.4,
        vertical_padding=False, width_height_ratio=16, use_cls=False, text_score=0.3,
        preprocessing='gray', scale=2, confidence=0.3),
    "tr": OcrSettings(det_limit_side_len=64, unclip_ratio=1.8, det_thresh=0.2, box_thresh=0.6,
        use_cls=False, rec_min_width=160, text_score=0.3, preprocessing='dark-invert', scale=1.5,
        confidence=0.6),
    "uk": OcrSettings(det_limit_side_len=128, unclip_ratio=1.7, det_thresh=0.4, cls_thresh=0.8,
        use_cls=False, rec_min_width=640, text_score=0.3, preprocessing='contrast', scale=1.5,
        confidence=0.6, min_height=60, min_side_len=60),
}


def settings_for(language: str) -> OcrSettings:
    return SETTINGS_BY_LANGUAGE.get(language, DEFAULT_SETTINGS)


def confidence_for(language: str, user_confidence: float) -> float:
    """Use the measured floor unless the user has customized the global value."""
    return settings_for(language).confidence if user_confidence == .45 else user_confidence


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
