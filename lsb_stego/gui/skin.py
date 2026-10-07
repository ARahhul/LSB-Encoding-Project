"""Renders every Luna control face as a cached Pillow image.

Colours follow the Windows XP "Default (blue)" visual style. All sizes are in
device pixels; callers pass ``scale`` so stroke widths track the DPI.
"""

from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw

from . import painter as P

# ---------------------------------------------------------------- push button

_BUTTON_FACE = {
    "normal": ((0, "#FFFFFF"), (0.86, "#ECEBE5"), (1, "#D8D0C4")),
    "pressed": ((0, "#CDCAC3"), (0.08, "#E3E3DB"), (0.94, "#E5E5DE"), (1, "#F2F2F1")),
    "disabled": ((0, "#F5F4EA"), (1, "#F5F4EA")),
}
_HOVER_RING = ((0, "#FFF0CF"), (0.2, "#FDD889"), (0.55, "#FBC761"), (1, "#E5A01A"))
_FOCUS_RING = ((0, "#CEE7FF"), (0.2, "#98B8EA"), (0.55, "#BCD4F6"), (1, "#89ADE4"))


@lru_cache(maxsize=128)
def button(w: int, h: int, state: str, ring: str | None, bg: str, scale: float) -> Image.Image:
    """``state``: normal | pressed | disabled. ``ring``: None | hover | focus."""
    bw = max(1, round(scale))
    radius = 3 * scale
    img = Image.new("RGB", (w, h), P.rgb(bg))
    outer = P.rounded_mask(w, h, radius)
    inner = P.rounded_mask(w, h, radius - bw, inset=bw)
    P.fill(img, "#C9C7BA" if state == "disabled" else "#003C74", outer)
    P.fill(img, P.vgradient(w, h, _BUTTON_FACE[state]), inner)
    if ring and state != "disabled":
        rw = max(2, round(2 * scale))
        band = P.ring(inner, P.rounded_mask(w, h, radius - bw - rw, inset=bw + rw))
        P.fill(img, P.vgradient(w, h, _HOVER_RING if ring == "hover" else _FOCUS_RING), band)
    return img


# ------------------------------------------------------------ check and radio

def _toggle_fill(state: str) -> tuple:
    if state == "pressed":
        return ((0, "#B0B0A7"), (1, "#E3E1D2"))
    if state == "disabled":
        return ((0, "#FFFFFF"), (1, "#FFFFFF"))
    return ((0, "#DCDCD7"), (1, "#FFFFFF"))


@lru_cache(maxsize=64)
def checkbox(size: int, checked: bool, state: str, scale: float) -> Image.Image:
    """``state``: normal | hover | pressed | disabled."""
    bw = max(1, round(scale))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    full = Image.new("L", (size, size), 255)
    P.fill(img, "#CAC8BB" if state == "disabled" else "#1C5180", full)
    inner = Image.new("L", (size, size), 0)
    inner.paste(255, (bw, bw, size - bw, size - bw))
    P.fill(img, P.dgradient(size, size, _toggle_fill(state)), inner)
    if state == "hover":
        rw = max(2, round(2 * scale))
        core_ = Image.new("L", (size, size), 0)
        core_.paste(255, (bw + rw, bw + rw, size - bw - rw, size - bw - rw))
        P.fill(img, P.dgradient(size, size, ((0, "#FEDF9C"), (1, "#F8B636"))), P.ring(inner, core_))
    if checked:
        k = P.SS * 2
        big = Image.new("L", (size * k, size * k), 0)
        u = size * k / 13.0
        pts = [(3.2 * u, 6.3 * u), (5.4 * u, 8.6 * u), (9.8 * u, 4.0 * u)]
        ImageDraw.Draw(big).line(pts, fill=255, width=max(1, round(2.1 * u)), joint="curve")
        mark = big.resize((size, size), Image.Resampling.BOX)
        P.fill(img, "#A6A6A6" if state == "disabled" else "#21A121", mark)
    return img


@lru_cache(maxsize=64)
def radio(size: int, checked: bool, state: str, scale: float) -> Image.Image:
    bw = max(1, round(scale))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    outer = P.ellipse_mask(size, size)
    inner = P.ellipse_mask(size, size, inset=bw)
    P.fill(img, "#CAC8BB" if state == "disabled" else "#1C5180", outer)
    P.fill(img, P.dgradient(size, size, _toggle_fill(state)), inner)
    if state == "hover":
        rw = max(2, round(2 * scale))
        P.fill(img, P.dgradient(size, size, ((0, "#FEDF9C"), (1, "#F8B636"))),
               P.ring(inner, P.ellipse_mask(size, size, inset=bw + rw)))
    if checked:
        dot_inset = size * 0.31
        dot = P.ellipse_mask(size, size, inset=dot_inset)
        colours = ((0, "#C0C0C0"), (1, "#8A8A8A")) if state == "disabled" else \
            ((0, "#55D551"), (0.5, "#2DB82D"), (1, "#098C09"))
        P.fill(img, P.dgradient(size, size, colours), dot)
    return img


# ----------------------------------------------------------------------- tabs

_TAB_FACE = ((0, "#FFFFFF"), (0.26, "#FAFAF9"), (0.95, "#F0F0EA"), (1, "#ECEBE5"))


@lru_cache(maxsize=32)
def tab(w: int, h: int, selected: bool, hover: bool, bg: str, panel: str, scale: float) -> Image.Image:
    bw = max(1, round(scale))
    radius = 3 * scale
    corners = (True, True, False, False)
    img = Image.new("RGB", (w, h), P.rgb(bg))
    outer = P.rounded_mask(w, h, radius, corners=corners)
    inner = P.rounded_mask(w, h, radius - bw, inset=bw, corners=corners,
                           bottom_inset=0 if selected else bw)
    P.fill(img, "#919B9C" if selected else "#91A7B4", outer)
    P.fill(img, panel if selected else P.vgradient(w, h, _TAB_FACE), inner)
    if selected or hover:
        P.fill(img, "#E68B2C", P.keep_rows(outer, 0, bw))
        P.fill(img, "#FFC73C", P.keep_rows(inner, bw, bw + max(2, round(2 * scale))))
    return img


# ------------------------------------------------------------------- progress

_BLOCKS = {
    "green": ((0, "#ACEDAD"), (0.14, "#7BE47D"), (0.28, "#4CDA50"), (0.42, "#2ED330"),
              (0.57, "#42D845"), (0.71, "#76E275"), (0.85, "#8FE791"), (1, "#FFFFFF")),
    "yellow": ((0, "#FFF3B0"), (0.14, "#FFE680"), (0.28, "#FFD84A"), (0.42, "#F7C925"),
               (0.57, "#FAD13A"), (0.71, "#FDE070"), (0.85, "#FFE88E"), (1, "#FFFFFF")),
    "red": ((0, "#F9C0C0"), (0.14, "#F08A8A"), (0.28, "#E65050"), (0.42, "#DE3030"),
            (0.57, "#E44848"), (0.71, "#EE7A7A"), (0.85, "#F29393"), (1, "#FFFFFF")),
}


def progress_geometry(w: int, h: int, scale: float) -> tuple[int, int, int, int, int, int]:
    """(left, top, inner_w, inner_h, block_w, step) of the block area."""
    bw = max(1, round(scale))
    left, top = bw + max(1, round(scale)), bw + max(1, round(scale))
    inner_w = w - left - bw - max(2, round(2 * scale))
    inner_h = h - 2 * top
    block = max(4, round(8 * scale))
    step = block + max(2, round(2 * scale))
    return left, top, inner_w, inner_h, block, step


@lru_cache(maxsize=64)
def progress_trough(w: int, h: int, bg: str, scale: float) -> Image.Image:
    bw = max(1, round(scale))
    img = Image.new("RGB", (w, h), P.rgb(bg))
    radius = 4 * scale
    P.fill(img, "#686868", P.rounded_mask(w, h, radius))
    P.fill(img, "#FFFFFF", P.rounded_mask(w, h, radius - bw, inset=bw))
    return img


@lru_cache(maxsize=8)
def progress_block(block_w: int, h: int, color: str) -> Image.Image:
    return P.vgradient(block_w, h, _BLOCKS[color])


def progress(w: int, h: int, blocks: tuple[int, ...], color: str, bg: str, scale: float) -> Image.Image:
    """Trough with blocks drawn at the given block indexes."""
    img = progress_trough(w, h, bg, scale).copy()
    left, top, inner_w, inner_h, block, step = progress_geometry(w, h, scale)
    face = progress_block(block, inner_h, color)
    for i in blocks:
        x = left + i * step
        if 0 <= i and x + block <= left + inner_w:
            img.paste(face, (x, top))
    return img


# ------------------------------------------------------------------ scrollbar

_SCROLL_FACE = {
    "normal": "#C8D6FB",
    "hover": "#D9E5FD",
    "pressed": "#A9C1F7",
    "disabled": "#E6EBF5",
}


@lru_cache(maxsize=32)
def scroll_track(w: int, h: int) -> Image.Image:
    return P.hgradient(w, h, ((0, "#EEEDE5"), (0.25, "#F3F1EC"), (1, "#FEFEFB")))


def _scroll_box(w: int, h: int, state: str, scale: float) -> Image.Image:
    bw = max(1, round(scale))
    img = scroll_track(w, h).copy()
    radius = 2 * scale
    P.fill(img, "#FFFFFF", P.rounded_mask(w, h, radius))
    inner = P.rounded_mask(w, h, radius - bw, inset=bw)
    face = _SCROLL_FACE[state]
    P.fill(img, face, inner)
    if state != "disabled":
        P.fill(img, P.mix(face, "#7C9BE8", 0.18),
               P.keep_cols(inner, w - bw - max(2, round(3 * scale)), w))
        top_left = ImageChops.lighter(P.keep_rows(inner, bw, 2 * bw), P.keep_cols(inner, bw, 2 * bw))
        P.fill(img, "#B7CAF5", top_left)
    return img


@lru_cache(maxsize=32)
def scroll_arrow(size: int, up: bool, state: str, scale: float) -> Image.Image:
    img = _scroll_box(size, size, state, scale)
    k = P.SS * 2
    big = Image.new("L", (size * k, size * k), 0)
    u = size * k / 17.0
    if up:
        pts = [(5 * u, 10 * u), (8.5 * u, 6.5 * u), (12 * u, 10 * u)]
    else:
        pts = [(5 * u, 7 * u), (8.5 * u, 10.5 * u), (12 * u, 7 * u)]
    ImageDraw.Draw(big).line(pts, fill=255, width=max(1, round(2.2 * u)), joint="curve")
    glyph = big.resize((size, size), Image.Resampling.BOX)
    P.fill(img, "#A9B6CF" if state == "disabled" else "#4D6185", glyph)
    return img


@lru_cache(maxsize=32)
def scroll_thumb(w: int, h: int, state: str, scale: float) -> Image.Image:
    img = _scroll_box(w, h, state, scale)
    if h >= 14 * scale:
        draw = ImageDraw.Draw(img)
        gw = max(4, round(7 * scale))
        x0 = (w - gw) // 2
        lines = 4
        gap = max(2, round(2 * scale))
        y0 = h // 2 - lines * gap // 2
        for i in range(lines):
            y = y0 + i * gap
            draw.line([(x0, y), (x0 + gw - 1, y)], fill=P.rgb("#EEF4FE"))
            draw.line([(x0 + 1, y + 1), (x0 + gw, y + 1)], fill=P.rgb("#8CB0F8"))
    return img


# ------------------------------------------------------------- window chrome

_TITLE_ACTIVE = ((0, "#0997FF"), (0.08, "#0053EE"), (0.4, "#0050EE"), (0.88, "#0066FF"),
                 (0.93, "#0066FF"), (0.95, "#005BFF"), (0.96, "#003DD7"), (1, "#003DD7"))
_TITLE_INACTIVE = ((0, "#A6C6F7"), (0.08, "#7D9FE6"), (0.4, "#7A9AE3"), (0.88, "#8FACEB"),
                   (0.93, "#8FACEB"), (0.95, "#86A5E8"), (0.96, "#6F8ED8"), (1, "#6F8ED8"))


@lru_cache(maxsize=8)
def titlebar(w: int, h: int, active: bool, scale: float) -> Image.Image:
    img = P.vgradient(w, h, _TITLE_ACTIVE if active else _TITLE_INACTIVE)
    draw = ImageDraw.Draw(img)
    edge_l = "#3D8AF7" if active else "#B4CBF4"
    edge_r = "#0037C9" if active else "#7D96DA"
    for i in range(max(1, round(scale))):
        draw.line([(i, 0), (i, h)], fill=P.rgb(edge_l))
        draw.line([(w - 1 - i, 0), (w - 1 - i, h)], fill=P.rgb(edge_r))
    return img


_CAPTION_BLUE = ((0, "#0054E9"), (0.55, "#2263D5"), (0.7, "#4479E4"), (0.9, "#A3BBEC"), (1, "#FFFFFF"))
_CAPTION_RED = ((0, "#CC4600"), (0.55, "#DC6527"), (0.7, "#CD7546"), (0.9, "#FFCCB2"), (1, "#FFFFFF"))


@lru_cache(maxsize=32)
def caption_button(size: int, kind: str, state: str, active: bool, scale: float) -> Image.Image:
    """``kind``: close | minimize | help. ``state``: normal | hover | pressed."""
    stops = _CAPTION_RED if kind == "close" else _CAPTION_BLUE
    face = P.radial(size, size, 0.9, 0.9, stops)
    if state == "hover":
        face = Image.blend(face, Image.new("RGB", face.size, (255, 255, 255)), 0.18)
    elif state == "pressed":
        face = Image.blend(face, Image.new("RGB", face.size, (0, 0, 40)), 0.22)
    if not active:
        face = Image.blend(face, Image.new("RGB", face.size, (200, 214, 245)), 0.45)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bw = max(1, round(scale))
    radius = 3 * scale
    P.fill(img, "#FFFFFF", P.rounded_mask(size, size, radius))
    P.fill(img, face, P.rounded_mask(size, size, radius - bw, inset=bw))

    k = P.SS * 2
    big = Image.new("L", (size * k, size * k), 0)
    draw = ImageDraw.Draw(big)
    u = size * k / 21.0
    if kind == "close":
        width = max(1, round(2.3 * u))
        draw.line([(6 * u, 6 * u), (15 * u, 15 * u)], fill=255, width=width)
        draw.line([(15 * u, 6 * u), (6 * u, 15 * u)], fill=255, width=width)
    elif kind == "minimize":
        draw.rectangle([5.5 * u, 13 * u, 12.5 * u, 16 * u], fill=255)
    else:
        P.draw_centered_text(big, "?", P.font(max(8, round(15 * u)), bold=True), 255,
                             (0, 0, size * k, size * k))
    glyph = big.resize((size, size), Image.Resampling.BOX)
    P.fill(img, "#FFFFFF" if active else "#EEF2FC", glyph)
    return img


@lru_cache(maxsize=16)
def group_border(w: int, h: int, top: int, bg: str, scale: float) -> Image.Image:
    bw = max(1, round(scale))
    img = Image.new("RGB", (w, h), P.rgb(bg))
    box = Image.new("RGB", (w, h - top), P.rgb(bg))
    radius = 3 * scale
    P.fill(box, "#D0D0BF", P.rounded_mask(w, h - top, radius))
    P.fill(box, bg, P.rounded_mask(w, h - top, radius - bw, inset=bw))
    img.paste(box, (0, top))
    return img


def dashed_border(w: int, h: int, color: str, bg: str, dash: int, scale: float) -> Image.Image:
    img = Image.new("RGB", (w, h), P.rgb(bg))
    draw = ImageDraw.Draw(img)
    bw = max(1, round(scale))
    c = P.rgb(color)
    for x in range(0, w, dash * 2):
        draw.rectangle([x, 0, min(x + dash, w) - 1, bw - 1], fill=c)
        draw.rectangle([x, h - bw, min(x + dash, w) - 1, h - 1], fill=c)
    for y in range(0, h, dash * 2):
        draw.rectangle([0, y, bw - 1, min(y + dash, h) - 1], fill=c)
        draw.rectangle([w - bw, y, w - 1, min(y + dash, h) - 1], fill=c)
    return img


@lru_cache(maxsize=4)
def checkerboard(w: int, h: int, cell: int) -> Image.Image:
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(225, 225, 225))
    return img


def blocks_for(fraction: float, w: int, h: int, scale: float) -> tuple[int, ...]:
    """Block indexes to light for a determinate progress value."""
    _, _, inner_w, _, block, step = progress_geometry(w, h, scale)
    total = max(1, (inner_w + step - block) // step)
    lit = math.ceil(max(0.0, min(1.0, fraction)) * total) if fraction > 0 else 0
    return tuple(range(lit))
