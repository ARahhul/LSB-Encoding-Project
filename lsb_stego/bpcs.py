"""BPCS (Bit-Plane Complexity Segmentation) steganography.

Where LSB writes into the lowest bit of every channel, BPCS hides data only
where the picture is already "noisy", so it can go deeper than the last bit
without visible change, and leaves smooth areas such as sky untouched.

How it works (after Kawaguchi & Eason, 1998):

1. Every R, G and B value is converted to Gray code, so neighbouring
   brightness levels differ in one bit and the bit-planes behave like
   independent black-and-white images.
2. Each bit-plane of each channel is cut into 8x8 blocks. A block's
   *complexity* is the number of black/white borders between neighbouring
   bits, divided by the maximum of 112. Blocks at or above ``ALPHA`` look
   like noise.
3. Noisy blocks are replaced, in order (plane 0 = least significant first,
   then R, G, B, then block row by row), by 8x8 blocks of secret data: 63
   data bits plus one flag bit at the top-left corner.
4. A data block that is itself too simple would no longer be recognised as
   noisy, so it is *conjugated*: XORed with a checkerboard, which turns
   complexity ``a`` into ``1 - a``. The checkerboard sets the corner flag,
   so the reader knows to undo it.

Because every block that carries data is still complex afterwards and every
other block is unchanged, the reader finds exactly the same blocks.

Only the lowest ``PLANES`` bit-planes are used, so no channel changes by more
than 15 levels. How much fits depends on the picture: busy photos can hold more
than LSB, flat graphics hold nothing.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

ALPHA = 0.3            # complexity threshold: blocks at or above it carry data
PLANES = 4             # bit-planes used, from the least significant up
BLOCK = 8
_BORDERS = 2 * BLOCK * (BLOCK - 1)                 # 112 for an 8x8 block
THRESHOLD = int(np.ceil(ALPHA * _BORDERS))         # 34 borders
DATA_BITS = BLOCK * BLOCK - 1                      # 63; bit 0 is the conjugation flag

_idx = np.add.outer(np.arange(BLOCK), np.arange(BLOCK))
CHECKERBOARD = (_idx % 2 == 0).astype(np.uint8)    # 1 at the top-left corner


def _to_gray(values: np.ndarray) -> np.ndarray:
    return values ^ (values >> 1)


def _from_gray(gray: np.ndarray) -> np.ndarray:
    binary = gray.copy()
    shift = 1
    while shift < 8:
        binary ^= binary >> shift
        shift <<= 1
    return binary


def complexity(blocks: np.ndarray) -> np.ndarray:
    """Border count of each (…, 8, 8) block of 0/1 bits (0 to 112)."""
    across = (blocks[..., :, 1:] != blocks[..., :, :-1]).sum(axis=(-2, -1))
    down = (blocks[..., 1:, :] != blocks[..., :-1, :]).sum(axis=(-2, -1))
    return across + down


def _crop(rgb: np.ndarray) -> tuple[int, int]:
    """Height and width of the area covered by whole 8x8 blocks."""
    return rgb.shape[0] // BLOCK * BLOCK, rgb.shape[1] // BLOCK * BLOCK


def _plane_blocks(gray: np.ndarray, channel: int, plane: int) -> np.ndarray:
    """Bit ``plane`` of one channel as an (n, 8, 8) array of blocks, row by row."""
    h, w = gray.shape[:2]
    bits = (gray[:, :, channel] >> plane) & 1
    return bits.reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).swapaxes(1, 2).reshape(-1, BLOCK, BLOCK)


def _store_plane(gray: np.ndarray, channel: int, plane: int, blocks: np.ndarray) -> None:
    """Inverse of :func:`_plane_blocks`: write ``blocks`` back into ``gray``."""
    h, w = gray.shape[:2]
    bits = blocks.reshape(h // BLOCK, w // BLOCK, BLOCK, BLOCK).swapaxes(1, 2).reshape(h, w)
    keep = np.uint8(0xFF ^ (1 << plane))
    gray[:, :, channel] = (gray[:, :, channel] & keep) | (bits.astype(np.uint8) << np.uint8(plane))


def _noisy(gray: np.ndarray) -> Iterator[tuple[int, int, np.ndarray, np.ndarray]]:
    """(plane, channel, blocks, indices of noisy blocks) in embedding order."""
    for plane in range(PLANES):
        for channel in range(3):
            blocks = _plane_blocks(gray, channel, plane)
            yield plane, channel, blocks, np.flatnonzero(complexity(blocks) >= THRESHOLD)


def _gray_area(rgb: np.ndarray) -> np.ndarray:
    h, w = _crop(rgb)
    return _to_gray(np.ascontiguousarray(rgb[:h, :w, :3]))


def capacity(rgb: np.ndarray) -> int:
    """Bytes BPCS can hide in this (height, width, 3 or 4) uint8 array."""
    gray = _gray_area(rgb)
    if gray.size == 0:
        return 0
    blocks = sum(idx.size for *_, idx in _noisy(gray))
    return blocks * DATA_BITS // 8


def _data_blocks(data: bytes) -> np.ndarray:
    """``data`` as (n, 8, 8) blocks: flag bit + 63 data bits, conjugated if simple."""
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    count = -(-bits.size // DATA_BITS)
    padded = np.zeros(count * DATA_BITS, dtype=np.uint8)
    padded[:bits.size] = bits
    flat = np.zeros((count, BLOCK * BLOCK), dtype=np.uint8)
    flat[:, 1:] = padded.reshape(count, DATA_BITS)
    blocks = flat.reshape(count, BLOCK, BLOCK)
    simple = complexity(blocks) < THRESHOLD
    blocks[simple] ^= CHECKERBOARD
    return blocks


def embed(rgb: np.ndarray, data: bytes) -> int:
    """Hide ``data`` in ``rgb`` in place. Returns the blocks used.

    Raises ValueError if the picture doesn't have enough noisy blocks.
    """
    payload = _data_blocks(data)
    h, w = _crop(rgb)
    gray = _gray_area(rgb)
    done = 0
    if gray.size:
        for plane, channel, blocks, idx in _noisy(gray):
            take = idx[:payload.shape[0] - done]
            if take.size:
                blocks[take] = payload[done:done + take.size]
                _store_plane(gray, channel, plane, blocks)
                done += take.size
            if done == payload.shape[0]:
                break
    if done < payload.shape[0]:
        raise ValueError("not enough complex areas in the picture")
    rgb[:h, :w, :3] = _from_gray(gray)
    return done


def _holding(gray: np.ndarray, count: int) -> list[tuple[int, int, np.ndarray, np.ndarray]]:
    """(plane, channel, blocks, indices) of the blocks holding the first ``count`` bytes."""
    needed = -(-count * 8 // DATA_BITS)
    found = []
    have = 0
    if gray.size:
        for plane, channel, blocks, idx in _noisy(gray):
            take = idx[:needed - have]
            if take.size:
                found.append((plane, channel, blocks, take))
                have += take.size
            if have == needed:
                break
    if have < needed:
        raise ValueError("the picture ends before the hidden data does")
    return found


def extract(rgb: np.ndarray, count: int) -> bytes:
    """The first ``count`` bytes hidden by :func:`embed`.

    Raises ValueError if the picture has fewer noisy blocks than that needs.
    """
    found = [blocks[take] for _p, _c, blocks, take in _holding(_gray_area(rgb), count)]
    blocks = np.concatenate(found) if found else np.zeros((0, BLOCK, BLOCK), np.uint8)
    flagged = blocks[:, 0, 0] == 1
    blocks[flagged] ^= CHECKERBOARD
    bits = blocks.reshape(-1, BLOCK * BLOCK)[:, 1:].reshape(-1)[:count * 8]
    return np.packbits(bits).tobytes()


def bit_map(rgb: np.ndarray, count: int) -> tuple[np.ndarray, int]:
    """Where the first ``count`` hidden bytes are, and how many blocks hold them.

    The map is (height, width, 3) uint8: bit ``k`` of ``map[y, x, c]`` is set
    when bit-plane ``k`` of that channel's Gray-coded value carries data.
    """
    out = np.zeros((rgb.shape[0], rgb.shape[1], 3), dtype=np.uint8)
    gray = _gray_area(rgb)
    h, w = gray.shape[:2]
    holding = _holding(gray, count)
    for plane, channel, _blocks, take in holding:
        used = np.zeros((h // BLOCK) * (w // BLOCK), dtype=bool)
        used[take] = True
        used = used.reshape(h // BLOCK, w // BLOCK).repeat(BLOCK, axis=0).repeat(BLOCK, axis=1)
        out[:h, :w, channel] |= used.astype(np.uint8) << np.uint8(plane)
    return out, sum(take.size for *_, take in holding)
