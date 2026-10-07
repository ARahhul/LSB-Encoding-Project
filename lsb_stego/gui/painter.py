"""Low-level Pillow helpers: colours, gradients and anti-aliased masks."""

from __future__ import annotations

from functools import lru_cache
from typing import Sequence

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

SS = 4  # supersampling factor for anti-aliased edges

Stops = Sequence[tuple[float, str]]
RGB = tuple[int, int, int]


def rgb(color: str) -> RGB:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


def mix(a: str, b: str, t: float) -> str:
    """Blend colour ``a`` toward ``b`` by ``t`` (0..1)."""
    ra, rb = rgb(a), rgb(b)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def _interp(stops: Stops, t: np.ndarray) -> np.ndarray:
    pos = np.array([p for p, _ in stops], dtype=float)
    cols = np.array([rgb(c) for _, c in stops], dtype=float)
    out = np.empty(t.shape + (3,))
    for ch in range(3):
        out[..., ch] = np.interp(t, pos, cols[:, ch])
    return out


def _to_image(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr.round(), 0, 255).astype(np.uint8))


def vgradient(w: int, h: int, stops: Stops) -> Image.Image:
    t = (np.arange(h) + 0.5) / max(h, 1)
    rows = _interp(stops, t)
    return _to_image(np.repeat(rows[:, None, :], w, axis=1))


def hgradient(w: int, h: int, stops: Stops) -> Image.Image:
    t = (np.arange(w) + 0.5) / max(w, 1)
    cols = _interp(stops, t)
    return _to_image(np.repeat(cols[None, :, :], h, axis=0))


def dgradient(w: int, h: int, stops: Stops) -> Image.Image:
    """Diagonal gradient from the top-left corner to the bottom-right."""
    ys, xs = np.mgrid[0:h, 0:w]
    t = (xs + ys + 1) / max(w + h, 1)
    return _to_image(_interp(stops, t))


def radial(w: int, h: int, cx: float, cy: float, stops: Stops) -> Image.Image:
    """CSS-style ``radial-gradient(circle at cx cy, ...)`` (farthest corner)."""
    ys, xs = np.mgrid[0:h, 0:w] + 0.5
    ox, oy = cx * w, cy * h
    d = np.hypot(xs - ox, ys - oy)
    far = max(np.hypot(ox - x, oy - y) for x in (0, w) for y in (0, h))
    return _to_image(_interp(stops, d / far))


def rounded_mask(w: int, h: int, radius: float, inset: float = 0,
                 corners: tuple[bool, bool, bool, bool] | None = None,
                 bottom_inset: float | None = None) -> Image.Image:
    """Anti-aliased 'L' mask of a rounded rectangle inset from the edges."""
    bottom = inset if bottom_inset is None else bottom_inset
    big = Image.new("L", (w * SS, h * SS), 0)
    box = (inset * SS, inset * SS, (w - inset) * SS - 1, (h - bottom) * SS - 1)
    if box[2] > box[0] and box[3] > box[1]:
        ImageDraw.Draw(big).rounded_rectangle(
            box, radius=max(0.0, radius) * SS, fill=255, corners=corners)
    return big.resize((w, h), Image.Resampling.BOX)


def ellipse_mask(w: int, h: int, inset: float = 0) -> Image.Image:
    big = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(big).ellipse(
        (inset * SS, inset * SS, (w - inset) * SS - 1, (h - inset) * SS - 1), fill=255)
    return big.resize((w, h), Image.Resampling.BOX)


def ring(outer: Image.Image, inner: Image.Image) -> Image.Image:
    return ImageChops.subtract(outer, inner)


def keep_rows(mask: Image.Image, top: int, bottom: int) -> Image.Image:
    """Copy of ``mask`` with everything outside rows [top, bottom) cleared."""
    out = mask.copy()
    w, h = out.size
    if top > 0:
        out.paste(0, (0, 0, w, top))
    if bottom < h:
        out.paste(0, (0, bottom, w, h))
    return out


def keep_cols(mask: Image.Image, left: int, right: int) -> Image.Image:
    """Copy of ``mask`` with everything outside columns [left, right) cleared."""
    out = mask.copy()
    w, h = out.size
    if left > 0:
        out.paste(0, (0, 0, left, h))
    if right < w:
        out.paste(0, (right, 0, w, h))
    return out


def fill(img: Image.Image, color: str | Image.Image, mask: Image.Image) -> None:
    if isinstance(color, str):
        img.paste(rgb(color) + ((255,) if img.mode == "RGBA" else ()), (0, 0) + img.size, mask)
    else:
        img.paste(color.convert(img.mode), (0, 0), mask)


@lru_cache(maxsize=32)
def font(size: int, bold: bool = True, serif: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if serif:
        names = ("georgiab.ttf", "timesbd.ttf", "DejaVuSerif-Bold.ttf")
    elif bold:
        names = ("tahomabd.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf")
    else:
        names = ("tahoma.ttf", "arial.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_centered_text(img: Image.Image, text: str, fnt, color: str | int,
                       box: tuple[float, float, float, float]) -> None:
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=fnt)
    x = box[0] + (box[2] - box[0] - (right - left)) / 2 - left
    y = box[1] + (box[3] - box[1] - (bottom - top)) / 2 - top
    draw.text((x, y), text, font=fnt, fill=rgb(color) if isinstance(color, str) else color)
