import os
import zlib

import numpy as np
import pytest
from PIL import Image

from lsb_stego import core
from lsb_stego.errors import (
    CapacityError,
    CorruptDataError,
    NoHiddenDataError,
    PasswordRequiredError,
    UnsupportedImageError,
    WrongPasswordError,
)


@pytest.fixture
def cover(tmp_path):
    rng = np.random.default_rng(42)
    path = tmp_path / "cover.png"
    Image.fromarray(rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)).save(path)
    return path


def roundtrip(cover, secret, tmp_path, password=None):
    result = core.encode(cover, secret, tmp_path / "out.png", password)
    return result, core.decode(result.path, password)


def legacy_encode(cover_path, data: bytes, out_path):
    """The original encode.py algorithm: red-channel LSB + four NUL bytes."""
    img = Image.open(cover_path).convert("RGB")
    bits = "".join(format(b, "08b") for b in data) + "00000000" * 4
    arr = np.array(img)
    red = arr[..., 0].reshape(-1)
    for i, bit in enumerate(bits):
        red[i] = (red[i] & 0xFE) | int(bit)
    arr[..., 0] = red.reshape(arr.shape[:2])
    Image.fromarray(arr).save(out_path)


# ------------------------------------------------------------------ round trips

def test_text_roundtrip(cover, tmp_path):
    _, revealed = roundtrip(cover, core.TextSecret("Meet me at 7pm."), tmp_path)
    assert revealed.is_text and revealed.text == "Meet me at 7pm."
    assert not revealed.encrypted and not revealed.legacy


def test_unicode_text_survives(cover, tmp_path):
    # The original encoder wrote format(ord(c), '08b'), which breaks above U+00FF.
    text = "héllo wörld · 你好 · Привет · 🌍🔐"
    _, revealed = roundtrip(cover, core.TextSecret(text), tmp_path)
    assert revealed.text == text


def test_binary_file_with_null_runs_is_not_truncated(cover, tmp_path):
    # The original decoder stopped at the first four NUL bytes in the data itself.
    data = b"PK\x03\x04" + b"\x00" * 64 + os.urandom(500) + b"\x00\x00\x00\x00\x00" + b"end"
    _, revealed = roundtrip(cover, core.FileSecret("archive.zip", data), tmp_path)
    assert revealed.kind == "file"
    assert revealed.name == "archive.zip"
    assert revealed.data == data


def test_file_name_loses_directories(cover, tmp_path):
    _, revealed = roundtrip(cover, core.FileSecret("..\\..\\evil/notes.txt", b"hi"), tmp_path)
    assert revealed.name == "notes.txt"


def test_empty_text(cover, tmp_path):
    _, revealed = roundtrip(cover, core.TextSecret(""), tmp_path)
    assert revealed.text == ""


def test_repetitive_text_is_compressed(cover, tmp_path):
    secret = core.TextSecret("abc" * 2000)
    assert core.container_size(secret) < 6000
    _, revealed = roundtrip(cover, secret, tmp_path)
    assert revealed.compressed and revealed.text == "abc" * 2000


# ------------------------------------------------------------------- passwords

def test_password_roundtrip(cover, tmp_path):
    _, revealed = roundtrip(cover, core.TextSecret("top secret"), tmp_path, password="hunter2")
    assert revealed.encrypted and revealed.text == "top secret"


def test_password_required(cover, tmp_path):
    result = core.encode(cover, core.TextSecret("x"), tmp_path / "o.png", password="pw")
    with pytest.raises(PasswordRequiredError):
        core.decode(result.path)


def test_wrong_password(cover, tmp_path):
    result = core.encode(cover, core.TextSecret("x"), tmp_path / "o.png", password="pw")
    with pytest.raises(WrongPasswordError):
        core.decode(result.path, "nope")


def test_encryption_hides_the_filename(cover):
    container = core.build_container(core.FileSecret("diary-2026.txt", b"dear diary"), password="pw")
    assert b"diary-2026" not in container


@pytest.mark.parametrize("password", [None, "pw"])
def test_container_size_is_exact(password):
    secret = core.FileSecret("a.bin", os.urandom(1234))
    assert core.container_size(secret, password) == len(core.build_container(secret, password))


# ---------------------------------------------------------------- image handling

def test_capacity_error(cover, tmp_path):
    available = core.capacity(cover)
    with pytest.raises(CapacityError) as info:
        core.encode(cover, core.FileSecret("big.bin", os.urandom(available)), tmp_path / "o.png")
    assert info.value.available == available
    assert info.value.needed > available


def test_lossy_output_extension_is_rewritten(cover, tmp_path):
    result = core.encode(cover, core.TextSecret("x"), tmp_path / "out.jpg")
    assert result.renamed and result.path.suffix == ".png"
    assert core.decode(result.path).text == "x"


def test_jpeg_cover(tmp_path):
    path = tmp_path / "photo.jpg"
    Image.fromarray(np.random.default_rng(1).integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(path)
    result = core.encode(path, core.TextSecret("from a jpeg"), tmp_path / "o.png")
    assert core.decode(result.path).text == "from a jpeg"


@pytest.mark.parametrize("mode", ["L", "LA", "P", "RGBA", "I;16", "1", "CMYK"])
def test_other_image_modes(tmp_path, mode):
    rng = np.random.default_rng(7)
    base = Image.fromarray(rng.integers(0, 256, (64, 64, 4), dtype=np.uint8), "RGBA")
    if mode == "I;16":
        img = Image.fromarray(rng.integers(0, 65535, (64, 64), dtype=np.uint16))
    elif mode == "P":
        img = base.convert("RGB").convert("P")
    else:
        img = base.convert(mode)
    path = tmp_path / ("in.tif" if mode == "CMYK" else "in.png")
    img.save(path)
    result = core.encode(path, core.TextSecret(f"mode {mode}"), tmp_path / "o.png")
    assert core.decode(result.path).text == f"mode {mode}"


def test_alpha_and_appearance_are_preserved(tmp_path):
    rng = np.random.default_rng(3)
    original = rng.integers(0, 256, (80, 80, 4), dtype=np.uint8)
    path = tmp_path / "in.png"
    Image.fromarray(original, "RGBA").save(path)
    result = core.encode(path, core.FileSecret("x.bin", os.urandom(1500)), tmp_path / "o.png")
    encoded = np.asarray(Image.open(result.path))
    assert np.array_equal(encoded[..., 3], original[..., 3])
    assert np.abs(encoded.astype(int) - original.astype(int)).max() <= 1


def test_damage_is_detected(cover, tmp_path):
    secret = core.FileSecret("noise.bin", os.urandom(600))  # incompressible: spans ~10 rows
    result = core.encode(cover, secret, tmp_path / "o.png")
    arr = np.array(Image.open(result.path))
    arr[3, :, :] ^= 1  # flip LSBs inside the stored blob
    Image.fromarray(arr).save(result.path)
    with pytest.raises(CorruptDataError):
        core.decode(result.path)


def test_not_an_image(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    with pytest.raises(UnsupportedImageError):
        core.decode(path)


def test_has_container(cover, tmp_path):
    assert not core.has_container(cover)
    result = core.encode(cover, core.TextSecret("x"), tmp_path / "o.png")
    assert core.has_container(result.path)


# --------------------------------------------------------- capacity / 2-bit mode

def test_small_secrets_use_one_bit(cover, tmp_path):
    result, revealed = roundtrip(cover, core.TextSecret("tiny"), tmp_path)
    assert result.depth == 1


def test_two_bit_mode_when_one_bit_is_not_enough(cover, tmp_path):
    one_bit = core.capacity(cover, 1)
    data = os.urandom(one_bit)  # incompressible and too big for 1 bit per channel
    original = np.asarray(Image.open(cover)).astype(int)
    result, revealed = roundtrip(cover, core.FileSecret("big.bin", data), tmp_path)
    assert result.depth == 2
    assert revealed.data == data
    encoded = np.asarray(Image.open(result.path)).astype(int)
    assert np.abs(encoded - original).max() <= 3


def test_two_bit_mode_with_password(cover, tmp_path):
    data = os.urandom(core.capacity(cover, 1))
    result, revealed = roundtrip(cover, core.FileSecret("big.bin", data), tmp_path, password="pw")
    assert result.depth == 2 and revealed.encrypted and revealed.data == data


def test_capacity_doubles_with_two_bits():
    one, two = core.capacity_for_size(4000, 3000, 1), core.capacity_for_size(4000, 3000, 2)
    assert one == 4000 * 3000 * 3 // 8
    assert two == core.HEADER.size + (4000 * 3000 * 3 - core.HEADER.size * 8) * 2 // 8
    assert core.depth_needed(one, 4000, 3000) == 1
    assert core.depth_needed(one + 1, 4000, 3000) == 2
    assert core.depth_needed(two + 1, 4000, 3000) is None


def test_five_megabyte_secret_in_a_twelve_megapixel_photo(tmp_path):
    """The size a typical phone photo can carry: a 5 MB file in a 4000x3000 cover."""
    rng = np.random.default_rng(12)
    cover_path = tmp_path / "photo.jpg"
    small = rng.integers(0, 256, (750, 1000, 3), dtype=np.uint8)
    Image.fromarray(small).resize((4000, 3000), Image.Resampling.BILINEAR).save(cover_path, quality=90)
    data = rng.bytes(5 * 1024 * 1024)
    result = core.encode(cover_path, core.FileSecret("holiday.jpg", data), tmp_path / "out.png", "pw")
    assert result.depth == 2
    revealed = core.decode(result.path, "pw")
    assert revealed.name == "holiday.jpg" and revealed.data == data


# ---------------------------------------------------------------- legacy format

def test_legacy_text_still_decodes(cover, tmp_path):
    legacy_encode(cover, b"hello from v1", tmp_path / "old.png")
    revealed = core.decode(tmp_path / "old.png")
    assert revealed.legacy and revealed.is_text and revealed.text == "hello from v1"


def test_legacy_file_with_known_signature(cover, tmp_path):
    data = b"%PDF-1.4\n" + bytes(range(1, 200))
    legacy_encode(cover, data, tmp_path / "old.png")
    revealed = core.decode(tmp_path / "old.png")
    assert revealed.legacy and revealed.name == "recovered.pdf" and revealed.data == data


def test_legacy_unknown_binary_is_only_a_candidate(cover, tmp_path):
    data = bytes([0x80 | (i % 120) for i in range(300)])
    legacy_encode(cover, data, tmp_path / "old.png")
    with pytest.raises(NoHiddenDataError) as info:
        core.decode(tmp_path / "old.png")
    assert info.value.candidate is not None and info.value.candidate.data == data


@pytest.mark.parametrize("fill", [0, 255])
def test_plain_images_hold_nothing(tmp_path, fill):
    path = tmp_path / "flat.png"
    Image.new("RGB", (50, 50), (fill, fill, fill)).save(path)
    with pytest.raises(NoHiddenDataError):
        core.decode(path)


def test_header_crc_is_checked_before_password(cover, tmp_path):
    result = core.encode(cover, core.TextSecret("x"), tmp_path / "o.png", password="pw")
    container = core.build_container(core.TextSecret("x"), password="pw")
    _, _, length, crc = core.HEADER.unpack(container[: core.HEADER.size])
    assert crc == zlib.crc32(container[core.HEADER.size:])
    assert core.decode(result.path, "pw").text == "x"
