"""Interactive command-line tools, matching the prompts of the original scripts.

Run with ``poetry run lsb-encode`` / ``poetry run lsb-decode`` or, as before,
``python encode.py`` / ``python decode.py`` inside the virtual environment.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Callable

from . import core
from .errors import NoHiddenDataError, PasswordRequiredError, StegoError


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _ask(prompt: str) -> str:
    # Explorer's "Copy as path" wraps paths in quotes; accept them as-is.
    return input(prompt).strip().strip('"')


def _run(main: Callable[[], int]) -> int:
    _utf8_console()
    try:
        return main()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 130
    except StegoError as exc:
        print(f"❌ {exc}")
        return 1
    except OSError as exc:
        print(f"❌ {exc.strerror or exc}: {exc.filename or ''}".rstrip(": "))
        return 1


def _encode() -> int:
    image_path = _ask("Enter path to the image (PNG recommended): ")
    if not Path(image_path).is_file():
        print("❌ Image file not found.")
        return 1
    room = core.capacity(image_path, core.MAX_DEPTH) - core.HEADER.size
    best = core.capacity(image_path, 1) - core.HEADER.size
    print(f"ℹ️ This image can hide up to {room:,} bytes "
          f"(up to {best:,} at 1 bit per channel, the least visible).")

    choice = input("Do you want to hide (T)ext or (F)ile? ").strip().lower()
    if choice == "t":
        secret: core.Secret = core.TextSecret(input("Enter the message to hide: "))
    elif choice == "f":
        file_path = _ask("Enter path to the file to hide: ")
        if not Path(file_path).is_file():
            print("❌ File not found.")
            return 1
        secret = core.FileSecret.from_path(file_path)
    else:
        print("❌ Invalid choice. Please enter 'T' or 'F'.")
        return 1

    password = getpass.getpass("Password to encrypt with (leave blank for none): ")
    if password and getpass.getpass("Confirm password: ") != password:
        print("❌ The passwords don't match.")
        return 1

    default = f"{Path(image_path).stem}_hidden.png"
    output = _ask(f"Enter output image filename [{default}]: ") or default
    result = core.encode(image_path, secret, output, password or None)
    if result.renamed:
        print("ℹ️ Saved as PNG: lossy formats such as JPEG would destroy the hidden data.")
    print(f"✅ Data encoded and saved to {result.path} "
          f"({result.used:,} of {result.capacity:,} bytes used, {result.depth} bit per channel)")
    return 0


def _decode() -> int:
    image_path = _ask("Enter path to the encoded image: ")
    if not Path(image_path).is_file():
        print("❌ Image file not found.")
        return 1
    try:
        revealed = core.decode(image_path)
    except PasswordRequiredError:
        revealed = core.decode(image_path, getpass.getpass("🔒 Enter the password: "))
    except NoHiddenDataError as exc:
        if exc.candidate is None:
            raise
        print("ℹ️ No hidden data was found, but there may be data from the old version of this tool.")
        if input("Extract it anyway? (y/N) ").strip().lower() != "y":
            return 1
        revealed = exc.candidate

    if revealed.legacy:
        print("ℹ️ Old format: there is no integrity check, so the result may be noise.")
    if revealed.is_text:
        print("\n🔓 Recovered text content:\n")
        print(revealed.text)
        return 0

    name = revealed.name or "recovered.bin"
    print(f"ℹ️ Recovered a file: {name} ({len(revealed.data):,} bytes).")
    output = _ask(f"Enter filename to save recovered file [{name}]: ") or name
    Path(output).write_bytes(revealed.data)
    print(f"✅ File recovered and saved to {output}")
    return 0


def encode_main() -> int:
    return _run(_encode)


def decode_main() -> int:
    return _run(_decode)
