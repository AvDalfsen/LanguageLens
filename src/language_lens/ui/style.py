from language_lens.i18n import ui_text
from PySide6.QtWidgets import QProxyStyle, QStyle


class LensStyle(QProxyStyle):
    """Keep platform behavior with intentional, readable hover help."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return 600
        return super().styleHint(hint, option, widget, returnData)


def help_markup(text: str) -> str:
    """Short hover help; the complete explanation is available to accessibility."""
    from html import escape
    import re
    first = re.split(r"(?<=[。！？؟])|(?<=[.!?])\s+", str(text), maxsplit=1)[0]
    return '<div style="max-width: 420px">' + escape(first) + '</div>'


def set_help(widget, text: str) -> None:

    from language_lens.i18n import tr
    widget._lens_help_source = text
    ui_text(widget, help_markup(tr(text)), property="toolTip")
    ui_text(widget, tr(text), property="accessibleDescription")
    widget.setToolTipDuration(10_000)
