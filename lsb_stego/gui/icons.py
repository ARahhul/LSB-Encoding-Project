"""Icons drawn with Pillow: app icon, XP message-box icons, small glyphs.

Run ``python -m lsb_stego.gui.icons out.ico`` to write the app icon as .ico.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import painter as P

_BASE = 256  # every icon is drawn at this size, then downsampled


def _down(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _shadow(shape: Image.Image, offset: tuple[int, int], blur: float, opacity: int) -> Image.Image:
    alpha = shape.getchannel("A").point(lambda a: a * opacity // 255)
    shadow = Image.new("RGBA", shape.size, (0, 0, 0, 0))
    shadow.putalpha(alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", shape.size, (0, 0, 0, 0))
    out.paste(shadow, offset, shadow)
    return out


def _layer(size: int = _BASE) -> Image.Image:
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))


def _paint(img: Image.Image, color, mask: Image.Image) -> None:
    P.fill(img, color, mask)


def _shape_mask(size: int, draw_fn) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw_fn(ImageDraw.Draw(mask))
    return mask


# ------------------------------------------------------------------ app icon

def _picture(size: int = _BASE, grey: bool = False) -> Image.Image:
    """A framed landscape photo."""
    img = _layer(size)
    u = size / 256
    frame = (18 * u, 38 * u, 222 * u, 206 * u)
    frame_mask = _shape_mask(size, lambda d: d.rounded_rectangle(frame, radius=14 * u, fill=255))
    framed = _layer(size)
    _paint(framed, "#FFFFFF", frame_mask)
    edge = P.ring(frame_mask, _shape_mask(size, lambda d: d.rounded_rectangle(
        (frame[0] + 4 * u, frame[1] + 4 * u, frame[2] - 4 * u, frame[3] - 4 * u), radius=11 * u, fill=255)))
    _paint(framed, "#9AA7BA", edge)

    photo = (34 * u, 54 * u, 206 * u, 190 * u)
    photo_mask = _shape_mask(size, lambda d: d.rectangle(photo, fill=255))
    _paint(framed, P.vgradient(size, size, ((0, "#2F7DE1"), (0.45, "#8EC5FA"), (0.75, "#DDF0FF"), (1, "#DDF0FF"))),
           photo_mask)
    sun = _shape_mask(size, lambda d: d.ellipse((150 * u, 70 * u, 188 * u, 108 * u), fill=255))
    _paint(framed, P.dgradient(size, size, ((0, "#FFF6B0"), (1, "#FFB800"))),
           Image.composite(sun, Image.new("L", sun.size, 0), photo_mask))
    hill_back = _shape_mask(size, lambda d: d.ellipse((90 * u, 120 * u, 300 * u, 280 * u), fill=255))
    hill_front = _shape_mask(size, lambda d: d.ellipse((-60 * u, 132 * u, 190 * u, 300 * u), fill=255))
    _paint(framed, P.vgradient(size, size, ((0, "#7FCB3E"), (1, "#3E8E1C"))),
           ImageChops.multiply(hill_back, photo_mask))
    _paint(framed, P.vgradient(size, size, ((0, "#9BDB4C"), (1, "#4E9E22"))),
           ImageChops.multiply(hill_front, photo_mask))

    img.alpha_composite(_shadow(framed, (round(6 * u), round(8 * u)), 7 * u, 110))
    img.alpha_composite(framed)
    if grey:
        alpha = img.getchannel("A")
        img = img.convert("L").convert("RGBA")
        img = Image.blend(img, Image.new("RGBA", img.size, (236, 233, 216, 0)), 0.35)
        img.putalpha(alpha.point(lambda a: a * 150 // 255))
    return img


def _padlock(size: int = _BASE) -> Image.Image:
    img = _layer(size)
    u = size / 256
    body = (128 * u, 136 * u, 238 * u, 236 * u)
    shackle_box = (146 * u, 74 * u, 220 * u, 170 * u)
    shackle = _layer(size)
    sd = ImageDraw.Draw(shackle)
    sd.rounded_rectangle(shackle_box, radius=37 * u, outline=P.rgb("#5E6B7A") + (255,), width=round(20 * u))
    inner_box = (shackle_box[0] + 6 * u, shackle_box[1] + 6 * u, shackle_box[2] - 6 * u, shackle_box[3])
    sd.rounded_rectangle(inner_box, radius=31 * u, outline=P.rgb("#C9D2DC") + (255,), width=round(6 * u))
    lock = _layer(size)
    lock.alpha_composite(shackle)
    body_mask = _shape_mask(size, lambda d: d.rounded_rectangle(body, radius=16 * u, fill=255))
    _paint(lock, "#8A5A00", body_mask)
    inner = _shape_mask(size, lambda d: d.rounded_rectangle(
        (body[0] + 6 * u, body[1] + 6 * u, body[2] - 6 * u, body[3] - 6 * u), radius=11 * u, fill=255))
    _paint(lock, P.vgradient(size, size, ((0, "#FFF1A8"), (0.55, "#F6C23E"), (1, "#C98A06"))), inner)
    hole = _shape_mask(size, lambda d: (
        d.ellipse((171 * u, 162 * u, 195 * u, 186 * u), fill=255),
        d.rectangle((179 * u, 178 * u, 187 * u, 208 * u), fill=255)))
    _paint(lock, "#5A3A00", hole)
    img.alpha_composite(_shadow(lock, (round(4 * u), round(6 * u)), 5 * u, 120))
    img.alpha_composite(lock)
    return img


@lru_cache(maxsize=1)
def _app_base() -> Image.Image:
    img = _picture()
    img.alpha_composite(_padlock())
    return img


@lru_cache(maxsize=8)
def app_icon(size: int) -> Image.Image:
    return _down(_app_base(), size)


@lru_cache(maxsize=4)
def picture_icon(size: int, grey: bool = True) -> Image.Image:
    return _down(_picture(grey=grey), size)


# --------------------------------------------------------- message-box icons

def _balloon(glyph: str) -> Image.Image:
    """XP's information / question icon: a white speech balloon."""
    img = _layer()
    u = _BASE / 256
    shape = _shape_mask(_BASE, lambda d: (
        d.ellipse((16 * u, 10 * u, 240 * u, 206 * u), fill=255),
        d.polygon([(60 * u, 170 * u), (40 * u, 246 * u), (120 * u, 196 * u)], fill=255)))
    balloon = _layer()
    _paint(balloon, "#6F8CB8", shape)
    inner = shape.filter(ImageFilter.MinFilter(max(3, round(7 * u)) | 1))
    _paint(balloon, P.dgradient(_BASE, _BASE, ((0, "#FFFFFF"), (0.6, "#F2F6FC"), (1, "#C9D8EF"))), inner)
    img.alpha_composite(_shadow(balloon, (round(6 * u), round(9 * u)), 8 * u, 90))
    img.alpha_composite(balloon)
    fnt = P.font(round((150 if glyph == "i" else 160) * u), serif=True)
    glyph_mask = Image.new("L", (_BASE, _BASE), 0)
    P.draw_centered_text(glyph_mask, glyph, fnt, 255, (16 * u, 4 * u, 240 * u, 206 * u))
    _paint(img, "#1E5CD6", glyph_mask)
    return img


def _warning() -> Image.Image:
    img = _layer()
    u = _BASE / 256
    pts = [(128 * u, 14 * u), (246 * u, 226 * u), (10 * u, 226 * u)]
    outer = _shape_mask(_BASE, lambda d: d.polygon(pts, fill=255)).filter(ImageFilter.GaussianBlur(2 * u))
    outer = outer.point(lambda v: 255 if v > 90 else v * 255 // 90)
    tri = _layer()
    _paint(tri, "#9C6A00", outer)
    inner = outer.filter(ImageFilter.MinFilter(max(3, round(11 * u)) | 1))
    _paint(tri, P.vgradient(_BASE, _BASE, ((0, "#FFF7B8"), (0.45, "#FFDD3C"), (1, "#F0B000"))), inner)
    img.alpha_composite(_shadow(tri, (round(5 * u), round(8 * u)), 7 * u, 100))
    img.alpha_composite(tri)
    mark = _shape_mask(_BASE, lambda d: (
        d.rounded_rectangle((114 * u, 74 * u, 142 * u, 168 * u), radius=10 * u, fill=255),
        d.ellipse((112 * u, 180 * u, 144 * u, 212 * u), fill=255)))
    _paint(img, "#1A1A1A", mark)
    return img


def _error() -> Image.Image:
    img = _layer()
    u = _BASE / 256
    circle = _shape_mask(_BASE, lambda d: d.ellipse((14 * u, 14 * u, 242 * u, 242 * u), fill=255))
    disc = _layer()
    _paint(disc, "#8F0A00", circle)
    inner = _shape_mask(_BASE, lambda d: d.ellipse((22 * u, 22 * u, 234 * u, 234 * u), fill=255))
    _paint(disc, P.radial(_BASE, _BASE, 0.32, 0.28, ((0, "#FFB3A6"), (0.35, "#F05A45"), (0.75, "#D11A08"), (1, "#A10F02"))),
           inner)
    img.alpha_composite(_shadow(disc, (round(5 * u), round(8 * u)), 7 * u, 100))
    img.alpha_composite(disc)
    cross = _shape_mask(_BASE, lambda d: (
        d.line([(84 * u, 84 * u), (172 * u, 172 * u)], fill=255, width=round(30 * u)),
        d.line([(172 * u, 84 * u), (84 * u, 172 * u)], fill=255, width=round(30 * u))))
    _paint(img, "#FFFFFF", cross)
    return img


@lru_cache(maxsize=16)
def message_icon(kind: str, size: int) -> Image.Image:
    """``kind``: info | question | warning | error."""
    if kind == "info":
        base = _balloon("i")
    elif kind == "question":
        base = _balloon("?")
    elif kind == "warning":
        base = _warning()
    else:
        base = _error()
    return _down(base, size)


# --------------------------------------------------------------- small glyphs

@lru_cache(maxsize=8)
def document_icon(size: int) -> Image.Image:
    """Generic XP document: white page, folded corner, a few text lines."""
    img = _layer()
    u = _BASE / 256
    page_pts = [(50 * u, 16 * u), (164 * u, 16 * u), (214 * u, 66 * u), (214 * u, 240 * u), (50 * u, 240 * u)]
    page_mask = _shape_mask(_BASE, lambda d: d.polygon(page_pts, fill=255))
    page = _layer()
    _paint(page, "#7A8DA8", page_mask)
    inner = page_mask.filter(ImageFilter.MinFilter(max(3, round(9 * u)) | 1))
    _paint(page, P.dgradient(_BASE, _BASE, ((0, "#FFFFFF"), (1, "#E4EAF4"))), inner)
    fold = _shape_mask(_BASE, lambda d: d.polygon([(164 * u, 16 * u), (164 * u, 66 * u), (214 * u, 66 * u)], fill=255))
    _paint(page, "#C3CEDF", fold)
    lines = _shape_mask(_BASE, lambda d: [
        d.rectangle((78 * u, y * u, (186 if i % 3 != 2 else 150) * u, (y + 9) * u), fill=255)
        for i, y in enumerate(range(96, 220, 24))])
    _paint(page, "#8FA6C8", lines)
    img.alpha_composite(_shadow(page, (round(5 * u), round(7 * u)), 6 * u, 90))
    img.alpha_composite(page)
    return _down(img, size)


def write_ico(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    images = [app_icon(s) for s in sizes]
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[:-1])
    return path


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "assets/app.ico"
    print(write_ico(target))
