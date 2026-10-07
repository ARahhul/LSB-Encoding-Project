"""``python -m lsb_stego [image]`` (and the packaged exe) start the GUI."""

from __future__ import annotations

import sys


def _report_missing(exc: ImportError) -> None:
    message = (
        f"A required component is missing ({exc.name or exc}).\n\n"
        "Run setup.bat in the program folder to repair the installation."
    )
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("LSB Steganography", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def main() -> None:
    try:
        from lsb_stego.gui.app import run
    except ImportError as exc:
        _report_missing(exc)
        sys.exit(1)
    run(sys.argv[1:])


if __name__ == "__main__":
    main()
