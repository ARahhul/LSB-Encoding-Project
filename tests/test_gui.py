"""GUI smoke tests: every face renders at common DPI scales, and the main
window builds and validates input without being shown."""

import tkinter as tk

import numpy as np
import pytest
from PIL import Image

from lsb_stego import core
from lsb_stego.gui import icons, skin

SCALES = [1.0, 1.25, 1.5, 2.0]


@pytest.mark.parametrize("scale", SCALES)
def test_skin_renders_at_every_scale(scale):
    px = lambda v: int(round(v * scale))  # noqa: E731
    for state in ("normal", "pressed", "disabled"):
        for ring in (None, "hover", "focus"):
            assert skin.button(px(75), px(23), state, ring, "#ECE9D8", scale).size == (px(75), px(23))
    for checked in (False, True):
        for state in ("normal", "hover", "pressed", "disabled"):
            assert skin.checkbox(px(13), checked, state, scale).size == (px(13), px(13))
            assert skin.radio(px(13), checked, state, scale).size == (px(13), px(13))
    skin.tab(px(60), px(20), True, False, "#ECE9D8", "#FCFCFE", scale)
    skin.tab(px(60), px(20), False, True, "#ECE9D8", "#FCFCFE", scale)
    w, h = px(200), px(14)
    skin.progress(w, h, skin.blocks_for(0.5, w, h, scale), "green", "#ECE9D8", scale)
    for state in ("normal", "hover", "pressed", "disabled"):
        skin.scroll_arrow(px(17), True, state, scale)
        skin.scroll_thumb(px(17), px(40), state, scale)
    skin.titlebar(px(400), px(30), True, scale)
    for kind in ("close", "minimize", "help"):
        skin.caption_button(px(21), kind, "hover", False, scale)
    skin.group_border(px(300), px(100), px(6), "#FCFCFE", scale)


def test_icons_render():
    assert icons.app_icon(32).size == (32, 32)
    for kind in ("info", "question", "warning", "error"):
        assert icons.message_icon(kind, 32).mode == "RGBA"
    assert icons.document_icon(32).size == (32, 32)


def test_ico_file(tmp_path):
    path = icons.write_ico(tmp_path / "app.ico")
    with Image.open(path) as ico:
        assert (256, 256) in ico.info["sizes"] and (16, 16) in ico.info["sizes"]


@pytest.fixture(scope="session")
def tk_root():
    # One interpreter per process: Tcl can fail to re-initialise after a Tk() is destroyed.
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available: {exc}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app_factory(monkeypatch, tk_root):
    from lsb_stego.gui import app as gui_app
    from lsb_stego.gui import theme

    monkeypatch.setattr(gui_app.App, "_present", lambda self: None)
    windows = []

    def make(scale=1.0):
        theme.init(tk_root, scale=scale)
        window = tk.Toplevel(tk_root)
        window.withdraw()
        windows.append(window)
        return gui_app, gui_app.App(window)

    yield make
    for window in windows:
        window.destroy()


@pytest.mark.parametrize("scale", SCALES)
def test_main_window_builds(app_factory, scale):
    _, app = app_factory(scale)
    app.root.update_idletasks()
    assert app.root.winfo_reqwidth() > 300
    assert not app.hide_button.enabled


def test_hide_validation(app_factory):
    gui_app, app = app_factory()
    thumb = Image.new("RGB", (8, 8))
    app.cover = gui_app.LoadedImage(gui_app.Path("c.png"), "c.png", 40, 40, "PNG", thumb, False)
    app.message.text.insert("1.0", "hello")
    app._compute_size()
    assert app.hide_button.enabled

    app.use_password.set(True)
    app._on_password_toggle()
    app._compute_size()
    assert not app.hide_button.enabled and "password" in app.hide_hint.cget("text")
    app.password.set("a")
    app.password2.set("b")
    assert "match" in app.hide_hint.cget("text")
    app.password2.set("a")
    assert app.hide_button.enabled

    app.message.text.insert("end", "x" * 5000 + "".join(chr(0x4E00 + i) for i in range(2000)))
    app._compute_size()
    assert not app.hide_button.enabled and app.hide_hint.cget("text").startswith("Too big")


def test_hide_with_bpcs(app_factory, tmp_path):
    gui_app, app = app_factory()
    thumb = Image.new("RGB", (8, 8))
    app.cover = gui_app.LoadedImage(gui_app.Path("c.png"), "c.png", 40, 40, "PNG", thumb, False,
                                    bpcs_capacity=200)
    app.message.text.insert("1.0", "hello")
    app._compute_size()
    app.method.set("bpcs")
    app._refresh_hide()
    assert app.hide_button.enabled and "BPCS" in app.hide_hint.cget("text")

    app.message.text.insert("end", "".join(chr(0x4E00 + i) for i in range(300)))
    app._compute_size()
    assert not app.hide_button.enabled and app.hide_hint.cget("text").startswith("Too big")

    app.cover = gui_app.LoadedImage(gui_app.Path("c.png"), "c.png", 40, 40, "PNG", thumb, False)
    app._refresh_hide()
    assert not app.hide_button.enabled and "no busy areas" in app.hide_hint.cget("text")


def test_load_image_measures_bpcs_room(tmp_path):
    from lsb_stego.gui import app as gui_app

    src = tmp_path / "c.png"
    Image.fromarray(np.random.default_rng(0).integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(src)
    loaded = gui_app.load_image(src, 32, for_encoding=True)
    assert loaded.bpcs_capacity == core.bpcs_capacity(src) > 0


def _wait_idle(app, timeout=10.0):
    import time

    end = time.time() + timeout
    app.root.update()
    while app._busy and time.time() < end:
        app.root.update()
        time.sleep(0.02)
    assert not app._busy


def _textured(path):
    rng = np.random.default_rng(1)
    Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(path)
    return path


def test_method_switch_applies_to_reveal(app_factory, tmp_path):
    _, app = app_factory()
    src = _textured(tmp_path / "c.png")
    hidden = core.encode(src, core.TextSecret("via BPCS"), tmp_path / "b.png", method="bpcs").path

    app.method.set("lsb")
    app._on_method()
    app.load_reveal(hidden)
    _wait_idle(app)
    assert "(BPCS)" in app.reveal_note.cget("text")
    assert "Switch to BPCS" in app.result_text.cget("text")
    assert app.switch_method_button.winfo_manager() == "grid"

    app.switch_method_button.invoke()  # "Use BPCS"
    _wait_idle(app)
    assert app.method.get() == "bpcs"
    assert app.revealed_text.get_text() == "via BPCS"
    assert app.text_info.cget("text").split(" · ")[1] == "BPCS"


def test_lsb_reveal_with_bpcs_selected_offers_switch(app_factory, tmp_path):
    _, app = app_factory()
    src = _textured(tmp_path / "c.png")
    hidden = core.encode(src, core.TextSecret("via LSB"), tmp_path / "l.png").path
    app.method.set("bpcs")
    app._on_method()
    app.load_reveal(hidden)
    _wait_idle(app)
    assert "Switch to LSB" in app.result_text.cget("text")
    app.method.set("lsb")
    app._on_method()
    _wait_idle(app)
    assert app.revealed_text.get_text() == "via LSB"


def test_reveal_shows_text(app_factory, tmp_path):
    gui_app, app = app_factory()
    src = tmp_path / "c.png"
    Image.fromarray(np.random.default_rng(0).integers(0, 256, (40, 40, 3), dtype=np.uint8)).save(src)
    result = core.encode(src, core.TextSecret("shown in the box"), tmp_path / "o.png")
    app._show_revealed(core.decode(result.path))
    assert app.revealed_text.get_text() == "shown in the box"
    assert "verified" in app.text_info.cget("text")


def test_sounds_synthesise_valid_wavs():
    import io
    import wave

    from lsb_stego.gui import sounds

    for name, make in sounds._SYNTH.items():
        min_secs, max_secs = (3.0, 6.0) if name == "startup" else (0.01, 0.3)
        with wave.open(io.BytesIO(make())) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (2, 2, sounds.RATE)
            assert min_secs <= w.getnframes() / w.getframerate() <= max_secs, name


def test_each_kind_of_key_has_its_own_sound():
    from lsb_stego.gui.sounds import key_sound

    assert key_sound("Return", "\r") == "enter"
    assert key_sound("BackSpace", "\b") == key_sound("Delete", "\x7f") == "backspace"
    assert key_sound("space", " ") == key_sound("Tab", "\t") == "space"
    assert key_sound("A", "A") == "capital"
    assert key_sound("a", "a").startswith("key")
    assert key_sound("a", "a") == key_sound("a", "a")  # a key always plays the same note
    assert len({key_sound(c, c) for c in "asdfgh"}) > 1  # but keys differ from each other
    assert key_sound("Shift_L", "") is None
