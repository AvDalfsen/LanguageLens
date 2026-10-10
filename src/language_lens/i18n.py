"""Bundled UI translations, independent of OCR and translation models."""
from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
import json
from pathlib import Path
import re
from string import Formatter

UI_LANGUAGES = (
    ("العربية", "ar"), ("中文", "zh"), ("Čeština", "cs"),
    ("Dansk", "da"), ("Nederlands", "nl"), ("English", "en"),
    ("Suomi", "fi"), ("Français", "fr"), ("Deutsch", "de"),
    ("Ελληνικά", "el"), ("हिन्दी", "hi"), ("Magyar", "hu"),
    ("Italiano", "it"), ("日本語", "ja"), ("한국어", "ko"),
    ("Norsk bokmål", "nb"), ("Polski", "pl"),
    ("Português (Portugal)", "pt"), ("Português (Brasil)", "pb"),
    ("Română", "ro"), ("Русский", "ru"), ("Español", "es"),
    ("Svenska", "sv"), ("Türkçe", "tr"), ("Українська", "uk"),
)
_language = "en"
_qt_translator = None
_rendered: OrderedDict = OrderedDict()


@lru_cache(maxsize=1)
def catalogs() -> dict:
    return json.loads((Path(__file__).parent / "data" / "ui-translations.json").read_text(encoding="utf-8"))


def language() -> str:
    return _language


def set_language(code: str) -> None:
    global _language
    _language = code if code in {code for _, code in UI_LANGUAGES} else "en"
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        _install_qt_translator(app)
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if _language == "ar" else Qt.LayoutDirection.LeftToRight)


def tr(source: str, **values) -> str:
    data = catalogs()
    key = data["sources"].get(source)
    translated = source if _language == "en" else data["languages"].get(_language, {}).get(key, source)
    rendered_values = {key: tr_message(value) if key in {"error", "item", "pack"}
                       and isinstance(value, str) else value for key, value in values.items()}
    result = translated.format(**rendered_values) if values else translated
    if key is not None:
        _rendered[(_language, result)] = (source, values)
        _rendered.move_to_end((_language, result))
        while len(_rendered) > 512:
            _rendered.popitem(last=False)
    return result


def _template_pattern(template):
    parts = []
    for literal, field, spec, conversion in Formatter().parse(template):
        parts.append(re.escape(literal))
        if field:
            parts.append(f"(?P<{field}>.+?)")
    return re.compile("".join(parts), re.DOTALL)


@lru_cache(maxsize=1)
def _service_patterns():
    """Match only explicitly catalogued service templates, never user text."""
    sources = [catalogs()["english"][key] for key in catalogs().get("service_templates", [])]
    return [(_template_pattern(source), source) for source in sorted(sources, key=len, reverse=True)]


@lru_cache(maxsize=len(UI_LANGUAGES))
def _ui_patterns(code):
    data = catalogs()
    locale = data["languages"].get(code, data["english"])
    return [(_template_pattern(text), data["english"][key])
            for key, text in sorted(locale.items(), key=lambda item: len(item[1]), reverse=True)
            if any(field for _, field, _, _ in Formatter().parse(text))]


def _source_info(value, previous):
    """Recover a template even after unrelated messages evict its cache entry."""
    cached = _rendered.get((previous, value))
    if cached:
        return cached
    data = catalogs()
    reverse = {text: data["english"][key] for key, text in data["languages"].get(previous, {}).items()}
    if value in reverse:
        return reverse[value], {}
    for pattern, source in _ui_patterns(previous):
        match = pattern.fullmatch(value)
        if match:
            values = match.groupdict()
            for key in ("item", "pack", "error"):
                if key in values:
                    values[key] = reverse.get(values[key], values[key])
            return source, values
    return value, {}


def tr_message(source: str) -> str:
    """Localize UI feedback received from workers; keep unknown diagnostics intact.

    Workers keep English messages for logs. Named values such as file names,
    shortcuts and error details stay intact; known pack names are UI captions.
    """
    if source in catalogs()["sources"]:
        return tr(source)
    for pattern, template in _service_patterns():
        match = pattern.fullmatch(source)
        if match:
            return tr(template, **match.groupdict())
    prefix, separator, detail = source.partition(": ")
    if separator and prefix in catalogs().get("failure_prefixes", []):
        return f"{tr(prefix)}: {tr_message(detail)}"
    return source


def translate_ui(root, previous: str | None = None) -> None:
    """Retranslate controls without recreating widgets or emitting edits.

    Only interface controls are passed here, never OCR text or model results.
    Dynamic messages use tr() when produced. Reverse lookup preserves the
    current state, such as Pause listening rather than the initial Start.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QComboBox, QWidget

    previous = language() if previous is None else previous
    def convert(value):
        source, values = _source_info(value, previous)
        return tr(source, **values)

    for widget in [root, *root.findChildren(QWidget), *root.findChildren(QAction)]:
        if isinstance(widget, QWidget) and widget.isWindow():
            widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft if _language == "ar" else Qt.LayoutDirection.LeftToRight)
        for getter, setter in (("text", "setText"), ("windowTitle", "setWindowTitle"),
                               ("toolTip", "setToolTip"), ("accessibleName", "setAccessibleName"),
                               ("accessibleDescription", "setAccessibleDescription")):
            if hasattr(widget, getter) and hasattr(widget, setter):
                old = getattr(widget, getter)()
                if getter == "toolTip" and hasattr(widget, "_lens_help_source"):
                    from html import escape
                    new = '<div style="max-width: 420px">'+escape(tr(widget._lens_help_source))+'</div>'
                else:
                    original = getattr(widget, "_lens_ui_sources", {}).get(getter)
                    if original and old == original[1]:
                        source, values = original[0]
                        new = tr(source, **values)
                    else:
                        source_info = _source_info(old, previous)
                        if not hasattr(widget, "_lens_ui_sources"):
                            widget._lens_ui_sources = {}
                        new = tr(source_info[0], **source_info[1])
                        widget._lens_ui_sources[getter] = (source_info, new)
                    if original and old == original[1]:
                        widget._lens_ui_sources[getter] = (original[0], new)
                if new != old:
                    getattr(widget, setter)(new)
        if isinstance(widget, QComboBox) and widget.objectName() not in {"uiLanguage", "textLanguage", "targetLanguage"}:
            blocked = widget.blockSignals(True)
            try:
                for index in range(widget.count()):
                    widget.setItemText(index, convert(widget.itemText(index)))
            finally:
                widget.blockSignals(blocked)
    root.setLayoutDirection(Qt.LayoutDirection.RightToLeft if _language == "ar" else Qt.LayoutDirection.LeftToRight)


def question(parent, title: str, message: str, buttons):
    """Translate standard confirmation buttons without changing Qt key names."""
    from PySide6.QtWidgets import QMessageBox
    if _language == "en":
        return QMessageBox.question(parent, title, message, buttons)
    dialog = QMessageBox(QMessageBox.Icon.Question, title, message, buttons, parent)
    for button, caption in ((QMessageBox.StandardButton.Yes, "Yes"),
                            (QMessageBox.StandardButton.No, "No"),
                            (QMessageBox.StandardButton.Cancel, "Cancel")):
        if dialog.button(button):
            dialog.button(button).setText(tr(caption))
    dialog.setDefaultButton(QMessageBox.StandardButton.No)
    dialog.setLayoutDirection(parent.layoutDirection())
    return dialog.exec()


# Qt's built-in button captions otherwise follow the OS rather than UI language.
from PySide6.QtWidgets import QMessageBox as _QtMessageBox


class MessageBox(_QtMessageBox):
    @staticmethod
    def _show(parent, title, text, icon):
        if language() == "en":
            method = { _QtMessageBox.Icon.Warning: _QtMessageBox.warning,
                       _QtMessageBox.Icon.Critical: _QtMessageBox.critical,
                       _QtMessageBox.Icon.Information: _QtMessageBox.information }[icon]
            return method(parent, title, text)
        dialog = _QtMessageBox(icon, title, text, _QtMessageBox.StandardButton.Ok, parent)
        dialog.button(_QtMessageBox.StandardButton.Ok).setText(tr("OK"))
        return dialog.exec()

    @staticmethod
    def warning(parent, title, text):
        return MessageBox._show(parent, title, text, _QtMessageBox.Icon.Warning)

    @staticmethod
    def critical(parent, title, text):
        return MessageBox._show(parent, title, text, _QtMessageBox.Icon.Critical)

    @staticmethod
    def information(parent, title, text):
        return MessageBox._show(parent, title, text, _QtMessageBox.Icon.Information)


from PySide6.QtCore import QTranslator


class _UiTranslator(QTranslator):
    """Only Qt's built-in editing menus; never translate captured text."""
    def translate(self, context, source, disambiguation=None, n=-1):
        if context in {"QLineEdit", "QWidgetTextControl"}:
            caption = {"Undo": "Undo", "Redo": "Redo", "Cut": "Cut",
                       "Copy": "Copy selection", "Paste": "Paste", "Delete": "Delete",
                       "Select All": "Select all", "Copy Link Location": "Copy link address"}.get(source.replace("&", ""))
            if caption:
                return tr(caption)
        # None is Qt's null string. An empty string hides an untranslated label.
        return None


def _install_qt_translator(app):
    global _qt_translator
    if _qt_translator is None:
        _qt_translator = _UiTranslator(app)
    app.removeTranslator(_qt_translator)
    if language() != "en":
        app.installTranslator(_qt_translator)
