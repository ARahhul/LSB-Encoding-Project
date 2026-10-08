"""Main window: an XP property sheet with Hide and Reveal pages."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageGrab

from .. import __version__, core
from ..errors import (
    CapacityError,
    CorruptDataError,
    NoHiddenDataError,
    PasswordRequiredError,
    StegoError,
    WrongPasswordError,
)
from . import datamap, dialogs, icons, sounds, winapi, widgets
from . import theme as T
from .chrome import XPChrome
from .widgets import (
    ImageDropZone,
    XPButton,
    XPCheck,
    XPEntry,
    XPGroupBox,
    XPProgress,
    XPRadio,
    XPStatusBar,
    XPTabs,
    XPText,
    ellipsize,
    enable_file_drop,
    label,
    photo,
)

APP_NAME = "LSB Steganography"
APP_ID = "LSBSteganography.Desktop.2"
METHOD_NAMES = {"lsb": "LSB", "bpcs": "BPCS"}
MAX_SECRET_FILE = 100 * 1024 * 1024
IMAGE_TYPES = [
    ("Image files", "*.png *.bmp *.tif *.tiff *.webp *.gif *.jpg *.jpeg"),
    ("PNG image", "*.png"),
    ("All files", "*.*"),
]
IMAGE_SUFFIXES = {".png", ".bmp", ".dib", ".tif", ".tiff", ".webp", ".gif", ".jpg", ".jpeg", ".jfif"}
LOSSY_FORMATS = {"JPEG", "MPO", "WEBP"}
LOG_PATH = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LSB Steganography" / "error.log"


# ----------------------------------------------------------------- helpers

def human_size(n: int) -> str:
    if n < 1024:
        return f"{n:,} byte{'s' if n != 1 else ''}"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unit == "GB":
            return f"{n:,.1f} {unit}" if n < 100 else f"{n:,.0f} {unit}"
    return f"{n:,.0f} GB"


def open_folder(path: Path) -> None:
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except OSError:
        pass


def pictures_dir() -> str:
    pictures = Path.home() / "Pictures"
    return str(pictures if pictures.is_dir() else Path.home())


def is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def clipboard_content(*, images_only: bool = True) -> Image.Image | Path | None:
    """A picture, or a file copied in Explorer, currently on the clipboard."""
    try:
        content = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(content, Image.Image):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str) and os.path.isfile(item):
                path = Path(item)
                if is_image_path(path) or not images_only:
                    return path
    return None


@dataclass
class LoadedImage:
    """What the UI needs to show an image without keeping it all in memory."""
    source: Path | Image.Image
    name: str
    width: int
    height: int
    fmt: str
    thumb: Image.Image
    has_data: bool
    bpcs_capacity: int = 0          # BPCS room depends on the picture's content
    data_method: str | None = None  # "lsb" or "bpcs" when has_data


    @property
    def capacity(self) -> int:
        """Most bytes this picture can carry (2-bit mode when needed)."""
        return core.capacity_for_size(self.width, self.height, core.MAX_DEPTH)

    @property
    def folder(self) -> str:
        return str(self.source.parent) if isinstance(self.source, Path) else pictures_dir()

    @property
    def stem(self) -> str:
        return self.source.stem if isinstance(self.source, Path) else "pasted image"


def load_image(source: Path | Image.Image, thumb_px: int, *, for_encoding: bool) -> LoadedImage:
    if isinstance(source, Path):
        with Image.open(source) as probe:
            fmt = probe.format or source.suffix.lstrip(".").upper()
        name = source.name
    else:
        fmt, name = "Clipboard", "Pasted image"
    img = core.open_image(source, for_encoding=for_encoding)
    scale = min(thumb_px / img.width, thumb_px / img.height, 1.0)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    # reducing_gap box-shrinks first, so a 12+ MP photo thumbnails in milliseconds.
    thumb = img.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)
    data_method = None
    try:
        data_method = core.detect_method(img)
    except StegoError:
        pass
    bpcs_room = core.bpcs_capacity(img) if for_encoding else 0
    return LoadedImage(source, name, img.width, img.height, fmt, thumb, data_method is not None,
                       bpcs_room, data_method)


class Worker:
    """Runs jobs off the Tk thread and delivers results back on it."""

    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._queue: queue.Queue = queue.Queue()
        self._poll()

    def run(self, job: Callable[[], Any], on_done: Callable[[Any], None],
            on_error: Callable[[BaseException], None]) -> None:
        def target() -> None:
            try:
                result = job()
            except BaseException as exc:  # delivered to the UI thread
                self._queue.put((on_error, exc))
            else:
                self._queue.put((on_done, result))
        threading.Thread(target=target, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                try:
                    callback, value = self._queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    callback(value)
                except Exception:
                    self._root.report_callback_exception(*sys.exc_info())
        finally:
            try:
                self._root.after(40, self._poll)
            except tk.TclError:  # window already destroyed
                pass


# -------------------------------------------------------------------- app

class App:
    def __init__(self, root: tk.Tk, initial: str | None = None) -> None:
        self.root = root
        self.worker = Worker(root)
        self._busy = 0

        # Hide page state
        self.cover: LoadedImage | None = None
        self.secret_mode = tk.StringVar(root, value="text")
        self.method = tk.StringVar(root, value="lsb")
        self.secret_file: Path | None = None
        self.secret_file_data: bytes | None = None
        self.use_password = tk.BooleanVar(root, value=False)
        self.password = tk.StringVar(root)
        self.password2 = tk.StringVar(root)
        self.needed: int | None = None
        self._size_job: str | None = None
        self._size_generation = 0

        # Reveal page state
        self.inspected: LoadedImage | None = None
        self.reveal_password = tk.StringVar(root)
        self.revealed: core.Revealed | None = None
        self._legacy_candidate: core.Revealed | None = None

        self.chrome = XPChrome(root, APP_NAME, icon=icons.app_icon(T.px(16)),
                               buttons=("help", "minimize", "close"),
                               on_close=self.close, on_help=self.about)
        self._build(self.chrome.body)
        self._bind_keys()
        self._refresh_hide()
        self._show_reveal_state("empty")
        self.reveal_button.set_enabled(False)
        self.where_button.set_enabled(False)
        self._update_method_hint()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._present()
        if initial:
            root.after(150, self.open_path, Path(initial))

    # ============================================================ layout
    def _build(self, body: tk.Frame) -> None:
        outer = tk.Frame(body, bg=T.DIALOG_BG)
        outer.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(8), 0))
        switch = tk.Frame(outer, bg=T.DIALOG_BG)
        switch.pack(fill="x", padx=T.px(2), pady=(0, T.px(6)))
        label(switch, "Method:").pack(side="left")
        XPRadio(switch, "LSB", self.method, "lsb", command=self._on_method).pack(
            side="left", padx=(T.px(8), 0))
        XPRadio(switch, "BPCS", self.method, "bpcs", command=self._on_method).pack(
            side="left", padx=(T.px(14), 0))
        self.method_hint = label(switch, "", fg=T.TEXT_MUTED, anchor="e")
        self.method_hint.pack(side="right")
        self.tabs = XPTabs(outer, on_change=self._on_tab_change)
        self.tabs.pack(fill="both", expand=True)
        hide_page = self.tabs.add("Hide")
        reveal_page = self.tabs.add("Reveal")
        self._build_hide(hide_page)
        self._build_reveal(reveal_page)

        bottom = tk.Frame(body, bg=T.DIALOG_BG)
        bottom.pack(fill="x", padx=T.px(8), pady=T.px(8))
        XPButton(bottom, "Close", command=self.close).pack(side="right")
        self.status = XPStatusBar(body)
        self.status.pack(fill="x", side="bottom")

    def _image_info(self, parent: tk.Frame, *, on_browse, on_paste, hint: str):
        """Drop zone + name/details/notes column + Browse/Paste buttons."""
        parent.grid_columnconfigure(1, weight=1)
        zone = ImageDropZone(parent, size=88, hint=hint, on_click=on_browse)
        zone.grid(row=0, column=0, rowspan=4, sticky="nw", padx=(0, T.px(10)))
        name = label(parent, "No image selected", font=T.FONT_BOLD, anchor="w")
        name.grid(row=0, column=1, sticky="ew")
        details = label(parent, "PNG, BMP, TIFF, GIF or JPEG", fg=T.TEXT_MUTED, anchor="w")
        details.grid(row=1, column=1, sticky="ew", pady=(T.px(3), 0))
        note = label(parent, "", anchor="nw", justify="left", height=2)
        note.grid(row=2, column=1, sticky="new", pady=(T.px(3), 0))
        parent.grid_rowconfigure(2, weight=1)
        buttons = tk.Frame(parent, bg=parent.cget("bg"))
        buttons.grid(row=3, column=1, sticky="sw", pady=(T.px(6), 0))
        XPButton(buttons, "Browse…", command=on_browse).pack(side="left")
        XPButton(buttons, "Paste", command=on_paste).pack(side="left", padx=(T.px(6), 0))
        return zone, name, details, note

    def _build_hide(self, page: tk.Frame) -> None:
        page.grid_columnconfigure(0, weight=1)
        pad = T.px(10)

        cover = XPGroupBox(page, "Cover image")
        cover.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad, 0))
        (self.cover_zone, self.cover_name, self.cover_details,
         self.cover_note) = self._image_info(cover.body, on_browse=self.browse_cover,
                                             on_paste=self.paste_cover, hint="Drop a picture here")
        enable_file_drop(cover, lambda paths: self.load_cover(Path(paths[0])), self.cover_zone.set_drop_hover)

        secret = XPGroupBox(page, "Secret to hide")
        secret.grid(row=1, column=0, sticky="nsew", padx=pad, pady=(T.px(8), 0))
        page.grid_rowconfigure(1, weight=1)
        sb = secret.body
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(1, weight=1)
        radios = tk.Frame(sb, bg=sb.cget("bg"))
        radios.grid(row=0, column=0, sticky="w", pady=(0, T.px(6)))
        XPRadio(radios, "Text message", self.secret_mode, "text", command=self._on_mode).pack(side="left")
        XPRadio(radios, "File", self.secret_mode, "file", command=self._on_mode).pack(side="left", padx=(T.px(18), 0))

        stack = tk.Frame(sb, bg=sb.cget("bg"))
        stack.grid(row=1, column=0, sticky="nsew")
        stack.grid_columnconfigure(0, weight=1)
        stack.grid_rowconfigure(0, weight=1)
        self.text_panel = tk.Frame(stack, bg=sb.cget("bg"))
        self.text_panel.grid(row=0, column=0, sticky="nsew")
        self.text_panel.grid_columnconfigure(0, weight=1)
        self.text_panel.grid_rowconfigure(0, weight=1)
        self.message = XPText(self.text_panel, height=5)
        self.message.grid(row=0, column=0, sticky="nsew")
        self.message.text.bind("<<Modified>>", self._on_message_modified)
        self.char_count = label(self.text_panel, "", fg=T.TEXT_MUTED, anchor="e")
        self.char_count.grid(row=1, column=0, sticky="e", pady=(T.px(3), 0))

        self.file_panel = tk.Frame(stack, bg=T.FIELD_BORDER)
        self.file_panel.grid(row=0, column=0, sticky="nsew")
        card = tk.Frame(self.file_panel, bg=T.WHITE)
        card.pack(fill="both", expand=True, padx=1, pady=1)
        card.grid_columnconfigure(1, weight=1)
        card.grid_rowconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)
        self._doc_icon = photo(icons.document_icon(T.px(32)))
        tk.Label(card, image=self._doc_icon, bg=T.WHITE, bd=0).grid(
            row=1, column=0, rowspan=2, padx=(T.px(12), T.px(10)))
        self.file_name = label(card, "No file chosen", font=T.FONT_BOLD, anchor="w")
        self.file_name.grid(row=1, column=1, sticky="ew")
        self.file_details = label(card, "Click Choose File… or drop any file here.",
                                  fg=T.TEXT_MUTED, anchor="w")
        self.file_details.grid(row=2, column=1, sticky="ew", pady=(T.px(2), 0))
        XPButton(card, "Choose File…", command=self.browse_secret_file).grid(
            row=1, column=2, rowspan=2, padx=(T.px(8), T.px(12)))
        self.text_panel.tkraise()
        enable_file_drop(secret, self._on_secret_drop)

        protect = XPGroupBox(page, "Protection")
        protect.grid(row=2, column=0, sticky="ew", padx=pad, pady=(T.px(8), 0))
        pb = protect.body
        pb.grid_columnconfigure(1, weight=1)
        pb.grid_columnconfigure(3, weight=1)
        XPCheck(pb, "Encrypt with a password (AES-256)", self.use_password,
                command=self._on_password_toggle).grid(row=0, column=0, columnspan=4, sticky="w")
        label(pb, "Password:").grid(row=1, column=0, sticky="w", pady=(T.px(6), 0))
        self.pw_entry = XPEntry(pb, self.password, show="●", width=12)
        self.pw_entry.grid(row=1, column=1, sticky="ew", padx=(T.px(6), T.px(12)), pady=(T.px(6), 0))
        label(pb, "Confirm:").grid(row=1, column=2, sticky="w", pady=(T.px(6), 0))
        self.pw2_entry = XPEntry(pb, self.password2, show="●", width=12)
        self.pw2_entry.grid(row=1, column=3, sticky="ew", padx=(T.px(6), 0), pady=(T.px(6), 0))
        for var in (self.password, self.password2):
            var.trace_add("write", lambda *_: self._on_password_change())
        self._on_password_toggle()

        meter = tk.Frame(page, bg=T.PANEL_BG)
        meter.grid(row=3, column=0, sticky="ew", padx=pad + T.px(2), pady=(T.px(10), 0))
        meter.grid_columnconfigure(1, weight=1)
        label(meter, "Space used:").grid(row=0, column=0, sticky="w")
        self.meter = XPProgress(meter, width=160, height=14)
        self.meter.grid(row=0, column=1, sticky="ew", padx=T.px(8))
        self.meter_text = label(meter, "", anchor="e", width=18)
        self.meter_text.grid(row=0, column=2, sticky="e")

        actions = tk.Frame(page, bg=T.PANEL_BG)
        actions.grid(row=4, column=0, sticky="ew", padx=pad, pady=(T.px(8), pad))
        actions.grid_columnconfigure(0, weight=1)
        self.hide_hint = label(actions, "", fg=T.TEXT_MUTED, anchor="w", justify="left",
                               wraplength=T.px(290))
        self.hide_hint.grid(row=0, column=0, sticky="ew", padx=(T.px(2), T.px(8)))
        self.hide_button = XPButton(actions, "Hide Data…", command=self.hide, default=True)
        self.hide_button.grid(row=0, column=1, sticky="e")

    def _build_reveal(self, page: tk.Frame) -> None:
        page.grid_columnconfigure(0, weight=1)
        pad = T.px(10)

        source = XPGroupBox(page, "Image to inspect")
        source.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad, 0))
        (self.reveal_zone, self.reveal_name, self.reveal_details,
         self.reveal_note) = self._image_info(source.body, on_browse=self.browse_reveal,
                                              on_paste=self.paste_reveal, hint="Drop a picture here")

        pw_row = tk.Frame(page, bg=T.PANEL_BG)
        pw_row.grid(row=1, column=0, sticky="ew", padx=pad + T.px(2), pady=(T.px(10), 0))
        pw_row.grid_columnconfigure(1, weight=1)
        label(pw_row, "Password:").grid(row=0, column=0, sticky="w")
        self.reveal_pw_entry = XPEntry(pw_row, self.reveal_password, show="●", width=16)
        self.reveal_pw_entry.grid(row=0, column=1, sticky="ew", padx=(T.px(6), T.px(8)))
        self.reveal_button = XPButton(pw_row, "Reveal", command=self.reveal)
        self.reveal_button.grid(row=0, column=2, sticky="e")
        self.where_button = XPButton(pw_row, "Show Where…", command=self.show_data_map)
        self.where_button.grid(row=0, column=3, sticky="e", padx=(T.px(6), 0))
        label(pw_row, "Only needed when the hidden content is password-protected.",
              fg=T.TEXT_MUTED, anchor="w").grid(row=1, column=1, columnspan=3, sticky="w",
                                                padx=(T.px(6), 0), pady=(T.px(3), 0))
        self.reveal_pw_entry.bind_entry("<Return>", lambda e: (self.reveal(), "break")[1])

        result = XPGroupBox(page, "Hidden content")
        result.grid(row=2, column=0, sticky="nsew", padx=pad, pady=(T.px(8), pad))
        page.grid_rowconfigure(2, weight=1)
        rb = result.body
        rb.grid_columnconfigure(0, weight=1)
        rb.grid_rowconfigure(0, weight=1)
        bg = rb.cget("bg")

        # empty / status message
        self.result_message = tk.Frame(rb, bg=bg)
        self.result_message.grid(row=0, column=0, sticky="nsew")
        self.result_message.grid_columnconfigure(1, weight=1)
        self.result_message.grid_rowconfigure(0, weight=1)
        self.result_icon = tk.Label(self.result_message, bg=bg, bd=0)
        self.result_icon.grid(row=0, column=0, sticky="w", padx=(T.px(4), T.px(10)))
        self.result_text = label(self.result_message, "", anchor="w", justify="left", wraplength=T.px(300))
        self.result_text.grid(row=0, column=1, sticky="ew")
        self.extract_anyway = XPButton(self.result_message, "Extract Anyway", command=self._extract_legacy)
        self.switch_method_button = XPButton(self.result_message, "Use BPCS",
                                             command=self._use_detected_method)

        # revealed text
        self.result_textpanel = tk.Frame(rb, bg=bg)
        self.result_textpanel.grid(row=0, column=0, sticky="nsew")
        self.result_textpanel.grid_columnconfigure(0, weight=1)
        self.result_textpanel.grid_rowconfigure(0, weight=1)
        self.revealed_text = XPText(self.result_textpanel, height=6, readonly=True)
        self.revealed_text.grid(row=0, column=0, columnspan=3, sticky="nsew")
        self.text_info = label(self.result_textpanel, "", fg=T.TEXT_MUTED, anchor="w")
        self.text_info.grid(row=1, column=0, sticky="ew", pady=(T.px(6), 0))
        XPButton(self.result_textpanel, "Copy", command=self.copy_revealed).grid(
            row=1, column=1, sticky="e", padx=(T.px(6), 0), pady=(T.px(6), 0))
        XPButton(self.result_textpanel, "Save As…", command=self.save_revealed).grid(
            row=1, column=2, sticky="e", padx=(T.px(6), 0), pady=(T.px(6), 0))

        # revealed file
        self.result_filepanel = tk.Frame(rb, bg=bg)
        self.result_filepanel.grid(row=0, column=0, sticky="nsew")
        self.result_filepanel.grid_columnconfigure(1, weight=1)
        self.result_filepanel.grid_rowconfigure(0, weight=1)
        self.result_filepanel.grid_rowconfigure(3, weight=1)
        tk.Label(self.result_filepanel, image=self._doc_icon, bg=bg, bd=0).grid(
            row=1, column=0, rowspan=2, padx=(T.px(4), T.px(10)))
        self.revealed_name = label(self.result_filepanel, "", font=T.FONT_BOLD, anchor="w")
        self.revealed_name.grid(row=1, column=1, sticky="ew")
        self.revealed_info = label(self.result_filepanel, "", fg=T.TEXT_MUTED, anchor="w")
        self.revealed_info.grid(row=2, column=1, sticky="ew", pady=(T.px(2), 0))
        XPButton(self.result_filepanel, "Save File…", command=self.save_revealed, default=False).grid(
            row=1, column=2, rowspan=2, sticky="e", padx=(T.px(8), 0))

        enable_file_drop(page, lambda paths: self.load_reveal(Path(paths[0])), self.reveal_zone.set_drop_hover)

    def _present(self) -> None:
        """Show the window centred, borderless, with a taskbar button."""
        root = self.root
        root.overrideredirect(True)
        # First map off-screen so the style switch below can't flicker.
        root.geometry("+-32000+-32000")
        root.deiconify()
        root.update_idletasks()
        winapi.make_borderless(root, taskbar=True)
        root.withdraw()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        x = (root.winfo_screenwidth() - w) // 2
        y = max(0, (root.winfo_screenheight() - h) // 2 - T.px(24))
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.deiconify()
        root.update_idletasks()
        winapi.round_top_corners(root, T.px(7))
        winapi.bring_to_front(root)
        self.message.text.focus_set()
        sounds.play_startup()

    # ============================================================ keyboard
    def _bind_keys(self) -> None:
        r = self.root
        r.bind("<Return>", self._on_return)
        r.bind("<Control-Tab>", lambda e: (self.tabs.select(self.tabs.current + 1), "break")[1])
        r.bind("<Control-Shift-Tab>", lambda e: (self.tabs.select(self.tabs.current - 1), "break")[1])
        r.bind("<Control-ISO_Left_Tab>", lambda e: (self.tabs.select(self.tabs.current - 1), "break")[1])
        r.bind("<Control-o>", lambda e: self._browse_current())
        r.bind("<Control-O>", lambda e: self._browse_current())
        r.bind("<Control-v>", self._on_paste_key, add="+")
        r.bind("<Control-V>", self._on_paste_key, add="+")
        r.bind("<Alt-F4>", lambda e: self.close())
        r.bind("<F1>", lambda e: self.about())
        r.bind_all("<Key>", sounds.on_key, add="+")

    def _on_return(self, event) -> None:
        if isinstance(event.widget, (tk.Text, XPButton)):
            return
        button = self.hide_button if self.tabs.current == 0 else self.reveal_button
        button.invoke()

    def _browse_current(self) -> None:
        (self.browse_cover if self.tabs.current == 0 else self.browse_reveal)()

    def _on_paste_key(self, _event) -> None:
        # Text still pastes as usual; a picture or copied file goes to the current page.
        content = clipboard_content(images_only=False)
        if content is None:
            return
        if isinstance(content, Path) and not is_image_path(content):
            if self.tabs.current == 0:
                self._on_secret_drop([str(content)])
            return
        (self.load_cover if self.tabs.current == 0 else self.load_reveal)(content)

    def _on_tab_change(self, index: int) -> None:
        self.hide_button.set_default(index == 0)
        self.reveal_button.set_default(index == 1)
        if index == 1:
            self.reveal_pw_entry.focus_set()

    # ============================================================ busy state
    def _set_busy(self, on: bool, text: str | None = None) -> None:
        self._busy += 1 if on else -1
        busy = self._busy > 0
        self.status.busy(busy)
        self.root.configure(cursor="watch" if busy else "")
        if text is not None:
            self.status.set(text)
        self._refresh_hide()
        self.reveal_button.set_enabled(not busy and self.inspected is not None)
        self.where_button.set_enabled(not busy and self.inspected is not None and self.inspected.has_data)

    def _error(self, title: str, exc: BaseException) -> None:
        if isinstance(exc, FileNotFoundError):
            text = f"The file could not be found:\n{exc.filename or exc}"
        elif isinstance(exc, PermissionError):
            text = f"Windows denied access to:\n{exc.filename or exc}"
        elif isinstance(exc, (StegoError, OSError)):
            text = str(exc)
        else:
            text = f"Something unexpected went wrong.\n\n{type(exc).__name__}: {exc}"
        self.status.set(title)
        dialogs.message(self.root, APP_NAME, text, kind="error")

    # ============================================================ any file
    def open_path(self, path: Path) -> None:
        """Open a file given on the command line: reveal if it hides something."""
        if not path.is_file():
            return

        def job():
            try:
                return core.has_container(path)
            except (StegoError, OSError):
                return False

        def done(has_data: bool) -> None:
            if has_data:
                self.tabs.select(1)
                self.load_reveal(path)
            else:
                self.load_cover(path)

        self.worker.run(job, done, lambda exc: self.load_cover(path))

    # ============================================================ method
    def _update_method_hint(self) -> None:
        self.method_hint.configure(text="Hides in every pixel's lowest bits"
                                   if self.method.get() == "lsb"
                                   else "Hides in the picture's busy areas only")

    def _on_method(self) -> None:
        """The LSB/BPCS switch applies to both pages."""
        self._update_method_hint()
        self.status.set(f"Method: {METHOD_NAMES[self.method.get()]}.")
        self._refresh_hide()
        if self.inspected is not None:
            self._show_reveal_note(self.inspected)
            self.reveal(auto=True)

    def _use_detected_method(self) -> None:
        if self.inspected is not None and self.inspected.data_method:
            self.method.set(self.inspected.data_method)
            self._on_method()

    # ============================================================ hide page
    def browse_cover(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, title="Choose a Cover Image",
                                          filetypes=IMAGE_TYPES, initialdir=self._initial_dir())
        if path:
            self.load_cover(Path(path))

    def paste_cover(self) -> None:
        content = clipboard_content()
        if content is None:
            dialogs.message(self.root, APP_NAME, "There is no picture on the clipboard.\n\n"
                            "Copy an image (or an image file in Explorer) and try again.", kind="info")
            return
        self.load_cover(content)

    def _initial_dir(self) -> str:
        for loaded in (self.cover, self.inspected):
            if loaded and isinstance(loaded.source, Path):
                return loaded.folder
        return pictures_dir()

    def load_cover(self, source: Path | Image.Image) -> None:
        self._set_busy(True, "Opening image…")

        def done(loaded: LoadedImage) -> None:
            self._set_busy(False, f"Loaded {loaded.name}.")
            self.cover = loaded
            self.cover_zone.set_image(loaded.thumb)
            self.cover_name.configure(text=ellipsize(loaded.name, T.FONT_BOLD, T.px(250)))
            self.cover_details.configure(text=f"{loaded.width:,} × {loaded.height:,} pixels · {loaded.fmt}")
            bpcs_room = max(0, loaded.bpcs_capacity - core.HEADER.size)
            notes = [f"Can hide up to {human_size(loaded.capacity - core.HEADER.size)} with LSB, "
                     f"{human_size(bpcs_room)} with BPCS."]
            if loaded.has_data:
                notes.append("Already holds hidden data; it will be replaced.")
            elif loaded.fmt.upper() in LOSSY_FORMATS:
                notes.append("The result will be saved as PNG.")
            self.cover_note.configure(text="\n".join(notes), fg=T.TEXT)
            self._schedule_size()

        def failed(exc: BaseException) -> None:
            self._set_busy(False)
            self._error("Could not open the image.", exc)

        source = Path(source) if isinstance(source, str) else source
        self.worker.run(lambda: load_image(source, T.px(84) * 2, for_encoding=True), done, failed)

    def _on_mode(self) -> None:
        if self.secret_mode.get() == "text":
            self.text_panel.tkraise()
            self.message.text.focus_set()
        else:
            self.file_panel.tkraise()
        self._schedule_size()

    def _on_message_modified(self, _event=None) -> None:
        self.message.text.edit_modified(False)
        count = len(self.message.get_text())
        self.char_count.configure(text=f"{count:,} character{'s' if count != 1 else ''}" if count else "")
        self._schedule_size()

    def _on_secret_drop(self, paths: list[str]) -> None:
        self.secret_mode.set("file")
        self._on_mode()
        self.load_secret_file(Path(paths[0]))

    def browse_secret_file(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, title="Choose a File to Hide",
                                          initialdir=self._initial_dir())
        if path:
            self.load_secret_file(Path(path))

    def load_secret_file(self, path: Path) -> None:
        try:
            size = path.stat().st_size
            if path.is_dir():
                raise IsADirectoryError(f"{path.name} is a folder. Zip it first, then hide the .zip file.")
            if size > MAX_SECRET_FILE:
                raise StegoError(f"{path.name} is {human_size(size)}. Files up to "
                                 f"{human_size(MAX_SECRET_FILE)} are supported.")
            data = path.read_bytes()
        except (OSError, StegoError) as exc:
            self._error("Could not read the file.", exc)
            return
        self.secret_file, self.secret_file_data = path, data
        self.file_name.configure(text=ellipsize(path.name, T.FONT_BOLD, T.px(230)))
        self.file_details.configure(text=f"{human_size(len(data))} · {ellipsize(str(path.parent), T.FONT, T.px(140), middle=True)}")
        self.status.set(f"Selected {path.name}.")
        self._schedule_size()

    def _on_password_toggle(self) -> None:
        on = self.use_password.get()
        self.pw_entry.set_enabled(on)
        self.pw2_entry.set_enabled(on)
        if on:
            self.pw_entry.focus_set()
        self._schedule_size()

    def _on_password_change(self) -> None:
        self._refresh_hide()

    def _current_secret(self) -> core.Secret | None:
        if self.secret_mode.get() == "text":
            text = self.message.get_text()
            return core.TextSecret(text) if text else None
        if self.secret_file is not None and self.secret_file_data is not None:
            return core.FileSecret(self.secret_file.name, self.secret_file_data)
        return None

    def _schedule_size(self) -> None:
        if self._size_job is not None:
            self.root.after_cancel(self._size_job)
        self._size_job = self.root.after(120, self._compute_size)

    def _compute_size(self) -> None:
        self._size_job = None
        self._size_generation += 1
        generation = self._size_generation
        secret = self._current_secret()
        password = "x" if self.use_password.get() else None
        if secret is None:
            self.needed = None
            self._refresh_hide()
            return
        payload = len(secret.text) if isinstance(secret, core.TextSecret) else len(secret.data)
        if payload < 256 * 1024:
            self.needed = core.container_size(secret, password)
            self._refresh_hide()
            return

        def done(size: int) -> None:
            if generation == self._size_generation:
                self.needed = size
                self._refresh_hide()

        self.needed = None
        self._refresh_hide(measuring=True)
        self.worker.run(lambda: core.container_size(secret, password), done, lambda exc: None)

    def _refresh_hide(self, measuring: bool = False) -> None:
        if not hasattr(self, "hide_button"):
            return
        use_bpcs = self.method.get() == "bpcs"
        cap = (self.cover.bpcs_capacity if use_bpcs else self.cover.capacity) if self.cover else 0
        need = self.needed
        depth = core.depth_needed(need, self.cover.width, self.cover.height) \
            if self.cover and need is not None and not use_bpcs else None
        if cap and need is not None:
            fraction = need / cap
            # Green: 1 bit per channel (or BPCS). Yellow: 2 bits (still invisible). Red: doesn't fit.
            if use_bpcs:
                color = "red" if need > cap else "green"
            else:
                color = "red" if depth is None else ("yellow" if depth > 1 else "green")
            self.meter.set(min(1.0, fraction), color)
            percent = f"{fraction:.0%}" if fraction >= 0.01 else "<1%"
            self.meter_text.configure(text=f"{human_size(need)} ({percent})", fg=T.TEXT_ERROR if need > cap else T.TEXT)
        else:
            self.meter.set(0)
            self.meter_text.configure(text=human_size(need) if need else "", fg=T.TEXT)

        secret_ready = self._current_secret() is not None
        pw_on = self.use_password.get()
        pw, pw2 = self.password.get(), self.password2.get()
        problem: str | None = None
        if not self.cover:
            problem = "Choose a cover image to begin."
        elif not secret_ready:
            problem = "Type the message to hide." if self.secret_mode.get() == "text" \
                else "Choose the file to hide."
        elif measuring or need is None:
            problem = "Measuring…"
        elif use_bpcs and not cap:
            problem = "This picture has no busy areas for BPCS. Use LSB or a more detailed photo."
        elif need > cap:
            problem = f"Too big by {human_size(need - cap)}. " + \
                ("Try LSB or a more detailed image." if use_bpcs else "Try a bigger image.")
        elif pw_on and not pw:
            problem = "Enter a password or untick encryption."
        elif pw_on and pw != pw2:
            problem = "The passwords don't match."
        error = problem is not None and problem.startswith(("Too big", "The passwords", "This picture"))
        if use_bpcs:
            ready = "Ready to hide with BPCS."
        else:
            ready = "Ready to hide (2-bit mode for extra room)." if depth and depth > 1 else "Ready to hide."
        self.hide_hint.configure(text=problem or ready,
                                 fg=T.TEXT_ERROR if error else T.TEXT_MUTED)
        self.hide_button.set_enabled(problem is None and self._busy == 0)

    def hide(self) -> None:
        if not self.hide_button.enabled or self.cover is None:
            return
        secret = self._current_secret()
        if secret is None:
            return
        cover = self.cover
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save Picture With Hidden Data", defaultextension=".png",
            filetypes=[("PNG image", "*.png")], initialdir=cover.folder,
            initialfile=f"{cover.stem}_hidden.png")
        if not path:
            return
        password = self.password.get() if self.use_password.get() else None
        method = self.method.get()
        what = "message" if isinstance(secret, core.TextSecret) else f"file “{secret.name}”"
        self._set_busy(True, "Hiding data…")

        def done(result: core.EncodeResult) -> None:
            self._set_busy(False, f"Saved {result.path.name} ({human_size(result.used)} hidden).")
            text = f"Your {what} is now hidden inside:\n{result.path}"
            detail = ("Share the picture as a PNG file. Apps that shrink or recompress images "
                      "(most chat apps and social networks) will erase the hidden data.")
            if result.renamed:
                detail = "It was saved as PNG because other formats would destroy the hidden data.\n\n" + detail
            if password:
                detail += "\n\nYou'll need the password to reveal it. It cannot be recovered if lost."
            choice = dialogs.message(self.root, APP_NAME, text, kind="info", detail=detail,
                                     buttons=("Show Changes", "Open Folder", "OK"), default=2, cancel="OK")
            if choice == "Open Folder":
                open_folder(result.path)
            elif choice == "Show Changes":
                self.show_changes(cover, result)

        def failed(exc: BaseException) -> None:
            self._set_busy(False)
            if isinstance(exc, CapacityError):
                self._error("The secret does not fit.", exc)
            else:
                self._error("Hiding failed.", exc)

        self.worker.run(lambda: core.encode(cover.source, secret, path, password, method=method),
                        done, failed)

    # ============================================================ reveal page
    def browse_reveal(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, title="Choose a Picture to Inspect",
                                          filetypes=IMAGE_TYPES, initialdir=self._initial_dir())
        if path:
            self.load_reveal(Path(path))

    def paste_reveal(self) -> None:
        content = clipboard_content()
        if content is None:
            dialogs.message(self.root, APP_NAME, "There is no picture on the clipboard.", kind="info")
            return
        self.load_reveal(content)

    def load_reveal(self, source: Path | Image.Image) -> None:
        if self.tabs.current != 1:
            self.tabs.select(1)
        self._set_busy(True, "Opening image…")
        source = Path(source) if isinstance(source, str) else source

        def done(loaded: LoadedImage) -> None:
            self._set_busy(False, f"Loaded {loaded.name}.")
            self.inspected = loaded
            self.reveal_button.set_enabled(self._busy == 0)
            self.where_button.set_enabled(self._busy == 0 and loaded.has_data)
            self.reveal_zone.set_image(loaded.thumb)
            self.reveal_name.configure(text=ellipsize(loaded.name, T.FONT_BOLD, T.px(250)))
            self.reveal_details.configure(text=f"{loaded.width:,} × {loaded.height:,} pixels · {loaded.fmt}")
            self._show_reveal_note(loaded)
            self.reveal(auto=True)

        def failed(exc: BaseException) -> None:
            self._set_busy(False)
            self._error("Could not open the image.", exc)

        self.worker.run(lambda: load_image(source, T.px(84) * 2, for_encoding=False), done, failed)

    def _show_reveal_note(self, loaded: LoadedImage) -> None:
        if loaded.data_method:
            self.reveal_note.configure(
                text=f"Contains hidden data ({METHOD_NAMES[loaded.data_method]}).", fg=T.TEXT_OK)
        else:
            self.reveal_note.configure(text="No hidden data detected.", fg=T.TEXT_MUTED)

    def reveal(self, auto: bool = False) -> None:
        loaded = self.inspected
        if loaded is None:
            if not auto:
                self.browse_reveal()
            return
        if self._busy and not auto:
            return
        password = self.reveal_password.get() or None
        method = self.method.get()
        self._set_busy(True, f"Looking for {METHOD_NAMES[method]} data…")

        def done(revealed: core.Revealed) -> None:
            self._set_busy(False)
            self._show_revealed(revealed)

        def failed(exc: BaseException) -> None:
            self._set_busy(False)
            self._legacy_candidate = None
            if isinstance(exc, PasswordRequiredError):
                self.status.set("The hidden content is password-protected.")
                self._show_reveal_state("locked")
                self.reveal_pw_entry.focus_set()
            elif isinstance(exc, WrongPasswordError):
                self.status.set("Wrong password.")
                self._show_reveal_state("wrong")
                self.reveal_pw_entry.entry.select_range(0, "end")
                self.reveal_pw_entry.focus_set()
            elif isinstance(exc, NoHiddenDataError):
                other = loaded.data_method
                if other and other != method:
                    self.status.set(f"This picture was hidden with {METHOD_NAMES[other]}.")
                    self._show_reveal_state("other")
                else:
                    self.status.set(f"No {METHOD_NAMES[method]} data found.")
                    self._legacy_candidate = exc.candidate
                    self._show_reveal_state("none")
            elif isinstance(exc, CorruptDataError):
                self.status.set("The hidden data is damaged.")
                self._show_reveal_state("corrupt", str(exc))
            else:
                self._show_reveal_state("empty")
                self._error("Reading the image failed.", exc)

        self.worker.run(lambda: core.decode(loaded.source, password, method=method), done, failed)

    def show_changes(self, cover: LoadedImage, result: core.EncodeResult) -> None:
        """Open the map for a picture just made, comparing it with its cover."""
        self._set_busy(True, "Comparing with the original…")

        def job():
            before = np.asarray(core.open_image(cover.source, for_encoding=True), dtype=np.uint8)
            img = core.open_image(result.path)
            return before, np.asarray(img, dtype=np.uint8), core.locate(img, method=result.method)

        def done(found) -> None:
            before, after, data = found
            self._set_busy(False, f"{int((before[..., :3] != after[..., :3]).any(axis=2).sum()):,} pixels changed.")
            datamap.show(self.root, result.path.name, after, data, original=before)

        def failed(exc: BaseException) -> None:
            self._set_busy(False)
            self._error("Could not compare the pictures.", exc)

        self.worker.run(job, done, failed)

    def show_data_map(self) -> None:
        """Open the map of the pixels and bits that hold the hidden data."""
        loaded = self.inspected
        if loaded is None or self._busy:
            return
        self._set_busy(True, "Mapping the hidden data…")

        def job():
            img = core.open_image(loaded.source)
            return np.asarray(img, dtype=np.uint8), core.locate(img)

        def done(result) -> None:
            rgb, data = result
            self._set_busy(False, f"The hidden data is in {data.pixels:,} pixels.")
            datamap.show(self.root, loaded.name, rgb, data)

        def failed(exc: BaseException) -> None:
            self._set_busy(False)
            if isinstance(exc, NoHiddenDataError):
                dialogs.message(self.root, APP_NAME, "There is no hidden data to show in this picture.")
            else:
                self._error("Could not map the hidden data.", exc)

        self.worker.run(job, done, failed)

    def _show_reveal_state(self, state: str, extra: str = "") -> None:
        method = METHOD_NAMES[self.method.get()]
        other = self.inspected.data_method if self.inspected else None
        other_name = METHOD_NAMES.get(other or "", "")
        icon_kind, text = {
            "empty": (None, "Open a picture to see what's hidden inside it.\n"
                            "You can also drop one onto this page or paste it with Ctrl+V."),
            "locked": ("question", "This picture holds password-protected content.\n"
                                   "Type the password above and click Reveal."),
            "wrong": ("error", "That password is incorrect. Check it and try again."),
            "none": ("info", f"No {method} hidden data was found in this picture."),
            "other": ("info", f"This picture holds data hidden with {other_name}, "
                              f"but the method is set to {method}.\n"
                              f"Switch to {other_name} to reveal it."),
            "corrupt": ("warning", extra),
        }[state]
        self.revealed = None
        if icon_kind:
            self._result_img = photo(icons.message_icon(icon_kind, T.px(32)))
            self.result_icon.configure(image=self._result_img)
            self.result_icon.grid()
        else:
            self.result_icon.grid_remove()
        if state == "none" and self._legacy_candidate is not None:
            text += ("\n\nIt might hold data from the older version of this tool, which had no "
                     "integrity check, so the result may be noise.")
            self.extract_anyway.grid(row=1, column=1, sticky="w", pady=(T.px(8), 0))
        else:
            self.extract_anyway.grid_remove()
        if state == "other":
            self.switch_method_button.set_text(f"Use {other_name}")
            self.switch_method_button.grid(row=1, column=1, sticky="w", pady=(T.px(8), 0))
        else:
            self.switch_method_button.grid_remove()
        self.result_text.configure(text=text, fg=T.TEXT_MUTED if state == "empty" else T.TEXT)
        self.result_message.tkraise()

    def _extract_legacy(self) -> None:
        if self._legacy_candidate is not None:
            self._show_revealed(self._legacy_candidate)

    def _show_revealed(self, revealed: core.Revealed) -> None:
        self.revealed = revealed
        traits = [METHOD_NAMES.get(revealed.method, revealed.method)]
        if revealed.encrypted:
            traits.append("encrypted")
        traits.append("old format, unverified" if revealed.legacy else "verified")
        if revealed.is_text:
            try:
                text = revealed.text
            except UnicodeDecodeError:
                text = revealed.data.decode("utf-8", errors="replace")
            self.revealed_text.set_text(text)
            count = len(text)
            self.text_info.configure(text=f"{count:,} char{'s' if count != 1 else ''} · " + " · ".join(traits))
            self.result_textpanel.tkraise()
            self.status.set("Revealed a hidden message.")
        else:
            name = revealed.name or "hidden file"
            self.revealed_name.configure(text=ellipsize(name, T.FONT_BOLD, T.px(240)))
            self.revealed_info.configure(text=f"{human_size(len(revealed.data))} · " + " · ".join(traits))
            self.result_filepanel.tkraise()
            self.status.set(f"Revealed a hidden file: {name}.")

    def copy_revealed(self) -> None:
        if self.revealed is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.revealed_text.get_text())
        self.status.set("Message copied to the clipboard.")

    def save_revealed(self) -> None:
        revealed = self.revealed
        if revealed is None:
            return
        folder = self.inspected.folder if self.inspected else pictures_dir()
        if revealed.is_text:
            path = filedialog.asksaveasfilename(parent=self.root, title="Save Hidden Message",
                                                defaultextension=".txt", initialdir=folder,
                                                initialfile="hidden message.txt",
                                                filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
            data = self.revealed_text.get_text().encode("utf-8")
        else:
            name = Path(revealed.name or "hidden file").name
            ext = Path(name).suffix
            path = filedialog.asksaveasfilename(parent=self.root, title="Save Hidden File",
                                                initialdir=folder, initialfile=name,
                                                filetypes=[(f"{ext.upper().lstrip('.')} file", f"*{ext}"),
                                                           ("All files", "*.*")] if ext else [("All files", "*.*")])
            data = revealed.data
        if not path:
            return
        try:
            Path(path).write_bytes(data)
        except OSError as exc:
            self._error("Saving failed.", exc)
            return
        self.status.set(f"Saved {Path(path).name}.")
        choice = dialogs.message(self.root, APP_NAME, f"Saved to:\n{path}", kind="info",
                                 buttons=("Open Folder", "OK"), default=1, cancel="OK")
        if choice == "Open Folder":
            open_folder(Path(path))

    # ============================================================ window
    def about(self) -> None:
        dialogs.message(
            self.root, f"About {APP_NAME}",
            f"{APP_NAME} {__version__}\n\n"
            "Hides a message or a file in the lowest bit of each pixel's red, green and blue "
            "values (LSB), or in the picture's noisy 8×8 bit-plane blocks (BPCS). The change "
            "is invisible to the eye.\n\n"
            "Hidden content is compressed, checked for damage, and can be locked with a "
            "password (AES-256-GCM).",
            icon=icons.app_icon(T.px(32)),
            detail="Tips: drop pictures or files straight onto the window, paste images with "
                   "Ctrl+V, and switch pages with Ctrl+Tab.")

    def close(self) -> None:
        if self._busy:
            choice = dialogs.message(self.root, APP_NAME, "An operation is still running. Quit anyway?",
                                     kind="warning", buttons=("Quit", "Cancel"), default=1, cancel="Cancel")
            if choice != "Quit":
                return
        sounds.close()
        self.root.destroy()


def _make_root() -> tk.Tk:
    if widgets.HAS_DND:
        try:
            from tkinterdnd2 import TkinterDnD
            return TkinterDnD.Tk()
        except Exception:
            widgets.HAS_DND = False
    return tk.Tk()


def _install_error_handler(root: tk.Tk) -> None:
    """There is no console under pythonw: log unexpected errors and say so."""
    def report(exc_type, exc, tb) -> None:
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as log:
                log.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} ({__version__})\n{details}\n")
        except OSError:
            pass
        try:
            dialogs.message(root, APP_NAME, "Something went wrong. Your files have not been changed.",
                            kind="error", detail=f"{exc_type.__name__}: {exc}\n\nDetails were saved to {LOG_PATH}")
        except tk.TclError:
            pass
    root.report_callback_exception = report


def run(argv: list[str] | None = None) -> None:
    winapi.enable_dpi_awareness()
    winapi.set_app_id(APP_ID)
    root = _make_root()
    root.withdraw()
    _install_error_handler(root)
    T.init(root)
    root.title(APP_NAME)
    root.iconphoto(True, *(photo(icons.app_icon(size)) for size in (16, 32, 48, 256)))
    App(root, initial=(argv or [None])[0])
    root.mainloop()
