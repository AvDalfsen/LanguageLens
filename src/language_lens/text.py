"""Offline word segmentation with offsets into the original screenshot text."""
from __future__ import annotations

from functools import lru_cache
from threading import RLock
import unicodedata

import regex


_TOKENIZER_LOCK = RLock()
_WORDS = regex.compile(r"[\p{L}\p{N}][\p{L}\p{M}\p{N}\u200c\u200d]*(?:[’'\-][\p{L}\p{N}][\p{L}\p{M}\p{N}\u200c\u200d]*)*")
_JAPANESE = regex.compile(r"[\p{Han}\p{Hiragana}\p{Katakana}]")
_HAN = regex.compile(r"\p{Han}")


@lru_cache(maxsize=1)
def _japanese_tokenizer():
    from janome.tokenizer import Tokenizer

    return Tokenizer()


@lru_cache(maxsize=1)
def _chinese_tokenizer():
    import jieba

    return jieba.Tokenizer()


def normalize_lookup_word(word: str) -> str:
    """Trim surrounding punctuation, retain case and every combining mark."""
    text = unicodedata.normalize("NFC", word).strip()
    spans = list(_WORDS.finditer(text))
    return text[spans[0].start():spans[-1].end()] if spans else text


def normalized_offsets(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Map NFC characters back to complete grapheme spans in the original text."""
    parts, offsets = [], []
    for match in regex.finditer(r"\X", text):
        part = unicodedata.normalize("NFC", match.group())
        parts.append(part)
        offsets.extend([match.span()] * len(part))
    return "".join(parts), offsets


def word_spans(text: str, source_language: str | None = None):
    """Yield source offsets; dictionary segmentation is selected by source language.

    Tokenizers include their dictionaries in the installed Python packages and
    never fetch a language model at capture time. Mixed Latin words retain the
    same apostrophe/hyphen handling as other source languages.
    """
    for match in _WORDS.finditer(text):
        part, start = match.group(), match.start()
        if source_language == "ja" and _JAPANESE.search(part):
            with _TOKENIZER_LOCK:
                surfaces = list(_japanese_tokenizer().tokenize(part, wakati=True))
            cursor = 0
            for surface in surfaces:
                position = part.find(surface, cursor)
                if position < 0:
                    raise ValueError("Japanese word boundaries do not match the recognized text.")
                for unit in _WORDS.finditer(surface):
                    yield start + position + unit.start(), start + position + unit.end()
                cursor = position + len(surface)
        elif source_language == "zh" and _HAN.search(part):
            with _TOKENIZER_LOCK:
                tokens = list(_chinese_tokenizer().tokenize(part, mode="default"))
            for surface, left, _right in tokens:
                for unit in _WORDS.finditer(surface):
                    yield start + left + unit.start(), start + left + unit.end()
        else:
            yield match.span()
