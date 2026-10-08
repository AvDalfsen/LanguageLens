"""Lens's SBD adapter for Argos 1.11.0, installed before importing its backend.

Argos imports its SBD implementations together, which eagerly imports Stanza.
Supply that small integration surface explicitly so source and frozen workers
use the same local-only MiniSBD implementation without importing Stanza/Torch.
Upstream Argos files and installed distribution metadata are never modified.
"""
from importlib.metadata import version
import sys
from types import ModuleType

from language_lens.services import sentence_models


class ISentenceBoundaryDetectionModel:
    def split_sentences(self, text):
        raise NotImplementedError


class MiniSBDSentencizer(ISentenceBoundaryDetectionModel):
    def __init__(self, pkg):
        self.pkg = pkg

    def split_sentences(self, text):
        return sentence_models.split(text, self.pkg.from_code)


class UnsupportedSentencizer(ISentenceBoundaryDetectionModel):
    def __init__(self, _pkg):
        raise RuntimeError("Language Lens requires its local MiniSBD sentence splitter.")


def install():
    if version("argostranslate") != "1.11.0":
        raise ImportError("The sentence adapter requires Argos Translate 1.11.0.")
    if version("minisbd") != "0.9.5":
        raise ImportError("The sentence adapter requires MiniSBD 0.9.5.")
    import argostranslate
    name = "argostranslate.sbd"
    current = sys.modules.get(name)
    if current is not None:
        if getattr(current, "lens_backend", None) != sentence_models.BACKEND_ID:
            raise ImportError("The Argos backend was loaded before the Lens sentence adapter. Restart the worker.")
        return
    adapter = ModuleType(name, __doc__)
    adapter.lens_backend = sentence_models.BACKEND_ID
    adapter.ISentenceBoundaryDetectionModel = ISentenceBoundaryDetectionModel
    adapter.MiniSBDSentencizer = MiniSBDSentencizer
    # These names are imported by Argos but its selected MINISBD branch never
    # constructs them. Fail explicitly if a future caller changes that policy.
    adapter.StanzaSentencizer = adapter.SpacySentencizerSmall = UnsupportedSentencizer
    sys.modules[name] = adapter
    argostranslate.sbd = adapter
