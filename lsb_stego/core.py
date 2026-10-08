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

BPCS mode (``method="bpcs"``, see :mod:`bpcs`) stores the same header and
blob, with magic ``BPC\\x01`` and no depth bits, inside the picture's noisy
8x8 bit-plane blocks instead. :func:`decode` tells the two apart by magic.

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

from . import bpcs, crypto
from .errors import (
    CapacityError,
    CorruptDataError,
    NoHiddenDataError,
    PasswordRequiredError,
    UnsupportedImageError,
)

MAGIC = b"LSB\x02"
MAGIC_BPCS = b"BPC\x01"
METHODS = ("lsb", "bpcs")
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
    method: str = "lsb"       # "lsb" or "bpcs"

    @property
    def is_text(self) -> bool:
        return self.kind == "text"

    @property
    def text(self) -> str:
        return self.data.decode("utf-8")


@dataclass(frozen=True)
class DataMap:
    """Which bits of which pixels hold hidden data (see :func:`locate`).

    ``bits[y, x, c]`` is a mask over the 8 bits of channel ``c`` (R, G, B) of
    the pixel at (x, y): bit ``k`` set means bit ``k`` carries hidden data. For
    BPCS those are the bits of the Gray-coded value, which is where BPCS works.
    """
    method: str           # "lsb", "bpcs" or "legacy"
    bits: np.ndarray      # (height, width, 3) uint8
    used: int             # bytes stored, header included
    depth: int = 1        # LSB: bits per channel for the payload
    blocks: int = 0       # BPCS: 8x8 blocks holding data

    @property
    def gray(self) -> bool:
        return self.method == "bpcs"

    @property
    def pixels(self) -> int:
        """Pixels with at least one hidden bit."""
        return int(np.count_nonzero(self.bits.any(axis=2)))

    @property
    def planes(self) -> list[int]:
        """Bit positions in use, lowest first."""
        used = int(np.bitwise_or.reduce(self.bits, axis=None)) if self.bits.size else 0
        return [k for k in range(8) if used >> k & 1]


@dataclass(frozen=True)
class EncodeResult:
    path: Path
    used: int          # bytes written, header included
    capacity: int      # bytes the image could hold at ``depth``
    renamed: bool      # the requested extension was replaced with .png
    depth: int = 1     # bits per channel used for the payload (LSB only)
    method: str = "lsb"


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


def bpcs_capacity(source: ImageSource) -> int:
    """Bytes (header included) BPCS can hide. Depends on the picture's content."""
    return bpcs.capacity(np.asarray(open_image(source, for_encoding=True), dtype=np.uint8))


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


def _bpcs_header(flags: int, blob: bytes) -> bytes:
    return HEADER.pack(MAGIC_BPCS, flags, len(blob), zlib.crc32(blob))


def build_container(secret: Secret, password: str | None = None, depth: int = 1) -> bytes:
    blob, flags = _blob(secret, password)
    return _header(flags, blob, depth) + blob


def container_size(secret: Secret, password: str | None = None) -> int:
    """Exact size :func:`build_container` will produce, without running scrypt."""
    blob, _ = _compress(_inner_bytes(secret))
    return HEADER.size + len(blob) + (crypto.OVERHEAD if password else 0)


def _parse_inner(inner: bytes, *, encrypted: bool, compressed: bool, method: str = "lsb") -> Revealed:
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
        method=method,
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
           password: str | None = None, *, max_depth: int = MAX_DEPTH,
           method: str = "lsb") -> EncodeResult:
    """Hide ``secret`` in ``cover`` and write a lossless PNG to ``out_path``.

    ``method`` is ``"lsb"`` (default) or ``"bpcs"``. LSB uses 1 bit per
    channel when the secret fits and up to ``max_depth`` bits when it
    doesn't. BPCS hides in the picture's noisy areas only; see :mod:`bpcs`.
    Any extension other than ``.png`` is replaced, because lossy formats
    such as JPEG would destroy the hidden bits.
    """
    if method not in METHODS:
        raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}.")
    img = open_image(cover, for_encoding=True)
    blob, flags = _blob(secret, password)
    size = HEADER.size + len(blob)
    arr = np.array(img, dtype=np.uint8)

    if method == "bpcs":
        # BPCS only rewrites noisy blocks, so an earlier LSB header in a smooth
        # area would survive and be read first. Break its magic before BPCS
        # picks its blocks (so the change can't shift them).
        samples = arr[..., :3].reshape(-1)
        if samples.size >= _HEADER_SAMPLES and _read(samples, 0, len(MAGIC), 1) == MAGIC:
            arr[0, 0, 0] ^= 1
        room = bpcs.capacity(arr)
        if size > room:
            raise CapacityError(size, room)
        bpcs.embed(arr, _bpcs_header(flags, blob) + blob)
        depth = 1
    else:
        depth = depth_needed(size, *img.size, max_depth=max_depth)
        if depth is None:
            raise CapacityError(size, capacity_for_size(*img.size, max_depth))
        samples = arr[..., :3].reshape(-1)
        _write(samples, 0, _header(flags, blob, depth), 1)
        _write(samples, _HEADER_SAMPLES, blob, depth)
        arr[..., :3] = samples.reshape(arr.shape[0], arr.shape[1], 3)
        room = capacity_for_size(*img.size, depth)

    out = Path(out_path)
    renamed = out.suffix.lower() != ".png"
    if renamed:
        out = out.with_suffix(".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(out, format="PNG", compress_level=PNG_LEVEL)
    return EncodeResult(out, size, room, renamed, depth, method)


def _bpcs_header_of(img: Image.Image) -> tuple[np.ndarray, tuple] | None:
    """The pixel array and unpacked BPCS header, if the picture has one."""
    arr = np.asarray(img, dtype=np.uint8)
    try:
        header = HEADER.unpack(bpcs.extract(arr, HEADER.size))
    except ValueError:
        return None
    return (arr, header) if header[0] == MAGIC_BPCS else None


def detect_method(source: ImageSource) -> str | None:
    """``"lsb"`` or ``"bpcs"`` for a picture holding a container, else None."""
    img = open_image(source)
    carrier = _carrier(img)
    if carrier.size >= _HEADER_SAMPLES and _read(carrier, 0, len(MAGIC), 1) == MAGIC:
        return "lsb"
    return "bpcs" if _bpcs_header_of(img) is not None else None


def has_container(source: ImageSource) -> bool:
    return detect_method(source) is not None


def _open_blob(flags: int, blob: bytes, crc: int, password: str | None,
               method: str) -> Revealed:
    """Check, decrypt and decompress a stored blob (shared by LSB and BPCS)."""
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
    return _parse_inner(blob, encrypted=encrypted, compressed=compressed, method=method)


def decode(source: ImageSource, password: str | None = None, *,
           method: str | None = None) -> Revealed:
    """Extract whatever :func:`encode` (or the original ``encode.py``) hid.

    ``method`` limits the search to ``"lsb"`` (which includes the original
    format) or ``"bpcs"``; by default both are tried and told apart by magic.
    """
    if method is not None and method not in METHODS:
        raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}.")
    img = open_image(source)
    carrier = _carrier(img)

    if method != "bpcs" and carrier.size >= _HEADER_SAMPLES:
        magic, flags, length, crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))
        if magic == MAGIC:
            depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1
            if length > capacity_for_size(*img.size, depth) - HEADER.size:
                raise CorruptDataError("The hidden content's length is larger than the image.")
            blob = _read(carrier, _HEADER_SAMPLES, length, depth)
            return _open_blob(flags, blob, crc, password, "lsb")

    found = _bpcs_header_of(img) if method != "lsb" else None
    if found is not None:
        arr, (_magic, flags, length, crc) = found
        if length > carrier.size // 2:  # BPCS can never use more than half the bits
            raise CorruptDataError("The hidden content's length is larger than the image.")
        try:
            blob = bpcs.extract(arr, HEADER.size + length)[HEADER.size:]
        except ValueError as exc:
            raise CorruptDataError("The hidden content runs past the end of the image.") from exc
        return _open_blob(flags, blob, crc, password, "bpcs")

    if method == "bpcs":
        raise NoHiddenDataError()
    return _decode_legacy(img)


def locate(source: ImageSource, *, method: str | None = None) -> DataMap:
    """Map where :func:`decode` would find hidden data, bit by bit.

    No password is needed: the header that says where the data is isn't
    encrypted. Raises :class:`NoHiddenDataError` if there is nothing to map.
    """
    if method is not None and method not in METHODS:
        raise ValueError(f"Unknown method {method!r}; expected one of {METHODS}.")
    img = open_image(source)
    carrier = _carrier(img)
    h, w = img.height, img.width

    if method != "bpcs" and carrier.size >= _HEADER_SAMPLES:
        magic, flags, length, _crc = HEADER.unpack(_read(carrier, 0, HEADER.size, 1))
        if magic == MAGIC:
            depth = ((flags & DEPTH_MASK) >> DEPTH_SHIFT) + 1
            if length > capacity_for_size(w, h, depth) - HEADER.size:
                raise CorruptDataError("The hidden content's length is larger than the image.")
            flat = np.zeros(carrier.size, dtype=np.uint8)
            flat[:_HEADER_SAMPLES] = 1
            end = _HEADER_SAMPLES + -(-length * 8 // depth)
            flat[_HEADER_SAMPLES:end] = (1 << depth) - 1
            return DataMap("lsb", flat.reshape(h, w, 3), HEADER.size + length, depth)

    found = _bpcs_header_of(img) if method != "lsb" else None
    if found is not None:
        arr, (_magic, _flags, length, _crc) = found
        try:
            bits, blocks = bpcs.bit_map(arr, HEADER.size + length)
        except ValueError as exc:
            raise CorruptDataError("The hidden content runs past the end of the image.") from exc
        return DataMap("bpcs", bits, HEADER.size + length, blocks=blocks)

    if method == "bpcs":
        raise NoHiddenDataError()
    _decode_legacy(img)  # raises NoHiddenDataError unless the old format is plausible
    red = np.asarray(img, dtype=np.uint8)[..., 0].reshape(-1)
    usable = red.size - red.size % 8
    stored = np.packbits(red[:usable] & 1).tobytes().find(LEGACY_TERMINATOR) + len(LEGACY_TERMINATOR)
    bits = np.zeros((h * w, 3), dtype=np.uint8)
    bits[:stored * 8, 0] = 1
    return DataMap("legacy", bits.reshape(h, w, 3), stored)


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
