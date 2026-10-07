"""XP-style modal message boxes, drawn with the same chrome as the main window."""

from __future__ import annotations

import sys
import tkinter as tk
from typing import Sequence

from PIL import Image

from . import icons, winapi
from . import theme as T
from .chrome import XPChrome
from .widgets import XPButton, photo

_SOUNDS = {
    "info": "MB_ICONASTERISK",
    "question": "MB_ICONQUESTION",
    "warning": "MB_ICONEXCLAMATION",
    "error": "MB_ICONHAND",
}


def _beep(kind: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import winsound

        winsound.MessageBeep(getattr(winsound, _SOUNDS.get(kind, "MB_OK")))
    except Exception:
        pass


class XPDialog(tk.Toplevel):
    """Borderless modal window owned by ``parent``'s toplevel."""

    def __init__(self, parent: tk.Misc, title: str, *, cancel_value=None) -> None:
        self.owner = parent.winfo_toplevel()
        super().__init__(self.owner)
        self.withdraw()
        self.overrideredirect(True)
        self.result = cancel_value
        self._cancel_value = cancel_value
        try:
            self._prev_focus = self.owner.focus_get()
        except (KeyError, tk.TclError):
            self._prev_focus = None
        self.chrome = XPChrome(self, title, icon=None, buttons=("close",), on_close=self.cancel)
        self.body = self.chrome.body
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())

    def show(self, focus: tk.Misc | None = None):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if self.owner.winfo_viewable():
            x = self.owner.winfo_rootx() + (self.owner.winfo_width() - w) // 2
            y = self.owner.winfo_rooty() + (self.owner.winfo_height() - h) // 3
        else:
            x = (self.winfo_screenwidth() - w) // 2
            y = (self.winfo_screenheight() - h) // 3
        x = max(0, min(x, self.winfo_screenwidth() - w))
        y = max(0, min(y, self.winfo_screenheight() - h))
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()
        winapi.make_borderless(self, taskbar=False, owner=self.owner)
        winapi.bring_to_front(self)
        (focus or self).focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()
        return self.result

    def finish(self, result) -> None:
        self.result = result
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        if self._prev_focus is not None:
            try:
                self._prev_focus.focus_set()
            except tk.TclError:
                pass

    def cancel(self) -> None:
        self.finish(self._cancel_value)


def message(parent: tk.Misc, title: str, text: str, *, kind: str = "info",
            buttons: Sequence[str] = ("OK",), default: int = 0, cancel: str | None = None,
            detail: str | None = None, icon: Image.Image | None = None) -> str | None:
    """Show an XP message box and return the label of the button pressed.

    ``kind`` picks the icon and sound: info | question | warning | error.
    Esc and the close button return ``cancel``.
    """
    dlg = XPDialog(parent, title, cancel_value=cancel)
    body = dlg.body
    pad = T.px(12)

    row = tk.Frame(body, bg=T.DIALOG_BG)
    row.pack(fill="both", expand=True, padx=(pad, pad + T.px(6)), pady=(T.px(14), T.px(12)))
    image = photo(icon if icon is not None else icons.message_icon(kind, T.px(32)))
    tk.Label(row, image=image, bg=T.DIALOG_BG, bd=0).pack(side="left", anchor="n", padx=(0, pad))
    column = tk.Frame(row, bg=T.DIALOG_BG)
    column.pack(side="left", fill="both", expand=True)
    tk.Label(column, text=text, justify="left", anchor="w", wraplength=T.px(330), bg=T.DIALOG_BG,
             fg=T.TEXT, font=T.FONT, bd=0, padx=0, pady=0).pack(anchor="w", pady=(T.px(2), 0))
    if detail:
        tk.Label(column, text=detail, justify="left", anchor="w", wraplength=T.px(330), bg=T.DIALOG_BG,
                 fg=T.TEXT_MUTED, font=T.FONT, bd=0).pack(anchor="w", pady=(T.px(8), 0))
    # Keep very short messages from producing a cramped box.
    tk.Frame(column, width=T.px(200), height=0, bg=T.DIALOG_BG).pack()

    button_row = tk.Frame(body, bg=T.DIALOG_BG)
    button_row.pack(pady=(0, pad))
    widgets = []
    for i, label in enumerate(buttons):
        b = XPButton(button_row, label, command=lambda value=label: dlg.finish(value), default=(i == default))
        b.pack(side="left", padx=T.px(3))
        widgets.append(b)
    dlg.bind("<Return>", lambda e: dlg.finish(buttons[default]))
    _beep(kind)
    return dlg.show(focus=widgets[default] if widgets else None)
