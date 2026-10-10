from language_lens.i18n import ui_text
from PySide6.QtWidgets import QProxyStyle, QStyle


class LensStyle(QProxyStyle):
    """Keep the platform appearance with near-instant native Qt tooltips."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):  # noqa: N802
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return 50
        return super().styleHint(hint, option, widget, returnData)


def set_help(widget, text: str) -> None:
    """Use readable rich-text wrapping and enough time to read detailed help."""
    from html import escape

    from language_lens.i18n import tr
    widget._lens_help_source = text
    ui_text(widget, f'<div style="max-width: 420px">{escape(tr(text))}</div>', property="toolTip")
    widget.setToolTipDuration(30_000)
