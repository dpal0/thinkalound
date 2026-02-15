from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any

import jwt

_LOGGER = logging.getLogger(__name__)


def issue_jwt(
    user_id: str,
    github_login: str,
    is_instructor: bool,
    exp_minutes: int,
) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "login": github_login,
        "is_instructor": is_instructor,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_minutes)).timestamp()),
    }
    secret = _get_jwt_secret()
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str) -> dict[str, Any]:
    secret = _get_jwt_secret()
    return jwt.decode(token, secret, algorithms=["HS256"])


def _get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        _LOGGER.warning("JWT_SECRET not set; using empty secret (dev-only).")
    return secret
