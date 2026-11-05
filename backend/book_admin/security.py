"""Password hashing, signed access tokens and API exceptions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

TOKEN_PREFIX = "v1"


class TokenError(ValueError):
    """Raised when an access token is missing, malformed, expired or forged."""


class ApiError(Exception):
    def __init__(self, status: int, code: int, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash, password)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def make_token(user: dict[str, Any], secret: str, ttl_seconds: int = 3600,
               now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else int(now)
    payload = {
        "sub": int(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "iat": issued_at,
        "exp": issued_at + int(ttl_seconds),
        "jti": secrets.token_hex(8),
    }
    body = _b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    signing_input = f"{TOKEN_PREFIX}.{body}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()
    return f"{TOKEN_PREFIX}.{body}.{signature}"


def decode_token(token: str, secret: str, now: int | None = None) -> dict[str, Any]:
    if not token or token.count(".") != 2:
        raise TokenError("Malformed token")
    prefix, body, signature = token.split(".")
    if prefix != TOKEN_PREFIX:
        raise TokenError("Unsupported token version")
    expected = hmac.new(
        secret.encode("utf-8"), f"{prefix}.{body}".encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise TokenError("Invalid token signature")
    try:
        payload = json.loads(_b64decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenError("Invalid token payload") from exc
    if not isinstance(payload, dict) or "sub" not in payload or "exp" not in payload:
        raise TokenError("Invalid token claims")
    current = int(time.time()) if now is None else int(now)
    if int(payload["exp"]) <= current:
        raise TokenError("Token expired")
    return payload


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiry_datetime(payload: dict[str, Any]) -> datetime:
    return datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
