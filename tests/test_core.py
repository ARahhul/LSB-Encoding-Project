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


# ---------------------------------------------------------------------- BPCS

@pytest.fixture
def photo_cover(tmp_path):
    """Half smooth gradient, half texture: BPCS should only use the texture."""
    rng = np.random.default_rng(3)
    y, x = np.mgrid[0:128, 0:192]
    arr = np.stack([x * 255 // 192, y * 255 // 128, (x + y) % 256], -1).astype(np.int64)
    arr[:, 96:] += rng.integers(-40, 40, (128, 96, 3))
    path = tmp_path / "photo.png"
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path)
    return path


@pytest.mark.parametrize("secret", [
    core.TextSecret("Hello, BPCS! " * 20),
    core.TextSecret(""),
    core.FileSecret("data.bin", os.urandom(3000)),
    core.FileSecret("zeros.bin", bytes(3000)),  # simple blocks: must be conjugated
])
def test_bpcs_roundtrip(photo_cover, tmp_path, secret):
    result = core.encode(photo_cover, secret, tmp_path / "out.png", method="bpcs")
    assert result.method == "bpcs"
    revealed = core.decode(result.path)  # method is detected, not passed
    if isinstance(secret, core.TextSecret):
        assert revealed.is_text and revealed.text == secret.text
    else:
        assert (revealed.name, revealed.data) == (secret.name, secret.data)


def test_bpcs_with_password(photo_cover, tmp_path):
    result = core.encode(photo_cover, core.TextSecret("top secret"), tmp_path / "out.png",
                         "pw", method="bpcs")
    with pytest.raises(PasswordRequiredError):
        core.decode(result.path)
    with pytest.raises(WrongPasswordError):
        core.decode(result.path, "nope")
    assert core.decode(result.path, "pw").text == "top secret"


def test_bpcs_changes_only_the_low_bit_planes(photo_cover, tmp_path):
    result = core.encode(photo_cover, core.FileSecret("r.bin", os.urandom(2000)),
                         tmp_path / "out.png", method="bpcs")
    before = np.asarray(Image.open(photo_cover), dtype=np.int16)
    after = np.asarray(Image.open(result.path), dtype=np.int16)
    assert np.abs(after - before).max() < 1 << core.bpcs.PLANES


def test_bpcs_skips_flat_pictures(tmp_path):
    flat = Image.new("RGB", (64, 64), (120, 130, 140))
    assert core.bpcs_capacity(flat) == 0
    with pytest.raises(CapacityError):
        core.encode(flat, core.TextSecret("x"), tmp_path / "out.png", method="bpcs")


def test_bpcs_capacity_error(photo_cover, tmp_path):
    room = core.bpcs_capacity(photo_cover)
    with pytest.raises(CapacityError):
        core.encode(photo_cover, core.FileSecret("big.bin", os.urandom(room)),
                    tmp_path / "out.png", method="bpcs")


def test_bpcs_detected_and_lsb_unaffected(photo_cover, cover, tmp_path):
    bpcs_out = core.encode(photo_cover, core.TextSecret("a"), tmp_path / "b.png", method="bpcs").path
    lsb_out = core.encode(cover, core.TextSecret("b"), tmp_path / "l.png").path
    assert core.has_container(bpcs_out) and core.has_container(lsb_out)
    assert not core.has_container(photo_cover)
    assert core.decode(lsb_out).text == "b"


def test_unknown_method(cover, tmp_path):
    with pytest.raises(ValueError):
        core.encode(cover, core.TextSecret("x"), tmp_path / "out.png", method="dct")


def test_bpcs_conjugation_restores_complexity():
    from lsb_stego import bpcs

    blocks = bpcs._data_blocks(bytes(64))
    assert (bpcs.complexity(blocks) >= bpcs.THRESHOLD).all()
    assert (blocks[:, 0, 0] == 1).all()  # all-zero data is simple, so every block is flagged


def test_bpcs_over_old_lsb_data_reads_the_new_secret(tmp_path):
    # Flat left half: BPCS leaves it alone, so the old LSB header there must be wiped.
    arr = np.full((128, 192, 3), 120, dtype=np.int64)
    arr[:, 96:] += np.random.default_rng(3).integers(-40, 40, (128, 96, 3))
    src = tmp_path / "c.png"
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(src)
    old = core.encode(src, core.TextSecret("old LSB"), tmp_path / "a.png").path
    new = core.encode(old, core.TextSecret("new BPCS"), tmp_path / "b.png", method="bpcs").path
    assert core.decode(new).text == "new BPCS"


def test_lsb_over_old_bpcs_data_reads_the_new_secret(photo_cover, tmp_path):
    old = core.encode(photo_cover, core.TextSecret("old BPCS"), tmp_path / "a.png", method="bpcs").path
    new = core.encode(old, core.TextSecret("new LSB"), tmp_path / "b.png").path
    assert core.decode(new).text == "new LSB"


def test_decode_with_a_chosen_method(photo_cover, cover, tmp_path):
    bpcs_out = core.encode(photo_cover, core.TextSecret("b"), tmp_path / "b.png", method="bpcs").path
    lsb_out = core.encode(cover, core.TextSecret("l"), tmp_path / "l.png").path
    assert core.detect_method(bpcs_out) == "bpcs" and core.detect_method(lsb_out) == "lsb"
    assert core.detect_method(photo_cover) is None

    assert core.decode(bpcs_out, method="bpcs").method == "bpcs"
    assert core.decode(lsb_out, method="lsb").method == "lsb"
    assert core.decode(bpcs_out).method == "bpcs"  # auto-detect still works
    with pytest.raises(NoHiddenDataError):
        core.decode(lsb_out, method="bpcs")
    with pytest.raises(NoHiddenDataError):
        core.decode(bpcs_out, method="lsb")
    with pytest.raises(ValueError):
        core.decode(lsb_out, method="dct")


# ------------------------------------------------------------------- locate

@pytest.mark.parametrize("method", ["lsb", "bpcs"])
def test_locate_covers_every_changed_bit(photo_cover, tmp_path, method):
    result = core.encode(photo_cover, core.FileSecret("r.bin", os.urandom(1500)),
                         tmp_path / "out.png", method=method)
    data = core.locate(result.path)
    assert data.method == method and data.used == result.used
    before = np.asarray(Image.open(photo_cover), dtype=np.uint8)
    after = np.asarray(Image.open(result.path), dtype=np.uint8)
    if method == "bpcs":  # BPCS works on Gray-coded values
        before, after = before ^ (before >> 1), after ^ (after >> 1)
    changed = before ^ after
    assert not (changed & ~data.bits).any()  # nothing changed outside the map
    assert data.pixels <= data.bits.shape[0] * data.bits.shape[1]


def test_locate_lsb_layout(cover, tmp_path):
    result = core.encode(cover, core.TextSecret("hi"), tmp_path / "out.png")
    data = core.locate(result.path)
    flat = data.bits.reshape(-1)
    stored = core.HEADER.size * 8 + (result.used - core.HEADER.size) * 8
    assert (flat[:stored] == 1).all() and not flat[stored:].any()
    assert data.planes == [0] and data.depth == 1


def test_locate_bpcs_uses_whole_blocks(photo_cover, tmp_path):
    result = core.encode(photo_cover, core.TextSecret("x" * 50), tmp_path / "out.png", method="bpcs")
    data = core.locate(result.path)
    assert data.blocks > 0
    assert data.bits.astype(bool).sum() == data.blocks * 64  # one channel-plane per block


def test_locate_without_data(photo_cover):
    with pytest.raises(NoHiddenDataError):
        core.locate(photo_cover)


def test_locate_legacy(cover, tmp_path):
    out = tmp_path / "legacy.png"
    legacy_encode(cover, b"old school", out)
    data = core.locate(out)
    assert data.method == "legacy" and data.used == len(b"old school") + 4
    assert data.bits[..., 1:].sum() == 0  # red channel only


@pytest.mark.parametrize("method", ["lsb", "bpcs"])
def test_hidden_bits_point_at_the_stored_stream(photo_cover, tmp_path, method):
    result = core.encode(photo_cover, core.TextSecret("Meet at 7pm"), tmp_path / "o.png", method=method)
    data = core.locate(result.path)
    after = np.asarray(Image.open(result.path), dtype=np.uint8)
    values = after ^ (after >> 1) if method == "bpcs" else after
    seen = set()
    for y, x in zip(*np.nonzero(data.bits.any(axis=2))):
        for hb in data.hidden_bits(int(x), int(y)):
            if hb.kind != "data":
                continue
            stored = int(values[y, x, hb.channel]) >> hb.plane & 1
            assert stored ^ hb.inverted == data.stream[hb.byte] >> (7 - hb.bit) & 1
            seen.add(hb.index)
    assert seen == set(range(data.used * 8))  # every stored bit is found exactly where it lives
    assert core.decode(result.path).text == "Meet at 7pm"


def test_describe_byte():
    stream = core.build_container(core.TextSecret("Hé!"))
    data = core.DataMap("lsb", np.zeros((1, 1, 3), np.uint8), len(stream), stream=stream)
    words = [data.describe_byte(i) for i in range(len(stream))]
    assert words[:4] == ["marker 'L'", "marker 'S'", "marker 'B'", "marker 0x02"]
    assert words[4] == "flags byte" and words[5] == "length field" and words[9] == "CRC-32 check"
    assert words[13] == "text/file type" and words[14] == words[15] == "name length"
    assert words[16:] == ["letter 'H'", "letter 'é'", "letter 'é'", "letter '!'"]
    locked = core.build_container(core.TextSecret("x"), password="pw")
    data = core.DataMap("lsb", np.zeros((1, 1, 3), np.uint8), len(locked), stream=locked)
    assert data.describe_byte(core.HEADER.size) == "encrypted byte"

