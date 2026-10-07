"""Password protection: scrypt key derivation + AES-256-GCM."""

from __future__ import annotations

import hashlib
import os
import unicodedata

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import CorruptDataError, WrongPasswordError

SALT_LEN = 16
NONCE_LEN = 12
TAG_LEN = 16
OVERHEAD = SALT_LEN + NONCE_LEN + TAG_LEN

_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1


def derive_key(password: str, salt: bytes) -> bytes:
    normalised = unicodedata.normalize("NFC", password).encode("utf-8")
    return hashlib.scrypt(
        normalised, salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        maxmem=64 * 1024 * 1024, dklen=32,
    )


def encrypt(plaintext: bytes, password: str, aad: bytes = b"") -> bytes:
    """Return ``salt | nonce | ciphertext+tag``."""
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    ciphertext = AESGCM(derive_key(password, salt)).encrypt(nonce, plaintext, aad)
    return salt + nonce + ciphertext


def decrypt(blob: bytes, password: str, aad: bytes = b"") -> bytes:
    if len(blob) < OVERHEAD:
        raise CorruptDataError("The encrypted content is truncated.")
    salt, nonce, ciphertext = blob[:SALT_LEN], blob[SALT_LEN:SALT_LEN + NONCE_LEN], blob[SALT_LEN + NONCE_LEN:]
    try:
        return AESGCM(derive_key(password, salt)).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise WrongPasswordError("The password is incorrect.") from None
