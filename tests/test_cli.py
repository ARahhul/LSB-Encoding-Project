import numpy as np
import pytest
from PIL import Image

from lsb_stego import cli


@pytest.fixture
def cover(tmp_path):
    path = tmp_path / "cover.png"
    Image.fromarray(np.random.default_rng(0).integers(0, 256, (60, 60, 3), dtype=np.uint8)).save(path)
    return path


def feed(monkeypatch, answers, passwords=()):
    answers, passwords = iter(answers), iter(passwords)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(passwords))


def test_text_roundtrip(monkeypatch, capsys, cover, tmp_path):
    out = tmp_path / "secret.png"
    feed(monkeypatch, [str(cover), "", "t", "hi there ✓", str(out)], passwords=[""])
    assert cli.encode_main() == 0
    feed(monkeypatch, [f'"{out}"'])
    assert cli.decode_main() == 0
    assert "hi there ✓" in capsys.readouterr().out


def test_file_roundtrip_with_password(monkeypatch, cover, tmp_path):
    payload = tmp_path / "data.bin"
    payload.write_bytes(b"\x00" * 50 + b"payload")
    out = tmp_path / "secret.png"
    feed(monkeypatch, [str(cover), "l", "f", str(payload), str(out)], passwords=["pw", "pw"])
    assert cli.encode_main() == 0
    recovered = tmp_path / "back.bin"
    feed(monkeypatch, [str(out), str(recovered)], passwords=["pw"])
    assert cli.decode_main() == 0
    assert recovered.read_bytes() == payload.read_bytes()


def test_wrong_password_reports_error(monkeypatch, capsys, cover, tmp_path):
    out = tmp_path / "secret.png"
    feed(monkeypatch, [str(cover), "", "t", "x", str(out)], passwords=["pw", "pw"])
    cli.encode_main()
    feed(monkeypatch, [str(out)], passwords=["bad"])
    assert cli.decode_main() == 1
    assert "incorrect" in capsys.readouterr().out


def test_bpcs_roundtrip(monkeypatch, capsys, cover, tmp_path):
    out = tmp_path / "secret.png"
    feed(monkeypatch, [str(cover), "b", "t", "hidden by BPCS", str(out)], passwords=[""])
    assert cli.encode_main() == 0
    assert "BPCS" in capsys.readouterr().out
    feed(monkeypatch, [str(out)])
    assert cli.decode_main() == 0
    assert "hidden by BPCS" in capsys.readouterr().out


def test_invalid_method(monkeypatch, capsys, cover):
    feed(monkeypatch, [str(cover), "x"])
    assert cli.encode_main() == 1
    assert "'L' or 'B'" in capsys.readouterr().out


def test_missing_image(monkeypatch, capsys, tmp_path):
    feed(monkeypatch, [str(tmp_path / "nope.png")])
    assert cli.encode_main() == 1
    assert "not found" in capsys.readouterr().out
