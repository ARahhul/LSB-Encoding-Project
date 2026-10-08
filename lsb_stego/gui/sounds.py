"""Windows XP style sounds: a startup chime and the button click.

Microsoft's own XP sound files can't ship with the app, so both sounds are
synthesised here and cached as WAV files. To use the real ones, drop
``startup.wav`` and/or ``click.wav`` into the ``sounds`` folder next to the
error log (``%LOCALAPPDATA%\\LSB Steganography\\sounds``); those win. For the
click, Windows' own "Windows Navigation Start.wav" (XP's Start.wav) is used
when present.

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
_VERSION = "1"  # bump when the synthesis changes so stale caches are rewritten

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


_SYNTH = {"startup": startup_wav, "click": click_wav}


def path_for(name: str) -> Path | None:
    """The WAV to play for ``name``: user override, system file, or our own."""
    if name in _paths:
        return _paths[name]
    found: Path | None = None
    override = SOUND_DIR / f"{name}.wav"
    if override.is_file():
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


def play_click() -> None:
    """Button click. Uses PlaySound, so a new click replaces the last one."""
    if not (enabled and IS_WINDOWS):
        return
    path = path_for("click")
    if path is None:
        return
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except RuntimeError:
        pass


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
