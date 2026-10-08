"""The "Where is the data?" window: a map of the pixels that hold hidden data,
a magnifier, and the selected pixel's colour values bit by bit.

Given the original cover too, it shows what changed: each value before and
after, with the bits that changed in red and the hidden bits that already
matched (so didn't need to change) in amber.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import numpy as np
from PIL import Image

from .. import core
from ..errors import StegoError
from . import dialogs
from . import theme as T
from .dialogs import XPDialog
from .widgets import XPButton, XPGroupBox, label, photo

HIGHLIGHT = (232, 52, 12)        # changed (or, without the original, holds hidden data)
HIGHLIGHT_HEX = "#E8340C"
KEPT = (242, 169, 59)            # holds hidden data, but already had the right bits
KEPT_HEX = "#F2A93B"
CHANNELS = ("R", "G", "B")
CHANNEL_NAMES = ("red", "green", "blue")
MAGNIFIER = 15                   # pixels across the magnifier
IMAGE_TYPES = [("Pictures", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"), ("All files", "*.*")]


def render(rgb: np.ndarray, used: np.ndarray, changed: np.ndarray | None = None) -> Image.Image:
    """Full-size map: the picture washed out to grey, data pixels coloured.

    Without ``changed`` every data pixel is red. With it, changed pixels are
    red and data pixels that kept their value are amber.
    """
    grey = rgb[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    base = (grey * 0.35 + 255 * 0.65).astype(np.uint8)
    out = np.repeat(base[..., None], 3, axis=2)
    if changed is None:
        out[used] = HIGHLIGHT
    else:
        out[used] = KEPT
        out[changed] = HIGHLIGHT
    return Image.fromarray(out)


def _pool(mask: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Shrink ``mask``: a cell is set when any pixel under it is."""
    return np.maximum.reduceat(np.maximum.reduceat(mask.astype(np.uint8), rows, axis=0),
                               cols, axis=1).astype(bool)


def _fit(rgb: np.ndarray, used: np.ndarray, max_w: int, max_h: int,
         changed: np.ndarray | None = None) -> tuple[Image.Image, float, np.ndarray]:
    """Map scaled to fit, display pixels per image pixel, and the display mask.

    Shrinking keeps every data pixel visible: a display pixel is coloured when
    any image pixel under it holds data.
    """
    h, w = used.shape
    scale = min(max_w / w, max_h / h)
    if scale >= 1:
        zoom = max(1, min(int(scale), 16))
        shown = used.repeat(zoom, axis=0).repeat(zoom, axis=1)
        image = render(rgb, used, changed).resize((w * zoom, h * zoom), Image.Resampling.NEAREST)
        return image, float(zoom), shown
    tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    rows = (np.arange(th) * h) // th
    cols = (np.arange(tw) * w) // tw
    small_used = _pool(used, rows, cols)
    small_changed = _pool(changed, rows, cols) if changed is not None else None
    small = np.asarray(Image.fromarray(np.ascontiguousarray(rgb[..., :3])).resize(
        (tw, th), Image.Resampling.BOX))
    return render(small, small_used, small_changed), tw / w, small_used


def _chip(parent: tk.Misc, colour: str, text: str) -> None:
    tk.Frame(parent, width=T.px(10), height=T.px(10), bg=colour).pack(side="left")
    label(parent, f" {text}", anchor="w").pack(side="left", padx=(0, T.px(12)))


class DataMapWindow(XPDialog):
    def __init__(self, parent: tk.Misc, name: str, rgb: np.ndarray, data: core.DataMap,
                 original: np.ndarray | None = None) -> None:
        super().__init__(parent, f"Where the data is hidden: {name}")
        self.rgb = rgb
        self.data = data
        self.used = data.bits.any(axis=2)
        self.height, self.width = self.used.shape
        self.original: np.ndarray | None = None
        self.changed: np.ndarray | None = None
        self._name = name
        pad = T.px(10)

        top = tk.Frame(self.body, bg=T.DIALOG_BG)
        top.pack(fill="both", expand=True, padx=pad, pady=(pad, 0))
        top.grid_columnconfigure(0, weight=1)

        # Map
        map_box = XPGroupBox(top, "Map")
        map_box.grid(row=0, column=0, sticky="nsew")
        self._map_size = (T.px(400), T.px(250))
        image, self.scale, _ = _fit(rgb, self.used, *self._map_size)
        # The border goes around the canvas, not over the picture's edge rows,
        # where LSB data starts.
        frame = tk.Frame(map_box.body, bg=T.FIELD_BORDER, padx=1, pady=1)
        frame.pack()
        self.map = tk.Canvas(frame, width=image.width, height=image.height, highlightthickness=0,
                             bd=0, bg=T.WHITE, cursor="crosshair")
        self.map.pack()
        self.map.bind("<Button-1>", self._on_map_click)
        self.map.bind("<B1-Motion>", self._on_map_click)
        self.map_legend = tk.Frame(map_box.body, bg=map_box.body.cget("bg"))
        self.map_legend.pack(fill="x", pady=(T.px(6), 0))

        # Magnifier
        zoom_box = XPGroupBox(top, "Magnifier")
        zoom_box.grid(row=0, column=1, sticky="nsew", padx=(pad, 0))
        self.cell = T.px(10)
        size = MAGNIFIER * self.cell
        frame = tk.Frame(zoom_box.body, bg=T.FIELD_BORDER, padx=1, pady=1)
        frame.pack()
        self.zoom = tk.Canvas(frame, width=size, height=size, highlightthickness=0, bd=0, bg=T.WHITE)
        self.zoom.pack()
        self.zoom.bind("<Button-1>", self._on_zoom_click)

        # Selected pixel: before -> after, bit by bit
        pixel_box = XPGroupBox(top, "Selected pixel")
        pixel_box.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(T.px(8), 0))
        pb = pixel_box.body
        self.pixel_title = label(pb, "", font=T.FONT_BOLD, anchor="w")
        self.pixel_title.pack(fill="x")
        self.bit_w = T.px(17)
        self.row_h = T.px(21)
        self._cols = self._columns()
        self.table = tk.Canvas(pb, width=self._cols["end"], height=4 * self.row_h + T.px(2),
                               highlightthickness=0, bd=0, bg=pb.cget("bg"))
        self.table.pack(anchor="w", pady=(T.px(4), 0))
        self.how = label(pb, "", anchor="w", justify="left", wraplength=self._cols["end"])
        self.how.pack(fill="x", pady=(T.px(6), 0))
        self.table_legend = tk.Frame(pb, bg=pb.cget("bg"))
        self.table_legend.pack(fill="x", pady=(T.px(6), 0))

        # Summary, hint and buttons
        self.summary = label(self.body, "", anchor="w", justify="left", wraplength=self._cols["end"])
        self.summary.pack(fill="x", padx=pad + T.px(2), pady=(T.px(8), 0))
        label(self.body, "Click the map or the magnifier to pick a pixel. "
                         "Arrow keys move one pixel; Shift+arrow moves 8.",
              fg=T.TEXT_MUTED, anchor="w").pack(fill="x", padx=pad + T.px(2), pady=(T.px(2), 0))
        buttons = tk.Frame(self.body, bg=T.DIALOG_BG)
        buttons.pack(fill="x", padx=pad, pady=pad)
        self.close_button = XPButton(buttons, "Close", command=self.cancel, default=True)
        self.close_button.pack(side="right")
        XPButton(buttons, "Save Map…", command=self.save_map).pack(side="right", padx=(0, T.px(6)))
        self.compare_button = XPButton(buttons, "Compare with Original…", command=self.compare)
        self.compare_button.pack(side="left")
        self.bind("<Return>", lambda e: self.cancel())
        for key, (dx, dy) in {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}.items():
            self.bind(f"<{key}>", lambda e, d=(dx, dy): self.move(*d))
            self.bind(f"<Shift-{key}>", lambda e, d=(dx, dy): self.move(d[0] * 8, d[1] * 8))

        if original is not None:
            self.set_original(original)
        else:
            self._refresh()
        first = int(np.argmax((self.changed if self.changed is not None else self.used).reshape(-1)))
        self.select(first % self.width, first // self.width)

    # ------------------------------------------------------------ original
    def set_original(self, original: np.ndarray) -> None:
        """Compare with the cover picture as it was before hiding."""
        self.original = original
        self.changed = (original[..., :3] != self.rgb[..., :3]).any(axis=2)
        self.compare_button.set_enabled(False)
        self._refresh()
        if hasattr(self, "x"):
            self.select(self.x, self.y)

    def compare(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Choose the Original Picture",
                                          filetypes=IMAGE_TYPES)
        if not path:
            return
        try:
            original = np.asarray(core.open_image(path, for_encoding=True), dtype=np.uint8)
        except (OSError, StegoError) as exc:
            dialogs.message(self, "Compare with Original", "That picture can't be opened.",
                            kind="error", detail=str(exc))
            return
        problem = self.check_original(original)
        if problem:
            dialogs.message(self, "Compare with Original", problem, kind="warning")
            return
        self.set_original(original)

    def check_original(self, original: np.ndarray) -> str | None:
        """Why ``original`` can't be the cover this picture was made from, if it can't."""
        if original.shape[:2] != self.rgb.shape[:2]:
            return (f"That picture is {original.shape[1]:,} × {original.shape[0]:,} pixels, but this one "
                    f"is {self.width:,} × {self.height:,}. Choose the original cover picture.")
        differs = original[..., :3] != self.rgb[..., :3]
        if not differs.any():
            return "That picture is identical to this one. Choose the cover picture from before hiding."
        outside = int((differs & (self.data.bits == 0)).any(axis=2).sum())
        if outside:
            return (f"That doesn't look like the original: {outside:,} pixels differ in places where "
                    "nothing was hidden. Choose the cover picture this one was made from.")
        return None

    # ------------------------------------------------------------ text
    def _refresh(self) -> None:
        """Redraw everything that depends on whether the original is known."""
        image, _, shown = _fit(self.rgb, self.used, *self._map_size, changed=self.changed)
        self._map_photo = photo(image, cache=False)
        self.map.delete("all")
        self.map.create_image(0, 0, image=self._map_photo, anchor="nw")
        self._draw_callout(shown)
        for legend in (self.map_legend, self.table_legend):
            for child in legend.winfo_children():
                child.destroy()
        if self.changed is None:
            _chip(self.map_legend, HIGHLIGHT_HEX, "Holds hidden data")
            _chip(self.table_legend, HIGHLIGHT_HEX, "Bit that holds hidden data")
        else:
            _chip(self.map_legend, HIGHLIGHT_HEX, "Changed")
            _chip(self.map_legend, KEPT_HEX, "Holds data, unchanged")
            _chip(self.table_legend, HIGHLIGHT_HEX, "Bit changed")
            _chip(self.table_legend, KEPT_HEX, "Hidden bit that already matched")
        self.summary.configure(text=self._summary())

    def _summary(self) -> str:
        d = self.data
        total = self.width * self.height
        share = d.pixels / total if total else 0
        percent = f"{share:.1%}" if share >= 0.001 else "<0.1%"
        planes = ", ".join(str(p) for p in d.planes)
        where = {
            "lsb": f"LSB, {d.depth} bit{'s' if d.depth > 1 else ''} per channel in the lowest "
                   f"bit{'s' if d.depth > 1 else ''}, filled pixel by pixel from the top-left.",
            "bpcs": f"BPCS, {d.blocks:,} noisy 8×8 blocks in bit-plane{'s' if len(d.planes) > 1 else ''} "
                    f"{planes} of the Gray-coded values.",
            "legacy": "the original encode.py format: the lowest bit of the red channel only.",
        }[d.method]
        text = f"{d.used:,} bytes are hidden in {d.pixels:,} of {total:,} pixels ({percent}), using {where}"
        if self.changed is not None:
            moved = int(np.abs(self.original[..., :3].astype(np.int16) - self.rgb[..., :3]).max())
            text += (f" {int(self.changed.sum()):,} of those pixels actually changed; the rest already "
                     f"had the right bits. No colour value moved by more than {moved} (out of 255).")
        return text

    def _how(self, bits: list[core.HiddenBit]) -> str:
        d = self.data
        if not bits:
            return "No hidden data in this pixel" + (", so it didn't change." if self.changed is not None else ".")
        if d.method == "bpcs":
            places = sorted({(hb.channel, hb.plane) for hb in bits})
            where = " and ".join(f"the {CHANNEL_NAMES[c]} channel (bit-plane {p})" for c, p in places)
            blocks = "block" if len(places) == 1 else "blocks"
            text = (f"BPCS chose this pixel's 8×8 {blocks} in {where} because {'it' if len(places) == 1 else 'they'} "
                    f"already looked like noise, and replaced each block's 64 bits with 63 hidden bits "
                    f"plus 1 flag bit (top-left corner).")
            if any(b.kind == "flag" for b in bits):
                text += " This pixel holds that flag: 1 means the block was conjugated."
            elif any(b.conjugated for b in bits):
                text += (" This block was conjugated (flipped in a checkerboard pattern) so it still "
                         "looks like noise; bits marked “flipped” are stored inverted.")
            return text + " Bits are shown in Gray code, which is where BPCS works; the colour value is on the right."
        if d.method == "legacy":
            return "The original encode.py replaced the last bit of the red value with one hidden bit."
        last = "last bit" if d.depth == 1 else f"last {d.depth} bits"
        text = f"LSB replaced the {last} of each colour value with hidden bits."
        if self.changed is not None:
            text += (" Where the old bit already matched the hidden bit, nothing changed (amber), "
                     f"so each value moves by at most {(1 << d.depth) - 1}.")
        else:
            text += " Use Compare with Original… to see the values before hiding."
        return text

    def _what(self, bits: list[core.HiddenBit], gray_value: int) -> str:
        """What the hidden bits in one colour value are, e.g. "1 = bit 3 of letter 'M'"."""
        parts = []
        for hb in bits:
            stored = (gray_value >> hb.plane) & 1
            if hb.kind == "flag":
                parts.append(f"{stored} = block flag ({'conjugated' if stored else 'as is'})")
            elif hb.kind == "padding":
                parts.append(f"{stored} = filler after the data")
            else:
                value = (self.data.stream[hb.byte] >> (7 - hb.bit)) & 1
                flipped = " (flipped)" if hb.inverted else ""
                parts.append(f"{value} = bit {hb.bit + 1} of {self.data.describe_byte(hb.byte)}{flipped}")
        return "; ".join(parts)

    # ------------------------------------------------------------ selection
    def select(self, x: int, y: int) -> None:
        self.x = max(0, min(self.width - 1, x))
        self.y = max(0, min(self.height - 1, y))
        self._draw_marker()
        self._draw_zoom()
        self._draw_table()

    def move(self, dx: int, dy: int) -> str:
        self.select(self.x + dx, self.y + dy)
        return "break"

    def _on_map_click(self, event) -> None:
        x, y = int(event.x / self.scale), int(event.y / self.scale)
        if self.scale < 1:
            # One display pixel covers several image pixels: prefer one with data.
            n = int(np.ceil(1 / self.scale))
            cell = self.used[y:y + n, x:x + n]
            if cell.any():
                dy, dx = np.unravel_index(int(np.argmax(cell)), cell.shape)
                x, y = x + int(dx), y + int(dy)
        self.select(x, y)

    def _on_zoom_click(self, event) -> None:
        half = MAGNIFIER // 2
        self.select(self.x - half + event.x // self.cell, self.y - half + event.y // self.cell)

    # ------------------------------------------------------------ drawing
    def _draw_callout(self, shown: np.ndarray) -> None:
        """Box and label the data when it's too small to spot on the map."""
        rows, cols = np.flatnonzero(shown.any(axis=1)), np.flatnonzero(shown.any(axis=0))
        if not rows.size:
            return
        mh, mw = shown.shape
        x0, x1, y0, y1 = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
        if (x1 - x0) * (y1 - y0) > 0.05 * mw * mh and min(x1 - x0, y1 - y0) >= T.px(6):
            return
        pad = T.px(4)
        bx0, by0 = max(1, x0 - pad), max(1, y0 - pad)
        bx1, by1 = min(mw - 1, x1 + pad), min(mh - 1, y1 + pad)
        self.map.create_rectangle(bx0, by0, bx1, by1, outline=HIGHLIGHT_HEX, width=2)
        text = "Hidden data is here"
        tw, th = T.FONT.measure(text) + T.px(8), T.FONT.metrics("linespace") + T.px(4)
        tx = min(max(1, bx0), mw - tw - 1)
        ty = by1 + T.px(3) if by1 + T.px(3) + th < mh else by0 - T.px(3) - th
        self.map.create_rectangle(tx, ty, tx + tw, ty + th, fill=HIGHLIGHT_HEX, outline="")
        self.map.create_text(tx + T.px(4), ty + th // 2, text=text, anchor="w", fill=T.WHITE,
                             font=T.FONT_BOLD)

    def _draw_marker(self) -> None:
        self.map.delete("marker")
        s = self.scale
        x0, y0 = self.x * s, self.y * s
        x1, y1 = x0 + max(s, 1), y0 + max(s, 1)
        r = T.px(3)
        # Thin and hollow, so it doesn't hide the coloured data pixels under it.
        self.map.create_rectangle(x0 - r, y0 - r, x1 + r, y1 + r, outline="#000000", width=1, tags="marker")
        self.map.create_rectangle(x0 - r - 1, y0 - r - 1, x1 + r + 1, y1 + r + 1, outline="#FFFFFF",
                                  width=1, tags="marker")

    def _draw_zoom(self) -> None:
        z, c, half = self.zoom, self.cell, MAGNIFIER // 2
        z.delete("all")
        for row in range(MAGNIFIER):
            for col in range(MAGNIFIER):
                x, y = self.x - half + col, self.y - half + row
                x0, y0 = col * c, row * c
                if not (0 <= x < self.width and 0 <= y < self.height):
                    z.create_rectangle(x0, y0, x0 + c, y0 + c, fill=T.DIALOG_BG, outline="")
                    continue
                r, g, b = (int(v) for v in self.rgb[y, x, :3])
                z.create_rectangle(x0, y0, x0 + c, y0 + c, fill=f"#{r:02X}{g:02X}{b:02X}", outline="")
                if self.used[y, x]:
                    kept = self.changed is not None and not self.changed[y, x]
                    z.create_rectangle(x0 + 1, y0 + 1, x0 + c - 1, y0 + c - 1,
                                       outline=KEPT_HEX if kept else HIGHLIGHT_HEX, width=2)
        x0 = y0 = half * c
        z.create_rectangle(x0 - 1, y0 - 1, x0 + c + 1, y0 + c + 1, outline="#000000", width=2)
        z.create_rectangle(x0 - 3, y0 - 3, x0 + c + 3, y0 + c + 3, outline="#FFFFFF", width=1)

    def _columns(self) -> dict[str, int]:
        """x positions of the table's columns."""
        w = self.bit_w
        cols = {"name": 0, "before": T.px(20)}
        cols["before_val"] = cols["before"] + 8 * w + T.px(6)
        cols["arrow"] = cols["before_val"] + T.px(32)
        cols["after"] = cols["arrow"] + T.px(22)
        cols["after_val"] = cols["after"] + 8 * w + T.px(6)
        cols["delta"] = cols["after_val"] + T.px(32)
        cols["what"] = cols["delta"] + T.px(50)
        cols["end"] = cols["what"] + T.px(250)
        return cols

    def _cells(self, x0: int, y0: int, value: int, red: int, amber: int) -> None:
        """Eight bit boxes for ``value``, most significant bit on the left."""
        cv, w, h = self.table, self.bit_w, self.row_h - T.px(4)
        for k in range(8):
            bit = 7 - k
            fill = HIGHLIGHT_HEX if red >> bit & 1 else KEPT_HEX if amber >> bit & 1 else T.WHITE
            cx = x0 + k * w
            cv.create_rectangle(cx, y0, cx + w - 1, y0 + h, fill=fill, outline=T.FIELD_BORDER)
            marked = fill != T.WHITE
            cv.create_text(cx + w // 2, y0 + h // 2, text=str(value >> bit & 1),
                           font=T.FONT_BOLD if marked else T.FONT,
                           fill=T.WHITE if fill == HIGHLIGHT_HEX else T.TEXT)

    def _byte_bits(self, x: int, mid: int, hb: core.HiddenBit) -> None:
        """The message byte's 8 bits, with the one stored here picked out."""
        value = self.data.stream[hb.byte]
        cw = T.FONT_BOLD.measure("0") + T.px(1)
        cv = self.table
        cv.create_text(x, mid, text="(", anchor="w", font=T.FONT, fill=T.TEXT_MUTED)
        x += T.FONT.measure("(")
        for k in range(8):
            ours = k == hb.bit
            cv.create_text(x + k * cw, mid, text=str(value >> (7 - k) & 1), anchor="w",
                           font=T.FONT_BOLD if ours else T.FONT,
                           fill=HIGHLIGHT_HEX if ours else T.TEXT_MUTED)
        cv.create_text(x + 8 * cw, mid, text=")", anchor="w", font=T.FONT, fill=T.TEXT_MUTED)

    def _draw_table(self) -> None:
        cv, cols, rh = self.table, self._cols, self.row_h
        cv.delete("all")
        gray = self.data.gray
        after = self.rgb[self.y, self.x, :3].astype(np.int64)
        before = self.original[self.y, self.x, :3].astype(np.int64) if self.original is not None else None
        mask = self.data.bits[self.y, self.x]
        bits = self.data.hidden_bits(self.x, self.y)
        code = " (Gray code)" if gray else ""

        # Header row
        hy = rh // 2
        muted = {"fill": T.TEXT_MUTED, "font": T.FONT, "anchor": "w"}
        if before is not None:
            cv.create_text(cols["before"], hy, text=f"Before{code}", **muted)
            cv.create_text(cols["after"], hy, text=f"After{code}", **muted)
            cv.create_text(cols["delta"], hy, text="Change", **muted)
        else:
            cv.create_text(cols["before"], hy, text=f"Now{code}", **muted)
        cv.create_text(cols["what"], hy, text="Hidden bit = which bit of the message", **muted)

        for i, name in enumerate(CHANNELS):
            y0 = (i + 1) * rh + T.px(2)
            mid = y0 + (rh - T.px(4)) // 2
            cv.create_text(cols["name"], mid, text=name, anchor="w", font=T.FONT_BOLD)
            shown_after = int(after[i] ^ (after[i] >> 1)) if gray else int(after[i])
            hidden = int(mask[i])
            channel_bits = [hb for hb in bits if hb.channel == i]
            what = self._what(channel_bits, int(after[i] ^ (after[i] >> 1)) if gray else int(after[i]))
            if before is None:
                self._cells(cols["before"], y0, shown_after, red=hidden, amber=0)
                cv.create_text(cols["before_val"], mid, text=str(int(after[i])), anchor="w", font=T.FONT)
            else:
                shown_before = int(before[i] ^ (before[i] >> 1)) if gray else int(before[i])
                flipped = shown_before ^ shown_after
                self._cells(cols["before"], y0, shown_before, red=flipped, amber=hidden & ~flipped)
                cv.create_text(cols["before_val"], mid, text=str(int(before[i])), anchor="w", font=T.FONT)
                cv.create_text(cols["arrow"] + T.px(4), mid, text="→", anchor="w", font=T.FONT_BOLD)
                self._cells(cols["after"], y0, shown_after, red=flipped, amber=hidden & ~flipped)
                cv.create_text(cols["after_val"], mid, text=str(int(after[i])), anchor="w", font=T.FONT_BOLD)
                delta = int(after[i] - before[i])
                cv.create_text(cols["delta"], mid, text=f"{delta:+d}".replace("-", "−") if delta else "0",
                               anchor="w",
                               font=T.FONT_BOLD if delta else T.FONT,
                               fill=HIGHLIGHT_HEX if delta else T.TEXT_MUTED)
            cv.create_text(cols["what"], mid, text=what or "—", anchor="w", font=T.FONT,
                           fill=T.TEXT if what else T.TEXT_MUTED, width=cols["end"] - cols["what"])
            data_bits = [hb for hb in channel_bits if hb.kind == "data"]
            if len(channel_bits) == 1 and data_bits:
                self._byte_bits(cols["what"] + T.FONT.measure(what) + T.px(8), mid, data_bits[0])

        self.pixel_title.configure(text=f"Pixel ({self.x:,}, {self.y:,})")
        self.how.configure(text=self._how(bits))

    # ------------------------------------------------------------ save
    def save_map(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Save Map", defaultextension=".png", filetypes=[("PNG image", "*.png")],
            initialfile=f"{Path(self._name).stem}_map.png")
        if path:
            render(self.rgb, self.used, self.changed).save(path)


def show(parent: tk.Misc, name: str, rgb: np.ndarray, data: core.DataMap,
         original: np.ndarray | None = None) -> None:
    window = DataMapWindow(parent, name, rgb, data, original)
    window.show(focus=window.close_button)
