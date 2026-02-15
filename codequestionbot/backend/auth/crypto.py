from __future__ import annotations

import os

import logging

from cryptography.fernet import Fernet

_LOGGER = logging.getLogger(__name__)


def encrypt_token(token: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        return token
    return fernet.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(token: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        return token
    return fernet.decrypt(token.encode("utf-8")).decode("utf-8")


def _get_fernet() -> Fernet | None:
    key = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
    if not key:
        _LOGGER.warning("TOKEN_ENCRYPTION_KEY not set; tokens stored unencrypted.")
        return None
    return Fernet(key)
