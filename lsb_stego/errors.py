"""Exceptions raised by the steganography engine."""

from __future__ import annotations

from typing import Any


class StegoError(Exception):
    """Base class for every error the engine raises on purpose."""


class UnsupportedImageError(StegoError):
    """The file could not be opened as an image."""


class CapacityError(StegoError):
    """The secret does not fit in the cover image."""

    def __init__(self, needed: int, available: int) -> None:
        super().__init__(
            f"The secret needs {needed:,} bytes but the image can only hold {available:,} bytes."
        )
        self.needed = needed
        self.available = available


class NoHiddenDataError(StegoError):
    """The image does not contain anything this tool hid.

    ``candidate`` is set when the image *might* hold data written by the
    original version of this tool (which had no header to confirm it).
    """

    def __init__(self, message: str = "No hidden data was found in this image.",
                 candidate: Any = None) -> None:
        super().__init__(message)
        self.candidate = candidate


class PasswordRequiredError(StegoError):
    """The hidden content is encrypted and no password was given."""


class WrongPasswordError(StegoError):
    """The password does not unlock the hidden content."""


class CorruptDataError(StegoError):
    """The hidden content failed its integrity check."""
