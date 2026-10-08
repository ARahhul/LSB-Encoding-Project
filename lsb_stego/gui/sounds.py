"""Windows XP style sounds: a startup chime, the button click and typing.

Typing has its own sound per kind of key: ordinary keys each keep a note on a
small scale, capital letters, space/Tab, Backspace/Delete and Enter each sound
different.

Microsoft's own XP sound files can't ship with the app, so every sound is
synthesised here and cached as WAV files. To use your own, drop any of
``startup.wav``, ``click.wav``, ``key.wav`` (all ordinary keys), ``capital.wav``,
``space.wav``, ``backspace.wav`` or ``enter.wav`` into the ``sounds`` folder next
to the error log (``%LOCALAPPDATA%\\LSB Steganography\\sounds``); those win. For
the click, Windows' own "Windows Navigation Start.wav" (XP's Start.wav) is
used when present.

Playback is Windows only, like :mod:`winapi`; every function is a silent
no-op elsewhere or when anything goes wrong.
"""

from __future__ import annotations

import io
import os
import sys
import wave
from pathlib import Path

import numpy as np

IS_WINDOWS = sys.platform == "win32"
RATE = 44100
SOUND_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LSB Steganography" / "sounds"
_SYSTEM_CLICK = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Media" / "Windows Navigation Start.wav"
_VERSION = "3"  # bump when the synthesis changes so stale caches are rewritten

enabled = True
_paths: dict[str, Path | None] = {}


# --------------------------------------------------------------- synthesis

def _wav_bytes(samples: np.ndarray) -> bytes:
    """16-bit stereo WAV from a (n, 2) float array in [-1, 1]."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _bell(freq: float, start: float, length: float, total: float, *, attack: float = 0.04,
          decay: float = 1.6, pan: float = 0.0) -> np.ndarray:
    """A soft, slightly detuned bell/pad note placed at ``start`` seconds."""
    out = np.zeros((int(total * RATE), 2))
    n = int(length * RATE)
    t = np.arange(n) / RATE
    env = np.minimum(t / attack, 1.0) * np.exp(-t * decay)
    tone = (np.sin(2 * np.pi * freq * t)
            + 0.5 * np.sin(2 * np.pi * freq * 1.003 * t)
            + 0.25 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t * 3)
            + 0.12 * np.sin(2 * np.pi * freq * 3.0 * t) * np.exp(-t * 6))
    note = tone * env / 1.9
    i = int(start * RATE)
    end = min(i + n, len(out))
    out[i:end, 0] += note[:end - i] * (1 - pan)
    out[i:end, 1] += note[:end - i] * (1 + pan)
    return out


def startup_wav() -> bytes:
    """An XP-flavoured startup chime: warm pad swell, rising bells, soft tail."""
    total = 4.2
    hz = lambda midi: 440.0 * 2 ** ((midi - 69) / 12)  # noqa: E731
    mix = np.zeros((int(total * RATE), 2))
    # Pad: an E-flat major chord swelling in underneath.
    for midi, pan in ((51, -0.3), (58, 0.3), (63, 0.0), (67, -0.2)):
        mix += 0.55 * _bell(hz(midi), 0.0, 3.8, total, attack=0.7, decay=0.9, pan=pan)
    # Rising bell motif on top, like the familiar four-note XP flourish.
    for start, midi, pan in ((0.05, 75, -0.4), (0.45, 70, 0.4), (0.85, 82, -0.2),
                             (1.25, 79, 0.2), (1.25, 87, 0.0)):
        mix += 0.35 * _bell(hz(midi), start, 2.8, total, attack=0.01, decay=1.4, pan=pan)
    # Simple feedback echo for a bit of space.
    delay = int(0.18 * RATE)
    for _ in range(3):
        echo = np.zeros_like(mix)
        echo[delay:] = mix[:-delay] * 0.25
        mix += echo[:, ::-1]
    fade = np.linspace(1.0, 0.0, int(0.6 * RATE))
    mix[-len(fade):] *= fade[:, None]
    return _wav_bytes(mix / max(1e-9, np.abs(mix).max()) * 0.8)


def click_wav() -> bytes:
    """XP's short navigation 'tick': a damped high pop with a tiny body."""
    n = int(0.045 * RATE)
    t = np.arange(n) / RATE
    env = np.exp(-t * 140)
    rng = np.random.default_rng(7)
    sig = (0.6 * np.sin(2 * np.pi * 2300 * t) + 0.4 * np.sin(2 * np.pi * 900 * t)) * env
    sig += 0.25 * rng.uniform(-1, 1, n) * np.exp(-t * 400)
    sig = sig / np.abs(sig).max() * 0.5
    return _wav_bytes(np.column_stack([sig, sig]))


def _tap(tone: float, body: float, length: float, *, decay: float = 220, noise: float = 0.35,
         gain: float = 0.3, sweep: float = 1.0, seed: int = 11) -> np.ndarray:
    """One keyboard tap: a damped tone over a low body and a burst of noise.

    ``sweep`` bends the tone's pitch to ``tone * sweep`` by the end.
    """
    n = int(length * RATE)
    t = np.arange(n) / RATE
    freq = tone * np.power(sweep, t / length)
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    rng = np.random.default_rng(seed)
    sig = 0.5 * np.sin(phase) * np.exp(-t * decay)
    sig += 0.5 * np.sin(2 * np.pi * body * t) * np.exp(-t * decay * 0.7)
    sig += noise * rng.uniform(-1, 1, n) * np.exp(-t * 600)
    return sig / np.abs(sig).max() * gain


def _mono(sig: np.ndarray) -> bytes:
    return _wav_bytes(np.column_stack([sig, sig]))


# Ordinary keys share a small scale; each key always lands on the same note.
KEY_NOTES = (1200.0, 1350.0, 1500.0, 1700.0, 1900.0, 2150.0)


def key_wav(note: int = 2) -> bytes:
    """A soft tap for an ordinary key, pitched at ``KEY_NOTES[note]``."""
    return _mono(_tap(KEY_NOTES[note], 420, 0.03, seed=11 + note))


def capital_wav() -> bytes:
    """Capital letter: a brighter double tap, as if Shift went down too."""
    first = _tap(2600, 520, 0.03, decay=260, gain=0.22, seed=21)
    second = _tap(3000, 520, 0.03, decay=260, gain=0.3, seed=22)
    gap = int(0.012 * RATE)
    out = np.zeros(gap + len(second))
    out[:len(first)] += first
    out[gap:] += second
    return _mono(out / np.abs(out).max() * 0.32)


def space_wav() -> bytes:
    """Space and Tab: the wide bar's deeper, longer thud."""
    return _mono(_tap(650, 210, 0.07, decay=90, noise=0.45, gain=0.32, seed=31))


def backspace_wav() -> bytes:
    """Backspace and Delete: a short tap that falls in pitch."""
    return _mono(_tap(1500, 380, 0.06, decay=120, gain=0.3, sweep=0.45, seed=41))


def enter_wav() -> bytes:
    """Enter: a solid 'thock' with a small XP-style ding on top."""
    total = int(0.22 * RATE)
    out = np.zeros(total)
    thock = _tap(500, 160, 0.08, decay=70, noise=0.5, gain=0.35, seed=51)
    out[:len(thock)] += thock
    t = np.arange(total - int(0.01 * RATE)) / RATE
    ding = (np.sin(2 * np.pi * 1318.5 * t) + 0.3 * np.sin(2 * np.pi * 2637 * t)) * np.exp(-t * 18)
    out[int(0.01 * RATE):] += 0.12 * ding
    return _mono(out / np.abs(out).max() * 0.35)


_SYNTH = {"startup": startup_wav, "click": click_wav, "capital": capital_wav,
          "space": space_wav, "backspace": backspace_wav, "enter": enter_wav,
          **{f"key{i}": (lambda i=i: key_wav(i)) for i in range(len(KEY_NOTES))}}


def path_for(name: str) -> Path | None:
    """The WAV to play for ``name``: user override, system file, or our own."""
    if name in _paths:
        return _paths[name]
    found: Path | None = None
    overrides = [SOUND_DIR / f"{name}.wav"]
    if name.startswith("key"):
        overrides.append(SOUND_DIR / "key.wav")  # one key.wav covers every ordinary key
    override = next((p for p in overrides if p.is_file()), None)
    if override is not None:
        found = override
    elif name == "click" and IS_WINDOWS and _SYSTEM_CLICK.is_file():
        found = _SYSTEM_CLICK
    else:
        cached = SOUND_DIR / ".generated" / f"{name}-v{_VERSION}.wav"
        try:
            if not cached.is_file():
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(_SYNTH[name]())
            found = cached
        except OSError:
            found = None
    _paths[name] = found
    return found


# ---------------------------------------------------------------- playback

if IS_WINDOWS:
    import ctypes
    import winsound

    _winmm = ctypes.WinDLL("winmm")
    _winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]


def _play(name: str) -> None:
    """PlaySound ``name`` asynchronously; a new sound replaces the last one."""
    if not (enabled and IS_WINDOWS):
        return
    path = path_for(name)
    if path is None:
        return
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except RuntimeError:
        pass


def play_click() -> None:
    """Button click."""
    _play("click")


_KEYSYM_SOUNDS = {"Return": "enter", "KP_Enter": "enter", "BackSpace": "backspace",
                  "Delete": "backspace", "Tab": "space", "space": "space"}


def key_sound(keysym: str, char: str) -> str | None:
    """Which sound a key press makes, or None for keys that don't type."""
    if keysym in _KEYSYM_SOUNDS:
        return _KEYSYM_SOUNDS[keysym]
    if not (char and char.isprintable()):
        return None
    if char.isupper():
        return "capital"
    return f"key{ord(char.lower()) % len(KEY_NOTES)}"


def on_key(event) -> None:
    """``<Key>`` handler: play the key's sound when typing into an editable field."""
    import tkinter as tk

    widget = event.widget
    if not isinstance(widget, (tk.Entry, tk.Text)) or str(widget.cget("state")) == "disabled":
        return
    if event.state & 0x4:  # Ctrl shortcuts (copy, paste, select all) are not typing
        return
    name = key_sound(event.keysym, event.char)
    if name:
        _play(name)


def play_startup() -> None:
    """Startup chime. Uses MCI so later button clicks don't cut it off."""
    if not (enabled and IS_WINDOWS):
        return
    path = path_for("startup")
    if path is None:
        return
    try:
        _winmm.mciSendStringW("close lsb_startup", None, 0, None)
        if _winmm.mciSendStringW(f'open "{path}" type waveaudio alias lsb_startup', None, 0, None) == 0:
            _winmm.mciSendStringW("play lsb_startup", None, 0, None)
    except OSError:
        pass


def close() -> None:
    """Release the MCI device opened for the startup chime."""
    if IS_WINDOWS:
        try:
            _winmm.mciSendStringW("close lsb_startup", None, 0, None)
        except OSError:
            pass
