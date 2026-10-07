"""Windows XP Luna ("Default (blue)") palette, fonts and DPI scaling."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

# --- palette ------------------------------------------------------------------
DIALOG_BG = "#ECE9D8"
PANEL_BG = "#FCFCFE"
WHITE = "#FFFFFF"
TEXT = "#000000"
TEXT_DISABLED = "#ACA899"
TEXT_MUTED = "#6D6D6D"
TEXT_ERROR = "#C00000"
TEXT_OK = "#1E7B1E"
SELECT_BG = "#316AC5"
SELECT_FG = "#FFFFFF"

FIELD_BORDER = "#7F9DB9"
FIELD_BORDER_DISABLED = "#C9C7BA"
FIELD_BG_DISABLED = "#EBEBE4"
FIELD_DROP_HOVER = "#E5A01A"

GROUP_BORDER = "#D0D0BF"
GROUP_CAPTION = "#0046D5"
TAB_BORDER = "#919B9C"
SEPARATOR_DARK = "#ACA899"
SEPARATOR_LIGHT = "#FFFFFF"

# Window frame stripes, outermost first.
FRAME_LEFT = ("#0831D9", "#166AEE", "#0855DD")
FRAME_RIGHT = ("#00138C", "#001EA0", "#003BDA")
FRAME_LEFT_INACTIVE = ("#7B95DD", "#A8BEF0", "#9AB2EA")
FRAME_RIGHT_INACTIVE = ("#5D73B9", "#6E85C8", "#8DA6E6")

TITLE_TEXT = "#FFFFFF"
TITLE_SHADOW = "#0F1089"
TITLE_TEXT_INACTIVE = "#D8E4F8"

# --- scaling & fonts -------------------------------------------------------------
_scale = 1.0
FONT: tkfont.Font
FONT_BOLD: tkfont.Font
FONT_TITLE: tkfont.Font


def scale() -> float:
    return _scale


def px(value: float) -> int:
    """Convert a 96-DPI design pixel value to device pixels."""
    return int(round(value * _scale))


def _family(root: tk.Misc, *candidates: str) -> str:
    available = {f.lower() for f in tkfont.families(root)}
    for name in candidates:
        if name.lower() in available:
            return name
    return "TkDefaultFont"


def init(root: tk.Misc, scale: float | None = None) -> None:
    """Measure the screen DPI (or use ``scale``) and create the shared fonts."""
    global _scale, FONT, FONT_BOLD, FONT_TITLE
    _scale = scale if scale is not None else max(1.0, root.winfo_fpixels("1i") / 96.0)
    body = _family(root, "Tahoma", "Segoe UI", "Verdana", "DejaVu Sans")
    title = _family(root, "Trebuchet MS", "Tahoma", "Segoe UI", "DejaVu Sans")
    FONT = tkfont.Font(root, family=body, size=-px(11))
    FONT_BOLD = tkfont.Font(root, family=body, size=-px(11), weight="bold")
    FONT_TITLE = tkfont.Font(root, family=title, size=-px(13), weight="bold")
    root.option_add("*Font", FONT)
    root.option_add("*Background", DIALOG_BG)
    root.option_add("*selectBackground", SELECT_BG)
    root.option_add("*selectForeground", SELECT_FG)
