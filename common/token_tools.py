"""Token helpers used by negative authentication tests.

The production service signs ``v1.<base64url-payload>.<hmac-sha256>``.  Tests
need expired/forged tokens without sleeping, so this module implements the
same format from the documented contract.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def make_token(
    *,
    user_id: int,
    username: str,
    role: str,
    secret: str,
    expires_in: int = 3600,
    issued_at: int | None = None,
    jti: str = "test-token",
) -> str:
    now = int(time.time()) if issued_at is None else int(issued_at)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
        "jti": jti,
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"v1.{body}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()
    return f"v1.{body}.{signature}"


def expired_token(secret: str) -> str:
    return make_token(
        user_id=2,
        username="reader",
        role="reader",
        secret=secret,
        expires_in=-60,
        issued_at=int(time.time()) - 7200,
        jti="expired",
    )


def forged_token(secret: str) -> str:
    token = make_token(
        user_id=1, username="admin", role="admin", secret=secret, jti="forged"
    )
    prefix, body, signature = token.split(".")
    flipped = ("0" if signature[0] != "0" else "1") + signature[1:]
    return f"{prefix}.{body}.{flipped}"


def token_for_admin(secret: str) -> str:
    return make_token(user_id=1, username="admin", role="admin", secret=secret, jti="custom")


def token_claims(token: str) -> dict[str, Any]:
    _, body, _ = token.split(".")
    padding = "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body + padding))
