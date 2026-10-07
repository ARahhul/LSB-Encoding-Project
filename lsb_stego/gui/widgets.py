"""Luna-skinned Tk widgets. Faces come from :mod:`skin`; behaviour is Tk."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

from PIL import Image, ImageDraw, ImageOps, ImageTk

from . import icons, skin
from . import theme as T

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:  # pragma: no cover - optional dependency
    DND_FILES = None
    HAS_DND = False

_photos: dict[int, tuple[Image.Image, ImageTk.PhotoImage]] = {}


def photo(img: Image.Image, *, cache: bool = True) -> ImageTk.PhotoImage:
    """PhotoImage for a Pillow image; cached images are converted once."""
    if not cache:
        return ImageTk.PhotoImage(img)
    entry = _photos.get(id(img))
    if entry is None or entry[0] is not img:
        entry = (img, ImageTk.PhotoImage(img))
        _photos[id(img)] = entry
    return entry[1]


def ellipsize(text: str, font: tkfont.Font, max_px: int, *, middle: bool = False) -> str:
    """Shorten ``text`` with an ellipsis so it fits ``max_px``."""
    if max_px <= 0 or font.measure(text) <= max_px:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if middle:
            head, tail = text[: (mid + 1) // 2], text[len(text) - mid // 2:] if mid // 2 else ""
            candidate = head + ell + tail
        else:
            candidate = text[:mid] + ell
        if font.measure(candidate) <= max_px:
            lo = mid
        else:
            hi = mid - 1
    if middle:
        return text[: (lo + 1) // 2] + ell + (text[len(text) - lo // 2:] if lo // 2 else "")
    return text[:lo] + ell


def label(master: tk.Misc, text: str = "", *, fg: str = T.TEXT, font=None, **kw) -> tk.Label:
    return tk.Label(master, text=text, fg=fg, bg=master.cget("bg"), font=font or T.FONT,
                    bd=0, padx=0, pady=0, **kw)


def select_all_bindings(widget: tk.Entry | tk.Text) -> None:
    def select_all(_event=None):
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "end-1c")
        else:
            widget.select_range(0, "end")
            widget.icursor("end")
        return "break"
    widget.bind("<Control-a>", select_all)
    widget.bind("<Control-A>", select_all)


def enable_file_drop(widget: tk.Misc, on_drop: Callable[[list[str]], None],
                     on_hover: Callable[[bool], None] | None = None) -> bool:
    """Accept files dropped from Explorer onto ``widget`` and its children."""
    if not HAS_DND:
        return False

    def enter(event):
        if on_hover:
            on_hover(True)
        return event.action

    def leave(event):
        if on_hover:
            on_hover(False)
        return event.action

    def drop(event):
        if on_hover:
            on_hover(False)
        paths = [p for p in widget.tk.splitlist(event.data) if p]
        if paths:
            widget.after_idle(on_drop, paths)
        return event.action

    stack = [widget]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            w.drop_target_register(DND_FILES)
        except (tk.TclError, AttributeError):
            return False
        w.dnd_bind("<<DropEnter>>", enter)
        w.dnd_bind("<<DropPosition>>", lambda e: e.action)
        w.dnd_bind("<<DropLeave>>", leave)
        w.dnd_bind("<<Drop>>", drop)
    return True


# ------------------------------------------------------------------- button

class XPButton(tk.Canvas):
    """XP push button: 75x23 minimum, hover/focus glow, default ring."""

    def __init__(self, master: tk.Misc, text: str = "", command: Callable[[], None] | None = None,
                 *, width: int = 75, height: int = 23, default: bool = False) -> None:
        self._bg = master.cget("bg")
        self._text = text
        self._command = command
        self._default = default
        self._enabled = True
        self._hover = self._pressed = self._focused = self._key_down = False
        self._min_w = width
        self._bw = max(T.px(width), T.FONT.measure(text) + T.px(18))
        self._bh = T.px(height)
        super().__init__(master, width=self._bw, height=self._bh, bg=self._bg,
                         highlightthickness=0, bd=0, takefocus=1)
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", lambda e: self._set(focused=True))
        self.bind("<FocusOut>", lambda e: self._set(focused=False, key_down=False))
        self.bind("<KeyPress-space>", lambda e: self._set(key_down=True))
        self.bind("<KeyRelease-space>", self._on_space_release)
        self.bind("<Return>", lambda e: (self.invoke(), "break")[1])
        self._redraw()

    # public API
    def invoke(self) -> None:
        if self._enabled and self._command:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self._enabled:
            self._enabled = enabled
            self.configure(takefocus=1 if enabled else 0)
            self._pressed = self._key_down = False
            self._redraw()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_text(self, text: str) -> None:
        self._text = text
        self._bw = max(T.px(self._min_w), T.FONT.measure(text) + T.px(18))
        self.configure(width=self._bw)
        self._redraw()

    def set_default(self, default: bool) -> None:
        self._default = default
        self._redraw()

    # internals
    def _set(self, **changes) -> None:
        for key, value in changes.items():
            setattr(self, "_" + key, value)
        self._redraw()

    def _on_press(self, _event) -> None:
        if self._enabled:
            self.focus_set()
            self._set(pressed=True)

    def _on_release(self, _event) -> None:
        fire = self._enabled and self._pressed and self._hover
        self._set(pressed=False)
        if fire:
            self.invoke()

    def _on_space_release(self, _event) -> None:
        if self._key_down:
            self._set(key_down=False)
            self.invoke()

    def _redraw(self) -> None:
        if not self._enabled:
            state, ring = "disabled", None
        else:
            down = (self._pressed and self._hover) or self._key_down
            state = "pressed" if down else "normal"
            ring = "hover" if self._hover else ("focus" if self._focused or self._default else None)
        face = photo(skin.button(self._bw, self._bh, state, ring, self._bg, T.scale()))
        self.delete("all")
        self.create_image(0, 0, image=face, anchor="nw")
        shift = 1 if state == "pressed" else 0
        self.create_text(self._bw // 2 + shift, self._bh // 2 + shift, text=self._text, font=T.FONT,
                         fill=T.TEXT_DISABLED if not self._enabled else T.TEXT)
        if self._focused and self._enabled:
            m = T.px(4)
            self.create_rectangle(m, m, self._bw - m - 1, self._bh - m - 1, outline="#000000", dash=(1, 1))


# ----------------------------------------------------------- check and radio

class _Toggle(tk.Canvas):
    _sprite: Callable[..., Image.Image]

    def __init__(self, master: tk.Misc, text: str, variable: tk.Variable,
                 command: Callable[[], None] | None = None) -> None:
        self._bg = master.cget("bg")
        self._text = text
        self._var = variable
        self._command = command
        self._enabled = True
        self._hover = self._pressed = self._focused = False
        self._box = T.px(13)
        self._gap = T.px(6)
        self._tw = T.FONT.measure(text)
        self._bh = max(self._box, T.FONT.metrics("linespace")) + T.px(4)
        w = self._box + self._gap + self._tw + T.px(3)
        super().__init__(master, width=w, height=self._bh, bg=self._bg, highlightthickness=0, bd=0, takefocus=1)
        self._trace = variable.trace_add("write", lambda *_: self._redraw())
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<FocusIn>", lambda e: self._set(focused=True))
        self.bind("<FocusOut>", lambda e: self._set(focused=False))
        self.bind("<KeyPress-space>", lambda e: self._set(pressed=True))
        self.bind("<KeyRelease-space>", self._on_space)
        self._redraw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(takefocus=1 if enabled else 0)
        self._redraw()

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            try:
                self._var.trace_remove("write", self._trace)
            except tk.TclError:
                pass

    def _set(self, **changes) -> None:
        for key, value in changes.items():
            setattr(self, "_" + key, value)
        self._redraw()

    def _on_press(self, _event) -> None:
        if self._enabled:
            self.focus_set()
            self._set(pressed=True)

    def _on_release(self, _event) -> None:
        fire = self._enabled and self._pressed and self._hover
        self._set(pressed=False)
        if fire:
            self._activate()

    def _on_space(self, _event) -> None:
        if self._pressed and self._enabled:
            self._set(pressed=False)
            self._activate()

    def _activate(self) -> None:
        raise NotImplementedError

    def _checked(self) -> bool:
        raise NotImplementedError

    def _redraw(self) -> None:
        if not self._enabled:
            state = "disabled"
        elif self._pressed and (self._hover or self._focused):
            state = "pressed"
        elif self._hover:
            state = "hover"
        else:
            state = "normal"
        sprite = photo(type(self)._sprite(self._box, self._checked(), state, T.scale()))
        self.delete("all")
        cy = self._bh // 2
        self.create_image(0, cy, image=sprite, anchor="w")
        x = self._box + self._gap
        self.create_text(x, cy, text=self._text, anchor="w", font=T.FONT,
                         fill=T.TEXT if self._enabled else T.TEXT_DISABLED)
        if self._focused and self._enabled:
            self.create_rectangle(x - T.px(2), 1, x + self._tw + T.px(1), self._bh - 2,
                                  outline="#000000", dash=(1, 1))


class XPCheck(_Toggle):
    _sprite = staticmethod(skin.checkbox)

    def _checked(self) -> bool:
        try:
            return bool(self._var.get())
        except tk.TclError:
            return False

    def _activate(self) -> None:
        self._var.set(not self._checked())
        if self._command:
            self._command()


class XPRadio(_Toggle):
    _sprite = staticmethod(skin.radio)

    def __init__(self, master, text, variable, value: str, command=None) -> None:
        self._value = value
        super().__init__(master, text, variable, command)

    def _checked(self) -> bool:
        return self._var.get() == self._value

    def _activate(self) -> None:
        if not self._checked():
            self._var.set(self._value)
            if self._command:
                self._command()


# -------------------------------------------------------------------- entry

class XPEntry(tk.Frame):
    """Single-line text box with XP's flat #7F9DB9 border."""

    def __init__(self, master: tk.Misc, textvariable: tk.Variable | None = None, *,
                 show: str = "", width: int = 20) -> None:
        super().__init__(master, bg=T.FIELD_BORDER, bd=0, highlightthickness=0)
        self.entry = tk.Entry(
            self, textvariable=textvariable, show=show, width=width, relief="flat", bd=T.px(2),
            highlightthickness=0, bg=T.WHITE, fg=T.TEXT, font=T.FONT, insertwidth=max(1, T.px(1)),
            disabledbackground=T.FIELD_BG_DISABLED, disabledforeground=T.TEXT_DISABLED,
            readonlybackground=T.WHITE, selectbackground=T.SELECT_BG, selectforeground=T.SELECT_FG)
        self.entry.pack(fill="both", expand=True, padx=1, pady=1, ipady=T.px(1))
        select_all_bindings(self.entry)

    def set_enabled(self, enabled: bool) -> None:
        self.entry.configure(state="normal" if enabled else "disabled")
        self.configure(bg=T.FIELD_BORDER if enabled else T.FIELD_BORDER_DISABLED)

    def get(self) -> str:
        return self.entry.get()

    def focus_set(self) -> None:
        self.entry.focus_set()

    def bind_entry(self, sequence: str, func) -> None:
        self.entry.bind(sequence, func)


# ---------------------------------------------------------------- scrollbar

class XPScrollbar(tk.Canvas):
    """Vertical Luna scrollbar speaking Tk's scrollbar protocol."""

    def __init__(self, master: tk.Misc, command: Callable[..., object] | None = None) -> None:
        self._size = T.px(17)
        super().__init__(master, width=self._size, height=self._size * 3, highlightthickness=0, bd=0,
                         bg="#F3F1EC", takefocus=0)
        self._command = command
        self._lo, self._hi = 0.0, 1.0
        self._hot: str | None = None
        self._down: str | None = None
        self._drag: tuple[int, float] | None = None
        self._repeat: str | None = None
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: self._set_hot(None))
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set(self, lo, hi) -> None:
        self._lo, self._hi = float(lo), float(hi)
        self._redraw()

    def _scrollable(self) -> bool:
        return not (self._lo <= 0.0 and self._hi >= 1.0)

    def _geometry(self) -> tuple[int, int, int, int]:
        """(track_top, track_len, thumb_top, thumb_len)."""
        a = self._size
        h = max(self.winfo_height(), a * 2)
        track = max(0, h - 2 * a)
        span = max(0.0, min(1.0, self._hi - self._lo))
        thumb = max(min(T.px(10), track), round(track * span))
        free = track - thumb
        movable = 1.0 - span
        top = a + (round(free * self._lo / movable) if movable > 0 else 0)
        return a, track, top, thumb

    def _part_at(self, y: int) -> str:
        a, track, top, thumb = self._geometry()
        if y < a:
            return "up"
        if y >= a + track:
            return "down"
        if not self._scrollable():
            return "track"
        if y < top:
            return "above"
        if y >= top + thumb:
            return "below"
        return "thumb"

    def _redraw(self) -> None:
        self.delete("all")
        w, a = self._size, self._size
        h = self.winfo_height()
        if h <= 1:
            return
        enabled = self._scrollable()
        _, track, top, thumb = self._geometry()
        self._track_img = photo(skin.scroll_track(w, max(1, track)))
        self.create_image(0, a, image=self._track_img, anchor="nw")

        def state(part: str) -> str:
            if not enabled:
                return "disabled"
            if self._down == part and self._hot == part:
                return "pressed"
            return "hover" if self._hot == part else "normal"

        self._up_img = photo(skin.scroll_arrow(a, True, state("up"), T.scale()))
        self._dn_img = photo(skin.scroll_arrow(a, False, state("down"), T.scale()))
        self.create_image(0, 0, image=self._up_img, anchor="nw")
        self.create_image(0, h - a, image=self._dn_img, anchor="nw")
        if enabled and thumb > 0:
            self._thumb_img = photo(skin.scroll_thumb(w, thumb, state("thumb"), T.scale()))
            self.create_image(0, top, image=self._thumb_img, anchor="nw")

    def _set_hot(self, part: str | None) -> None:
        if part != self._hot:
            self._hot = part
            self._redraw()

    def _on_motion(self, event) -> None:
        if self._drag is None:
            self._set_hot(self._part_at(event.y))

    def _call(self, *args) -> None:
        if self._command:
            self._command(*args)

    def _step(self, part: str) -> None:
        if part == "up":
            self._call("scroll", -1, "units")
        elif part == "down":
            self._call("scroll", 1, "units")
        elif part == "above":
            self._call("scroll", -1, "pages")
        elif part == "below":
            self._call("scroll", 1, "pages")

    def _auto_repeat(self, part: str, delay: int) -> None:
        if self._down != part:
            return
        if part in ("above", "below"):
            pointer_y = self.winfo_pointery() - self.winfo_rooty()
            if self._part_at(pointer_y) != part:
                return
        self._step(part)
        self._repeat = self.after(delay, self._auto_repeat, part, 40)

    def _on_press(self, event) -> None:
        if not self._scrollable():
            return
        part = self._part_at(event.y)
        self._down = part
        self._hot = part
        if part == "thumb":
            _, _, top, _ = self._geometry()
            self._drag = (event.y - top, self._lo)
        elif part != "track":
            self._step(part)
            self._repeat = self.after(350, self._auto_repeat, part, 40)
        self._redraw()

    def _on_drag(self, event) -> None:
        if self._drag is None:
            return
        a, track, _, thumb = self._geometry()
        free = track - thumb
        if free <= 0:
            return
        offset, _ = self._drag
        fraction = (event.y - offset - a) / free * (1.0 - (self._hi - self._lo))
        self._call("moveto", max(0.0, fraction))

    def _on_release(self, event) -> None:
        if self._repeat:
            self.after_cancel(self._repeat)
            self._repeat = None
        self._down = None
        self._drag = None
        self._hot = self._part_at(event.y) if 0 <= event.x < self._size else None
        self._redraw()


# --------------------------------------------------------------- multi-line

class XPText(tk.Frame):
    """Multi-line text box with a Luna scrollbar."""

    _NAV_KEYS = {"Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next", "Tab",
                 "Shift_L", "Shift_R", "Control_L", "Control_R", "ISO_Left_Tab"}

    def __init__(self, master: tk.Misc, *, height: int = 6, readonly: bool = False) -> None:
        super().__init__(master, bg=T.FIELD_BORDER, bd=0, highlightthickness=0)
        self._readonly = readonly
        self._inner = tk.Frame(self, bg=T.WHITE)
        self._inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.text = tk.Text(
            self._inner, height=height, width=10, wrap="word", relief="flat", bd=0, highlightthickness=0,
            padx=T.px(3), pady=T.px(2), font=T.FONT, bg=T.WHITE, fg=T.TEXT, undo=True,
            insertwidth=max(1, T.px(1)), selectbackground=T.SELECT_BG, selectforeground=T.SELECT_FG,
            inactiveselectbackground="#C5C5C5")
        self.scrollbar = XPScrollbar(self._inner, command=self.text.yview)
        self.text.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        select_all_bindings(self.text)
        if readonly:
            self.text.bind("<Key>", self._block_edits)
            for seq in ("<<Paste>>", "<<Cut>>", "<<Clear>>", "<<Undo>>", "<<Redo>>"):
                self.text.bind(seq, lambda e: "break")
        # Tab moves focus like every other control instead of inserting a tab.
        self.text.bind("<Tab>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])
        self.text.bind("<Shift-Tab>", lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[1])

    def _block_edits(self, event):
        ctrl = bool(event.state & 0x4)
        if event.keysym in self._NAV_KEYS or (ctrl and event.keysym.lower() in {"c", "a", "insert"}):
            return None
        return "break"

    def get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set_text(self, value: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.edit_reset()
        self.text.mark_set("insert", "1.0")
        self.text.see("1.0")

    def set_enabled(self, enabled: bool) -> None:
        bg = T.WHITE if enabled else T.FIELD_BG_DISABLED
        self.text.configure(state="normal" if enabled else "disabled", bg=bg,
                            fg=T.TEXT if enabled else T.TEXT_DISABLED)
        self._inner.configure(bg=bg)
        self.configure(bg=T.FIELD_BORDER if enabled else T.FIELD_BORDER_DISABLED)


# --------------------------------------------------------------- group box

class XPGroupBox(tk.Frame):
    """Rounded #D0D0BF frame with a blue caption; put children in ``.body``."""

    def __init__(self, master: tk.Misc, text: str, *, padding: int = 8) -> None:
        bg = master.cget("bg")
        super().__init__(master, bg=bg)
        self._bg = bg
        self._canvas = tk.Canvas(self, width=1, height=1, bg=bg, highlightthickness=0, bd=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._caption = tk.Label(self, text=text, bg=bg, fg=T.GROUP_CAPTION, font=T.FONT,
                                 padx=T.px(2), pady=0, bd=0)
        self._cap_h = self._caption.winfo_reqheight()
        self._caption.place(x=T.px(6), y=0)
        self.body = tk.Frame(self, bg=bg)
        self.body.grid(row=0, column=0, sticky="nsew", padx=T.px(padding),
                       pady=(self._cap_h + T.px(4), T.px(padding)))
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return
        self._img = photo(skin.group_border(w, h, self._cap_h // 2, self._bg, T.scale()))
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, image=self._img, anchor="nw")


class Separator(tk.Canvas):
    """Etched horizontal line."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, width=1, height=2, bg=master.cget("bg"), highlightthickness=0, bd=0)
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None) -> None:
        w = self.winfo_width()
        self.delete("all")
        self.create_line(0, 0, w, 0, fill=T.SEPARATOR_DARK)
        self.create_line(0, 1, w, 1, fill=T.SEPARATOR_LIGHT)


# ---------------------------------------------------------------------- tabs

class XPTabs(tk.Frame):
    """Property-sheet tabs. Pages are stacked so the panel never resizes."""

    def __init__(self, master: tk.Misc, on_change: Callable[[int], None] | None = None) -> None:
        bg = master.cget("bg")
        super().__init__(master, bg=bg)
        self._bg = bg
        self._on_change = on_change
        self._titles: list[str] = []
        self.pages: list[tk.Frame] = []
        self._current = 0
        self._hover: int | None = None
        self._focused = False
        self._tab_h = T.px(20)
        self._lift = T.px(2)
        self._header_h = self._tab_h + self._lift + 1
        self.header = tk.Canvas(self, width=1, height=self._header_h, bg=bg, highlightthickness=0, bd=0,
                                takefocus=1)
        self.header.grid(row=0, column=0, sticky="ew")
        border = tk.Frame(self, bg=T.TAB_BORDER)
        border.grid(row=1, column=0, sticky="nsew")
        self.panel = tk.Frame(border, bg=T.PANEL_BG)
        self.panel.pack(fill="both", expand=True, padx=1, pady=(0, 1))
        self.panel.grid_columnconfigure(0, weight=1)
        self.panel.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.header.bind("<Configure>", lambda e: self._redraw())
        self.header.bind("<Motion>", self._on_motion)
        self.header.bind("<Leave>", lambda e: self._set_hover(None))
        self.header.bind("<ButtonPress-1>", self._on_click)
        self.header.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.header.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.header.bind("<Left>", lambda e: self.select(self._current - 1))
        self.header.bind("<Right>", lambda e: self.select(self._current + 1))

    @property
    def current(self) -> int:
        return self._current

    def add(self, title: str) -> tk.Frame:
        page = tk.Frame(self.panel, bg=T.PANEL_BG)
        page.grid(row=0, column=0, sticky="nsew")
        self._titles.append(title)
        self.pages.append(page)
        self.pages[self._current].tkraise()
        self._redraw()
        return page

    def select(self, index: int) -> None:
        if not self.pages:
            return
        index %= len(self.pages)
        if index == self._current:
            return
        self._current = index
        self.pages[index].tkraise()
        self._redraw()
        if self._on_change:
            self._on_change(index)

    def _tab_boxes(self) -> list[tuple[int, int]]:
        boxes, x = [], T.px(2)
        for title in self._titles:
            w = T.FONT.measure(title) + T.px(18)
            boxes.append((x, w))
            x += w
        return boxes

    def _index_at(self, x: int, y: int) -> int | None:
        for i, (bx, bw) in enumerate(self._tab_boxes()):
            if i == self._current:
                if bx - self._lift <= x < bx + bw + self._lift:
                    return i
            elif bx <= x < bx + bw and y >= self._lift:
                return i
        return None

    def _on_motion(self, event) -> None:
        self._set_hover(self._index_at(event.x, event.y))

    def _set_hover(self, index: int | None) -> None:
        if index != self._hover:
            self._hover = index
            self._redraw()

    def _set_focus(self, focused: bool) -> None:
        self._focused = focused
        self._redraw()

    def _on_click(self, event) -> None:
        index = self._index_at(event.x, event.y)
        if index is not None:
            self.select(index)

    def _redraw(self) -> None:
        c = self.header
        c.delete("all")
        width = max(c.winfo_width(), 1)
        self._imgs = []
        bottom = self._header_h - 1
        boxes = self._tab_boxes()
        for i, (x, w) in enumerate(boxes):
            if i == self._current:
                continue
            img = photo(skin.tab(w, self._tab_h, False, self._hover == i, self._bg, T.PANEL_BG, T.scale()))
            c.create_image(x, self._lift, image=img, anchor="nw")
            c.create_text(x + w // 2, self._lift + self._tab_h // 2 + 1, text=self._titles[i], font=T.FONT, fill=T.TEXT)
        c.create_line(0, bottom, width, bottom, fill=T.TAB_BORDER)
        if boxes:
            x, w = boxes[self._current]
            sw, sh = w + 2 * self._lift, self._tab_h + self._lift + 1
            img = photo(skin.tab(sw, sh, True, False, self._bg, T.PANEL_BG, T.scale()))
            c.create_image(x - self._lift, 0, image=img, anchor="nw")
            cx, cy = x + w // 2, self._tab_h // 2 + T.px(1)
            c.create_text(cx, cy, text=self._titles[self._current], font=T.FONT, fill=T.TEXT)
            if self._focused:
                tw = T.FONT.measure(self._titles[self._current])
                th = T.FONT.metrics("linespace")
                c.create_rectangle(cx - tw // 2 - T.px(2), cy - th // 2, cx + tw // 2 + T.px(2), cy + th // 2,
                                   outline="#000000", dash=(1, 1))


# ------------------------------------------------------------------ progress

class XPProgress(tk.Canvas):
    """Green-block progress bar with an optional marquee (busy) mode."""

    def __init__(self, master: tk.Misc, *, width: int = 200, height: int = 14) -> None:
        self._bg = master.cget("bg")
        super().__init__(master, width=T.px(width), height=T.px(height), bg=self._bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self._fraction = 0.0
        self._color = "green"
        self._marquee: int | None = None
        self._job: str | None = None
        self.bind("<Configure>", lambda e: self._redraw())

    def set(self, fraction: float, color: str = "green") -> None:
        self._fraction, self._color = fraction, color
        self._redraw()

    def start(self) -> None:
        if self._job is None:
            self._marquee = -3
            self._tick()

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self._marquee = None
        self._redraw()

    def _size(self) -> tuple[int, int]:
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            w, h = int(self.cget("width")), int(self.cget("height"))
        return w, h

    def _tick(self) -> None:
        w, h = self._size()
        _, _, inner_w, _, block, step = skin.progress_geometry(w, h, T.scale())
        total = max(1, (inner_w + step - block) // step)
        self._marquee = self._marquee + 1 if self._marquee < total else -3
        self._redraw()
        self._job = self.after(60, self._tick)

    def _redraw(self) -> None:
        w, h = self._size()
        if self._marquee is not None:
            blocks = tuple(range(self._marquee, self._marquee + 3))
            color = "green"
        else:
            blocks = skin.blocks_for(self._fraction, w, h, T.scale())
            color = self._color
        self._img = photo(skin.progress(w, h, blocks, color, self._bg, T.scale()), cache=False)
        self.delete("all")
        self.create_image(0, 0, image=self._img, anchor="nw")


# ----------------------------------------------------------------- drop zone

class ImageDropZone(tk.Canvas):
    """Square thumbnail well: dashed 'drop here' prompt, or the picture."""

    def __init__(self, master: tk.Misc, *, size: int = 92, hint: str = "Drop an image here",
                 on_click: Callable[[], None] | None = None) -> None:
        self._bg = master.cget("bg")
        self._s = T.px(size)
        super().__init__(master, width=self._s, height=self._s, bg=self._bg, highlightthickness=0,
                         bd=0, cursor="hand2", takefocus=0)
        self._hint = hint
        self._image: Image.Image | None = None
        self._thumb: Image.Image | None = None
        self._hover = False
        self._drop_hover = False
        if on_click:
            self.bind("<ButtonRelease-1>", lambda e: on_click())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._redraw()

    def set_image(self, img: Image.Image | None) -> None:
        self._image = img
        self._thumb = None
        if img is not None:
            inner = self._s - 2 * T.px(3)
            self._thumb = ImageOps.contain(img, (inner, inner), Image.Resampling.LANCZOS).convert("RGBA")
        self._redraw()

    def set_drop_hover(self, on: bool) -> None:
        self._drop_hover = on
        self._redraw()

    def _set_hover(self, on: bool) -> None:
        self._hover = on
        self._redraw()

    def _redraw(self) -> None:
        s = self._s
        accent = T.FIELD_DROP_HOVER if (self._drop_hover or self._hover) else T.FIELD_BORDER
        if self._thumb is None:
            base = skin.dashed_border(s, s, accent, T.WHITE, T.px(3), T.scale()).convert("RGBA")
            pic = icons.picture_icon(T.px(40))
            base.alpha_composite(pic, ((s - pic.width) // 2, T.px(12)))
        else:
            base = Image.new("RGBA", (s, s), (255, 255, 255, 255))
            inner = s - 2 * T.px(3)
            board = skin.checkerboard(inner, inner, T.px(6)).convert("RGBA")
            ox = (inner - self._thumb.width) // 2
            oy = (inner - self._thumb.height) // 2
            tile = board.crop((ox, oy, ox + self._thumb.width, oy + self._thumb.height))
            tile.alpha_composite(self._thumb)
            base.paste(tile, (T.px(3) + ox, T.px(3) + oy))
            border = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            bw = max(1, round(T.scale()))
            ImageDraw.Draw(border).rectangle([0, 0, s - 1, s - 1], outline=accent, width=bw)
            base.alpha_composite(border)
        self._img = photo(base, cache=False)
        self.delete("all")
        self.create_image(0, 0, image=self._img, anchor="nw")
        if self._thumb is None:
            self.create_text(s // 2, s - T.px(26), text=self._hint, font=T.FONT, fill=T.TEXT_MUTED,
                             justify="center", width=s - T.px(10))


# ---------------------------------------------------------------- status bar

class XPStatusBar(tk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=T.DIALOG_BG)
        Separator(self).pack(side="top", fill="x")
        row = tk.Frame(self, bg=T.DIALOG_BG)
        row.pack(fill="x", padx=T.px(2), pady=(T.px(2), T.px(2)))
        self._text = tk.StringVar(self, value="Ready")
        self._label = tk.Label(row, textvariable=self._text, anchor="w", bg=T.DIALOG_BG, fg=T.TEXT,
                               font=T.FONT, padx=T.px(4), pady=T.px(1))
        self._label.pack(side="left", fill="x", expand=True)
        self.progress = XPProgress(row, width=110, height=13)

    def set(self, text: str) -> None:
        self._text.set(text)

    def busy(self, on: bool) -> None:
        if on:
            self.progress.pack(side="right", padx=(T.px(4), T.px(2)))
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.pack_forget()
