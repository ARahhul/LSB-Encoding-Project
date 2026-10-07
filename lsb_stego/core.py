"""LSB steganography engine.

Data is written into the lowest bits of the red, green and blue channel of
every pixel, row by row. Alpha is never touched.

Container layout (version 2)::

    outer  = MAGIC "LSB\\x02" | flags u8 | length u32 | crc32 u32 | blob[length]
    blob   = inner, optionally zlib-compressed (flag 0x01),
             then optionally AES-256-GCM encrypted (flag 0x02)
    inner  = kind u8 (0 text, 1 file) | name_len u16 | name utf-8 | data

The 13-byte header always uses 1 bit per channel. The blob after it uses
``depth`` bits per channel (flags bits 2-3 hold ``depth - 1``): 1 bit when the
secret fits, otherwise 2, which doubles the room while changing each channel
by at most 3/255.

All integers are big-endian. The CRC covers ``blob`` as stored, so damage is
reported as corruption rather than as a wrong password.

Images written by the original ``encode.py`` (red channel only, terminated by
four NUL bytes) are still readable; see :func:`_decode_legacy`.
"""

from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image, ImageOps

from . import crypto
from .errors import (
    CapacityError,
    CorruptDataError,
    NoHiddenDataError,
    PasswordRequiredError,
    UnsupportedImageError,
)

MAGIC = b"LSB\x02"
HEADER = struct.Struct(">4sBII")
_INNER = struct.Struct(">BH")

FLAG_COMPRESSED = 0x01
FLAG_ENCRYPTED = 0x02
DEPTH_SHIFT = 2
DEPTH_MASK = 0x0C
MAX_DEPTH = 2          # used automatically when 1 bit per channel is not enough
KIND_TEXT = 0
KIND_FILE = 1

MAX_NAME_CHARS = 255
PNG_LEVEL = 3          # as small as level 6 on LSB-noisy pixels, and faster
MAX_DECOMPRESSED = 1 << 30
LEGACY_TERMINATOR = b"\x00" * 4

ImageSource = Union[str, os.PathLike, Image.Image]


@dataclass(frozen=True)
class TextSecret:
    text: str


@dataclass(frozen=True)
class FileSecret:
    name: str
    data: bytes

    @classmethod
    def from_path(cls, path: str | os.PathLike) -> "FileSecret":
        path = Path(path)
        return cls(path.name, path.read_bytes())


Secret = Union[TextSecret, FileSecret]


@dataclass(frozen=True)
class Revealed:
    kind: str                 # "text" or "file"
    data: bytes
    name: str | None = None
    encrypted: bool = False
    compressed: bool = False
    legacy: bool = False      # written by the original encode.py: no integrity check

    @property
    def is_text(self) -> bool:
        return self.kind == "text"

    @property
    def text(self) -> str:
        return self.data.decode("utf-8")


@dataclass(frozen=True)
class EncodeResult:
    path: Path
    used: int          # bytes written, header included
    capacity: int      # bytes the image could hold at ``depth``
    renamed: bool      # the requested extension was replaced with .png
    depth: int = 1     # bits per channel used for the payload


# --------------------------------------------------------------------- images

def open_image(source: ImageSource, *, for_encoding: bool = False) -> Image.Image:
    """Open ``source`` and return it as an RGB or RGBA image."""
    if isinstance(source, Image.Image):
        img = source
    else:
        try:
            img = Image.open(source)
            img.load()
        except FileNotFoundError:
            raise
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
            raise UnsupportedImageError(f"This file can't be opened as an image ({exc}).") from exc
    if for_encoding:
        # Bake the EXIF rotation in so the output looks the way the user saw it.
        img = ImageOps.exif_transpose(img)
    if img.mode in ("RGB", "RGBA"):
        return img
    has_alpha = img.mode in ("LA", "PA", "La") or (img.mode == "P" and "transparency" in img.info)
    if img.mode in ("I;16", "I;16B", "I;16L", "I"):
        img = img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    return img.convert("RGBA" if has_alpha else "RGB")


def capacity_for_size(width: int, height: int, depth: int = MAX_DEPTH) -> int:
    """Bytes (header included) that fit in an image of this size."""
    samples = width * height * 3
    header_samples = HEADER.size * 8
    if samples < header_samples:
        return samples // 8
    return HEADER.size + (samples - header_samples) * depth // 8


def capacity(source: ImageSource, depth: int = MAX_DEPTH) -> int:
    if isinstance(source, Image.Image):
        width, height = source.size
    else:
        with Image.open(source) as img:
            width, height = img.size
    return capacity_for_size(width, height, depth)


def depth_needed(size: int, width: int, height: int, max_depth: int = MAX_DEPTH) -> int | None:
    """Fewest bits per channel that fit ``size`` bytes, or None if none do."""
    for depth in range(1, max_depth + 1):
        if size <= capacity_for_size(width, height, depth):
            return depth
    return None


# ----------------------------------------------------------------- container

def _inner_bytes(secret: Secret) -> bytes:
    if isinstance(secret, TextSecret):
        kind, name, data = KIND_TEXT, b"", secret.text.encode("utf-8")
    elif isinstance(secret, FileSecret):
        base = Path(secret.name).name or "secret.bin"
        kind, name, data = KIND_FILE, base[:MAX_NAME_CHARS].encode("utf-8"), secret.data
    else:
        raise TypeError(f"Unsupported secret type: {type(secret).__name__}")
    return _INNER.pack(kind, len(name)) + name + data


def _compress(inner: bytes) -> tuple[bytes, bool]:
    # Photos, archives and videos are already compressed: probe a sample so a
    # multi-megabyte secret isn't run through zlib for nothing.
    if len(inner) > 256 * 1024:
        probe = inner[:64 * 1024]
        if len(zlib.compress(probe, 1)) > len(probe) * 0.97:
            return inner, False
    packed = zlib.compress(inner, 6)
    return (packed, True) if len(packed) < len(inner) else (inner, False)


def _blob(secret: Secret, password: str | None) -> tuple[bytes, int]:
    blob, compressed = _compress(_inner_bytes(secret))
    flags = FLAG_COMPRESSED if compressed else 0
    if password:
        blob = crypto.encrypt(blob, password, aad=MAGIC)
        flags |= FLAG_ENCRYPTED
    return blob, flags


def _header(flags: int, blob: bytes, depth: int) -> bytes:
    return HEADER.pack(MAGIC, flags | ((depth - 1) << DEPTH_SHIFT), len(blob), zlib.crc32(blob))


def build_container(secret: Secret, password: str | None = None, depth: int = 1) -> bytes:
    blob, flags = _blob(secret, password)
    return _header(flags, blob, depth) + blob


def container_size(secret: Secret, password: str | None = None) -> int:
    """Exact size :func:`build_container` will produce, without running scrypt."""
    blob, _ = _compress(_inner_bytes(secret))
    return HEADER.size + len(blob) + (crypto.OVERHEAD if password else 0)


def _parse_inner(inner: bytes, *, encrypted: bool, compressed: bool) -> Revealed:
    if len(inner) < _INNER.size:
        raise CorruptDataError("The hidden content is truncated.")
    kind, name_len = _INNER.unpack_from(inner)
    start = _INNER.size + name_len
    if kind not in (KIND_TEXT, KIND_FILE) or start > len(inner):
        raise CorruptDataError("The hidden content is malformed.")
    name = inner[_INNER.size:start].decode("utf-8", errors="replace") or None
    return Revealed(
        kind="text" if kind == KIND_TEXT else "file",
        data=inner[start:],
        name=name,
        encrypted=encrypted,
        compressed=compressed,
    )


# ------------------------------------------------------------------ bit I/O

_HEADER_SAMPLES = HEADER.size * 8


def _carrier(img: Image.Image) -> np.ndarray:
    """Flat uint8 array of every R, G and B sample (alpha excluded)."""
    arr = np.asarray(img, dtype=np.uint8)
    return arr[..., :3].reshape(-1)


def _write(samples: np.ndarray, start: int, data: bytes, depth: int) -> None:
    """Store ``data`` in the low ``depth`` bits of samples[start:], MSB first."""
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    if depth == 1:
        values = bits
    else:
        pad = (-bits.size) % depth
        if pad:
            bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
        groups = bits.reshape(-1, depth)
        values = np.zeros(groups.shape[0], dtype=np.uint8)
        for j in range(depth):
            values |= groups[:, j] << np.uint8(depth - 1 - j)
    end = start + values.size
    keep = np.uint8(0xFF ^ ((1 << depth) - 1))
    samples[start:end] = (samples[start:end] & keep) | values


def _read(carrier: np.ndarray, start: int, count: int, depth: int) -> bytes:
    """Inverse of :func:`_write`: ``count`` bytes from samples[start:]."""
    nbits = count * 8
    needed = -(-nbits // depth)
    if start + needed > carrier.size:
        raise CorruptDataError("The hidden content runs past the end of the image.")
    chunk = carrier[start:start + needed]
    if depth == 1:
        bits = chunk & 1
    else:
        bits = np.empty((needed, depth), dtype=np.uint8)
        for j in range(depth):
            bits[:, j] = (chunk >> np.uint8(depth - 1 - j)) & 1
        bits = bits.reshape(-1)[:nbits]
    return np.packbits(bits).tobytes()


# ------------------------------------------------------------------- public

def encode(cover: ImageSource, secret: Secret, out_path: str | os.PathLike,
           password: str | None = None, *, max_depth: int = MAX_DEPTH) -> EncodeResult:
    """Hide ``secret`` in ``cover`` and write a lossless PNG to ``out_path``.

    Uses 1 bit per channel when the secret fits and up to ``max_depth`` bits
    when it doesn't. Any extension other than ``.png`` is replaced, because
    lossy formats such as JPEG would destroy the hidden bits.
    """
    img = open_image(cover, for_encoding=True)
    blob, flags = _blob(secret, password)
    size = HEADER.size + len(blob)
    depth = depth_needed(size, *img.size, max_depth=max_depth)
    if depth is None:
        raise CapacityError(size, capacity_for_size(*img.size, max_depth))

    arr = np.array(img, dtype=np.uint8)
    samples = arr[..., :3].reshape(-1)
    _write(samples, 0, _header(flags, blob, depth), 1)
    _write(samples, _HEADER_SAMPLES, blob, depth)
    arr[..., :3] = samples.reshape(arr.shape[0], arr.shape[1], 3)

    out = Path(out_path)
    renamed = out.suffix.lower() != ".png"
    if renamed:
        out = out.with_suffix(".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)
    return EncodeResult(out, size, capacity_for_size(*img.size, depth), renamed, depth)


def has_container(source: ImageSource) -> bool:
    carrier = _carrier(open_image(source))
    if carrier.size < _HEADER_SAMPLES:
        return False
    return _read(carrier, 0, len(MAGIC), 1) == MAGIC


def decode(source: ImageSource, password: str | None = None) -> Revealed:
    """Extract whatever :func:`encode` (or the original ``encode.py``) hid."""
    img = open_image(source)
    carrier = _carrier(img)

    if carrier.size >= _HEADER_SAMPLES:
        magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))
        if magic == MAGIC:
            depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1
            if length > capacity_for_size(*img.size, depth) - HEADER.size:
                raise CorruptDataError("The hidden content's length is larger than the image.")
            blob = _read(carrier, _HEADER_SAMPLES, length, depth)
            if zlib.crc32(blob) != crc:
                raise CorruptDataError(
                    "The hidden content is damaged. The image was probably edited, "
                    "resized or re-saved in a lossy format after the data was hidden."
                )
            encrypted = bool(flags & FLAG_ENCRYPTED)
            compressed = bool(flags & FLAG_COMPRESSED)
            if encrypted:
                if not password:
                    raise PasswordRequiredError("This content is protected by a password.")
                blob = crypto.decrypt(blob, password, aad=MAGIC)
            if compressed:
                try:
                    inflater = zlib.decompressobj()
                    blob = inflater.decompress(blob, MAX_DECOMPRESSED)
                except zlib.error as exc:
                    raise CorruptDataError("The hidden content could not be decompressed.") from exc
            return _parse_inner(blob, encrypted=encrypted, compressed=compressed)

    return _decode_legacy(img)


# -------------------------------------------------------------------- legacy

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", ".zip"),
    (b"%PDF", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"7z\xbc\xaf\x27\x1c", ".7z"),
    (b"Rar!\x1a\x07", ".rar"),
    (b"\x1f\x8b", ".gz"),
    (b"MZ", ".exe"),
    (b"{\\rtf", ".rtf"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".doc"),
    (b"OggS", ".ogg"),
    (b"ID3", ".mp3"),
    (b"fLaC", ".flac"),
)


def _guess_extension(data: bytes) -> str | None:
    for signature, ext in _SIGNATURES:
        if data.startswith(signature):
            return ext
    if data[:4] == b"RIFF" and data[8:12] in (b"WAVE", b"AVI ", b"WEBP"):
        return {b"WAVE": ".wav", b"AVI ": ".avi", b"WEBP": ".webp"}[data[8:12]]
    if data[4:8] == b"ftyp":
        return ".mp4"
    return None


def _as_printable_text(data: bytes) -> str | None:
    for encoding in ("utf-8", "latin-1"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        printable = sum(ch.isprintable() or ch in "\r\n\t" for ch in text)
        if text and printable / len(text) >= 0.95:
            return text
    return None


def _decode_legacy(img: Image.Image) -> Revealed:
    """Read the original format: red-channel LSBs ending in four NUL bytes.

    That format has no header, so any image "decodes" to something. Results
    that are neither readable text nor a recognisable file type are reported
    as :class:`NoHiddenDataError` with the raw bytes attached as a candidate.
    """
    red = np.asarray(img, dtype=np.uint8)[..., 0].reshape(-1)
    usable = red.size - red.size % 8
    raw = np.packbits(red[:usable] & 1).tobytes()
    end = raw.find(LEGACY_TERMINATOR)
    data = raw[:end] if end > 0 else b""
    if not data:
        raise NoHiddenDataError()

    text = _as_printable_text(data)
    if text is not None:
        return Revealed("text", text.encode("utf-8"), legacy=True)

    ext = _guess_extension(data)
    candidate = Revealed("file", data, name=f"recovered{ext or '.bin'}", legacy=True)
    if ext is None:
        raise NoHiddenDataError(candidate=candidate)
    return candidate
