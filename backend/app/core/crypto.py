"""Encrypt secrets at rest. Keys never go in logs or API responses."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet(secret: str) -> Fernet:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str, secret: str) -> str:
    return _fernet(secret).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str, secret: str) -> str:
    try:
        return _fernet(secret).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Stored secret could not be decrypted.") from exc
