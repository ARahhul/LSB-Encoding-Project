"""The "Where is the data?" window: a map of the pixels that hold hidden data,
a magnifier, and a bit-by-bit view of the selected pixel."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import numpy as np
from PIL import Image

from .. import core
from . import theme as T
from .dialogs import XPDialog
from .widgets import XPButton, XPGroupBox, label, photo

HIGHLIGHT = (232, 52, 12)        # pixels and bits that hold hidden data
HIGHLIGHT_HEX = "#E8340C"
CHANNELS = ("R", "G", "B")
MAGNIFIER = 15                   # pixels across the magnifier
METHOD_NAMES = {"lsb": "LSB", "bpcs": "BPCS", "legacy": "Old format (red channel LSB)"}


def render(rgb: np.ndarray, used: np.ndarray) -> Image.Image:
    """Full-size map: the picture washed out to grey, data pixels in red."""
    grey = rgb[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    base = (grey * 0.35 + 255 * 0.65).astype(np.uint8)
    out = np.repeat(base[..., None], 3, axis=2)
    out[used] = HIGHLIGHT
    return Image.fromarray(out)


def _fit(rgb: np.ndarray, used: np.ndarray, max_w: int,
         max_h: int) -> tuple[Image.Image, float, np.ndarray]:
    """Map scaled to fit, display pixels per image pixel, and the display mask.

    Shrinking keeps every data pixel visible: a display pixel is red when any
    image pixel under it holds data.
    """
    h, w = used.shape
    scale = min(max_w / w, max_h / h)
    if scale >= 1:
        zoom = max(1, min(int(scale), 16))
        shown = used.repeat(zoom, axis=0).repeat(zoom, axis=1)
        return render(rgb, used).resize((w * zoom, h * zoom), Image.Resampling.NEAREST), float(zoom), shown
    tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    rows = (np.arange(th) * h) // th
    cols = (np.arange(tw) * w) // tw
    small_used = np.maximum.reduceat(np.maximum.reduceat(used.astype(np.uint8), rows, axis=0),
                                     cols, axis=1).astype(bool)
    small = np.asarray(Image.fromarray(np.ascontiguousarray(rgb[..., :3])).resize(
        (tw, th), Image.Resampling.BOX))
    return render(small, small_used), tw / w, small_used


class DataMapWindow(XPDialog):
    def __init__(self, parent: tk.Misc, name: str, rgb: np.ndarray, data: core.DataMap) -> None:
        super().__init__(parent, f"Where the data is hidden: {name}")
        self.rgb = rgb
        self.data = data
        self.used = data.bits.any(axis=2)
        self.height, self.width = self.used.shape
        self._name = name
        pad = T.px(10)

        top = tk.Frame(self.body, bg=T.DIALOG_BG)
        top.pack(fill="both", expand=True, padx=pad, pady=(pad, 0))

        # Map
        map_box = XPGroupBox(top, "Map")
        map_box.grid(row=0, column=0, sticky="nsew")
        image, self.scale, shown = _fit(rgb, self.used, T.px(400), T.px(300))
        self._map_photo = photo(image, cache=False)
        # The border goes around the canvas, not over the picture's edge rows,
        # where LSB data starts.
        frame = tk.Frame(map_box.body, bg=T.FIELD_BORDER, padx=1, pady=1)
        frame.pack()
        self.map = tk.Canvas(frame, width=image.width, height=image.height, highlightthickness=0,
                             bd=0, bg=T.WHITE, cursor="crosshair")
        self.map.pack()
        self.map.create_image(0, 0, image=self._map_photo, anchor="nw")
        self._draw_callout(shown)
        self.map.bind("<Button-1>", self._on_map_click)
        self.map.bind("<B1-Motion>", self._on_map_click)
        legend = tk.Frame(map_box.body, bg=map_box.body.cget("bg"))
        legend.pack(fill="x", pady=(T.px(6), 0))
        tk.Frame(legend, width=T.px(10), height=T.px(10), bg=HIGHLIGHT_HEX).pack(side="left")
        label(legend, "  Holds hidden data", anchor="w").pack(side="left")

        # Magnifier + pixel bits
        right = tk.Frame(top, bg=T.DIALOG_BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(pad, 0))
        zoom_box = XPGroupBox(right, "Magnifier")
        zoom_box.pack(fill="x")
        self.cell = T.px(10)
        size = MAGNIFIER * self.cell
        frame = tk.Frame(zoom_box.body, bg=T.FIELD_BORDER, padx=1, pady=1)
        frame.pack()
        self.zoom = tk.Canvas(frame, width=size, height=size, highlightthickness=0, bd=0, bg=T.WHITE)
        self.zoom.pack()
        self.zoom.bind("<Button-1>", self._on_zoom_click)

        bits_box = XPGroupBox(right, "Selected pixel")
        bits_box.pack(fill="x", pady=(T.px(8), 0))
        self.pixel_title = label(bits_box.body, "", font=T.FONT_BOLD, anchor="w")
        self.pixel_title.pack(fill="x")
        self.bit_w = T.px(15)
        self.bits = tk.Canvas(bits_box.body, width=T.px(30) + 8 * self.bit_w + T.px(34),
                              height=3 * T.px(19) + T.px(4), highlightthickness=0, bd=0,
                              bg=bits_box.body.cget("bg"))
        self.bits.pack(anchor="w", pady=(T.px(4), 0))
        self.pixel_note = label(bits_box.body, "", fg=T.TEXT_MUTED, anchor="w", justify="left",
                                wraplength=T.px(190))
        self.pixel_note.pack(fill="x", pady=(T.px(4), 0))

        top.grid_columnconfigure(0, weight=1)

        # Summary, hint and buttons
        label(self.body, self._summary(), anchor="w", justify="left",
              wraplength=T.px(560)).pack(fill="x", padx=pad + T.px(2), pady=(T.px(8), 0))
        label(self.body, "Click the map or the magnifier to pick a pixel. "
                         "Arrow keys move one pixel; Shift+arrow moves 8.",
              fg=T.TEXT_MUTED, anchor="w").pack(fill="x", padx=pad + T.px(2), pady=(T.px(2), 0))
        buttons = tk.Frame(self.body, bg=T.DIALOG_BG)
        buttons.pack(fill="x", padx=pad, pady=pad)
        self.close_button = XPButton(buttons, "Close", command=self.cancel, default=True)
        self.close_button.pack(side="right")
        XPButton(buttons, "Save Map…", command=self.save_map).pack(side="right", padx=(0, T.px(6)))
        self.bind("<Return>", lambda e: self.cancel())
        for key, (dx, dy) in {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}.items():
            self.bind(f"<{key}>", lambda e, d=(dx, dy): self.move(*d))
            self.bind(f"<Shift-{key}>", lambda e, d=(dx, dy): self.move(d[0] * 8, d[1] * 8))

        first = int(np.argmax(self.used.reshape(-1)))
        self.select(first % self.width, first // self.width)

    # ------------------------------------------------------------ text
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
        return (f"{d.used:,} bytes are hidden in {d.pixels:,} of {total:,} pixels ({percent}), "
                f"using {where}")

    # ------------------------------------------------------------ selection
    def select(self, x: int, y: int) -> None:
        self.x = max(0, min(self.width - 1, x))
        self.y = max(0, min(self.height - 1, y))
        self._draw_marker()
        self._draw_zoom()
        self._draw_bits()

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
        # Thin and hollow, so it doesn't hide the red data pixels under it.
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
                    z.create_rectangle(x0 + 1, y0 + 1, x0 + c - 1, y0 + c - 1, outline=HIGHLIGHT_HEX, width=2)
        x0 = y0 = half * c
        z.create_rectangle(x0 - 1, y0 - 1, x0 + c + 1, y0 + c + 1, outline="#000000", width=2)
        z.create_rectangle(x0 - 3, y0 - 3, x0 + c + 3, y0 + c + 3, outline="#FFFFFF", width=1)

    def _draw_bits(self) -> None:
        cv, w = self.bits, self.bit_w
        cv.delete("all")
        rh = T.px(19)
        mask = self.data.bits[self.y, self.x]
        values = self.rgb[self.y, self.x, :3].astype(np.uint8)
        if self.data.gray:
            values = values ^ (values >> 1)
        for i, (name, value, m) in enumerate(zip(CHANNELS, values, mask)):
            y0 = i * rh + T.px(2)
            cv.create_text(0, y0 + rh // 2, text=name, anchor="w", font=T.FONT_BOLD)
            for k in range(8):
                bit = 7 - k                          # most significant bit on the left
                x0 = T.px(22) + k * w
                hidden = (int(m) >> bit) & 1
                cv.create_rectangle(x0, y0, x0 + w - 1, y0 + rh - T.px(3),
                                    fill=HIGHLIGHT_HEX if hidden else T.WHITE, outline=T.FIELD_BORDER)
                cv.create_text(x0 + w // 2, y0 + (rh - T.px(3)) // 2, text=str((int(value) >> bit) & 1),
                               font=T.FONT_BOLD if hidden else T.FONT,
                               fill=T.WHITE if hidden else T.TEXT)
            cv.create_text(T.px(26) + 8 * w, y0 + rh // 2, text=str(int(value)), anchor="w", font=T.FONT)

        self.pixel_title.configure(text=f"Pixel ({self.x:,}, {self.y:,})")
        count = sum(bin(int(m)).count("1") for m in mask)
        if not count:
            note = "No hidden data in this pixel."
        else:
            note = f"Red bits hold hidden data ({count} of 24 bits here)."
            if self.data.gray:
                note += " BPCS works on the Gray-coded values shown."
        self.pixel_note.configure(text=note)

    # ------------------------------------------------------------ save
    def save_map(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Save Map", defaultextension=".png", filetypes=[("PNG image", "*.png")],
            initialfile=f"{Path(self._name).stem}_map.png")
        if path:
            render(self.rgb, self.used).save(path)


def show(parent: tk.Misc, name: str, rgb: np.ndarray, data: core.DataMap) -> None:
    window = DataMapWindow(parent, name, rgb, data)
    window.show(focus=window.close_button)
