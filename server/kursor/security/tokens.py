"""Short-lived JWT access tokens (HS256, random 512-bit server secret)."""

from __future__ import annotations

import secrets
import threading
import time
from pathlib import Path
from typing import Any

import jwt

from ..fsutil import atomic_write_bytes, mtime_ns

ISSUER = "kursor"
AUDIENCE = "kursor-client"
ALGORITHM = "HS256"


def load_or_create_secret(path: Path) -> bytes:
    if path.exists():
        data = path.read_bytes()
        if len(data) >= 32:
            return data
    data = secrets.token_bytes(64)
    atomic_write_bytes(path, data)
    return data


def rotate_secret(path: Path) -> None:
    atomic_write_bytes(path, secrets.token_bytes(64))


class TokenService:
    def __init__(self, secret_path: Path, access_ttl: int):
        self.secret_path = secret_path
        self.access_ttl = access_ttl
        self._lock = threading.Lock()
        self._secret = load_or_create_secret(secret_path)
        self._mtime = mtime_ns(secret_path)

    @property
    def secret(self) -> bytes:
        return self._secret

    def maybe_reload(self) -> bool:
        """Pick up a secret rotated by the CLI (revoke-all)."""
        current = mtime_ns(self.secret_path)
        if current == self._mtime:
            return False
        with self._lock:
            self._secret = load_or_create_secret(self.secret_path)
            self._mtime = mtime_ns(self.secret_path)
        return True

    def issue_access(self, device_id: str, pwv: str = "") -> tuple[str, int]:
        """``pwv``: version of the PC password the device proved; a password change invalidates the token."""
        now = int(time.time())
        exp = now + self.access_ttl
        payload = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": device_id,
            "iat": now,
            "nbf": now,
            "exp": exp,
            "jti": secrets.token_hex(8),
            "typ": "access",
            "pwv": pwv,
        }
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM), exp

    def verify_access(self, token: str, pwv: str | None = None) -> dict[str, Any]:
        claims = jwt.decode(
            token,
            self._secret,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=5,
            options={"require": ["exp", "iat", "nbf", "sub", "aud", "iss"]},
        )
        if claims.get("typ") != "access":
            raise jwt.InvalidTokenError("wrong token type")
        if pwv is not None and claims.get("pwv") != pwv:
            # Reported as expired: the client refreshes, and the refresh asks for the new password.
            raise jwt.ExpiredSignatureError("password changed")
        return claims
