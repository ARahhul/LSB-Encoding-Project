"""XP Luna window chrome drawn inside a borderless Tk window."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Sequence

from PIL import Image

from . import skin, winapi
from . import theme as T
from .widgets import ellipsize, photo


class _FrameEdge(tk.Canvas):
    """The 3-stripe blue window border on the left, right or bottom."""

    def __init__(self, master: tk.Misc, side: str) -> None:
        self._side = side
        self._sw = max(1, round(T.scale()))
        thickness = self._sw * 3
        # Tk canvases default to 10cm x 7cm; pin the free dimension to 1px.
        size = {"width": thickness, "height": 1} if side in ("left", "right") else {"height": thickness, "width": 1}
        super().__init__(master, highlightthickness=0, bd=0, bg=T.FRAME_RIGHT[0], **size)
        self._active = True
        self.bind("<Configure>", lambda e: self._redraw())

    def set_active(self, active: bool) -> None:
        self._active = active
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        w, h, sw = self.winfo_width(), self.winfo_height(), self._sw
        left = T.FRAME_LEFT if self._active else T.FRAME_LEFT_INACTIVE
        right = T.FRAME_RIGHT if self._active else T.FRAME_RIGHT_INACTIVE
        if self._side == "left":
            for i, c in enumerate(left):
                self.create_rectangle(i * sw, 0, (i + 1) * sw, h, fill=c, outline="")
        elif self._side == "right":
            for i, c in enumerate(right):
                self.create_rectangle(w - (i + 1) * sw, 0, w - i * sw, h, fill=c, outline="")
        else:
            for i, c in enumerate(right):
                self.create_rectangle(0, h - (i + 1) * sw, w, h - i * sw, fill=c, outline="")
            for i, c in enumerate(left):  # left stripes run down into the corner
                self.create_rectangle(i * sw, 0, (i + 1) * sw, h - i * sw, fill=c, outline="")


class XPChrome:
    """Title bar, caption buttons and frame around ``self.body``.

    ``buttons`` lists caption buttons left to right: "help", "minimize", "close".
    """

    def __init__(self, win: tk.Tk | tk.Toplevel, title: str, *, icon: Image.Image | None,
                 buttons: Sequence[str] = ("minimize", "close"),
                 on_close: Callable[[], None], on_help: Callable[[], None] | None = None) -> None:
        self.win = win
        self._title = title
        self._icon = photo(icon) if icon is not None else None
        self._buttons = list(buttons)
        self._actions = {"close": on_close, "minimize": lambda: winapi.minimize(win), "help": on_help}
        self._active = True
        self._hot: str | None = None
        self._down: str | None = None
        self._drag: tuple[int, int] | None = None
        self._size = (0, 0)
        self._h = T.px(30)
        self._btn = T.px(21)

        win.configure(bg=T.FRAME_RIGHT[0])
        self.titlebar = tk.Canvas(win, width=1, height=self._h, highlightthickness=0, bd=0, bg="#0053EE")
        self._edges = [_FrameEdge(win, "left"), _FrameEdge(win, "right"), _FrameEdge(win, "bottom")]
        self.body = tk.Frame(win, bg=T.DIALOG_BG)

        self.titlebar.grid(row=0, column=0, columnspan=3, sticky="ew")
        self._edges[0].grid(row=1, column=0, sticky="ns")
        self.body.grid(row=1, column=1, sticky="nsew")
        self._edges[1].grid(row=1, column=2, sticky="ns")
        self._edges[2].grid(row=2, column=0, columnspan=3, sticky="ew")
        win.grid_columnconfigure(1, weight=1)
        win.grid_rowconfigure(1, weight=1)

        tb = self.titlebar
        tb.bind("<Configure>", lambda e: self._redraw())
        tb.bind("<Motion>", self._on_motion)
        tb.bind("<Leave>", lambda e: self._set_hot(None))
        tb.bind("<ButtonPress-1>", self._on_press)
        tb.bind("<B1-Motion>", self._on_drag)
        tb.bind("<ButtonRelease-1>", self._on_release)
        win.bind("<Configure>", self._on_configure, add="+")
        win.bind("<FocusIn>", lambda e: win.after_idle(self._refresh_active), add="+")
        win.bind("<FocusOut>", lambda e: win.after_idle(self._refresh_active), add="+")

    # ----------------------------------------------------------------- state
    def set_title(self, title: str) -> None:
        self._title = title
        self._redraw()

    def _refresh_active(self) -> None:
        try:
            focus = self.win.focus_get()
        except (KeyError, tk.TclError):
            focus = None
        active = focus is not None and focus.winfo_toplevel() is self.win
        if active != self._active:
            self._active = active
            for edge in self._edges:
                edge.set_active(active)
            self._redraw()

    def _on_configure(self, event) -> None:
        if event.widget is not self.win:
            return
        size = (event.width, event.height)
        if size != self._size:
            self._size = size
            winapi.round_top_corners(self.win, T.px(7))

    # ---------------------------------------------------------- caption bits
    def _button_boxes(self) -> dict[str, tuple[int, int]]:
        w = self.titlebar.winfo_width()
        right = w - max(1, round(T.scale())) * 3 - T.px(3)
        y = (self._h - self._btn) // 2 + T.px(1)
        boxes = {}
        for kind in reversed(self._buttons):
            right -= self._btn
            boxes[kind] = (right, y)
            right -= T.px(2)
        return boxes

    def _button_at(self, x: int, y: int) -> str | None:
        for kind, (bx, by) in self._button_boxes().items():
            if bx <= x < bx + self._btn and by <= y < by + self._btn:
                return kind
        return None

    def _redraw(self) -> None:
        tb = self.titlebar
        w = tb.winfo_width()
        if w <= 1:
            return
        tb.delete("all")
        self._bg_img = photo(skin.titlebar(w, self._h, self._active, T.scale()))
        tb.create_image(0, 0, image=self._bg_img, anchor="nw")
        x = T.px(7)
        cy = self._h // 2 + T.px(1)
        if self._icon is not None:
            tb.create_image(x, cy, image=self._icon, anchor="w")
            x += self._icon.width() + T.px(5)
        boxes = self._button_boxes()
        text_room = min((bx for bx, _ in boxes.values()), default=w) - x - T.px(6)
        text = ellipsize(self._title, T.FONT_TITLE, text_room)
        if self._active:
            tb.create_text(x + 1, cy + 1, text=text, anchor="w", font=T.FONT_TITLE, fill=T.TITLE_SHADOW)
        tb.create_text(x, cy, text=text, anchor="w", font=T.FONT_TITLE,
                       fill=T.TITLE_TEXT if self._active else T.TITLE_TEXT_INACTIVE)
        self._btn_imgs = []
        for kind, (bx, by) in boxes.items():
            if self._down == kind and self._hot == kind:
                state = "pressed"
            elif self._hot == kind:
                state = "hover"
            else:
                state = "normal"
            img = photo(skin.caption_button(self._btn, kind, state, self._active, T.scale()))
            self._btn_imgs.append(img)
            tb.create_image(bx, by, image=img, anchor="nw")

    def _set_hot(self, kind: str | None) -> None:
        if kind != self._hot:
            self._hot = kind
            self._redraw()

    # ------------------------------------------------------------ mouse
    def _on_motion(self, event) -> None:
        if self._drag is None:
            self._set_hot(self._button_at(event.x, event.y))

    def _on_press(self, event) -> None:
        kind = self._button_at(event.x, event.y)
        if kind:
            self._down = kind
            self._hot = kind
            self._redraw()
        else:
            self._drag = (event.x_root - self.win.winfo_x(), event.y_root - self.win.winfo_y())

    def _on_drag(self, event) -> None:
        if self._drag is not None:
            dx, dy = self._drag
            self.win.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
        elif self._down:
            self._set_hot(self._button_at(event.x, event.y))

    def _on_release(self, event) -> None:
        self._drag = None
        kind = self._down
        self._down = None
        hit = kind is not None and self._button_at(event.x, event.y) == kind
        self._hot = self._button_at(event.x, event.y)
        self._redraw()
        if hit:
            action = self._actions.get(kind)
            if action:
                action()
