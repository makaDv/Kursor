"""PC password: a second factor asked on every app start (pairing and session refresh).

Only a scrypt hash is stored (``password.json`` in the data dir). The file is
re-read when its mtime changes, so a password set from the CLI or the desktop app
applies to a running server at once.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
from pathlib import Path

from ..fsutil import atomic_write_json, mtime_ns, read_json

MIN_LENGTH = 8
MAX_LENGTH = 128
# scrypt cost: ~50 ms and 32 MiB per check on a normal PC, too slow for offline guessing at scale.
_N, _R, _P = 2**15, 8, 1
_MAXMEM = 64 * 1024 * 1024


def _hash(password: str, salt: bytes, n: int = _N, r: int = _R, p: int = _P) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=32)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class PasswordError(ValueError):
    pass


def validate(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise PasswordError(f"La password deve avere almeno {MIN_LENGTH} caratteri")
    if len(password) > MAX_LENGTH:
        raise PasswordError(f"La password può avere al massimo {MAX_LENGTH} caratteri")


class PasswordStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._mtime: int | None = -1
        self._record: dict | None = None

    def _current(self) -> dict | None:
        with self._lock:
            mtime = mtime_ns(self.path)
            if mtime != self._mtime:
                self._mtime = mtime
                data = read_json(self.path, None) if mtime is not None else None
                self._record = data if isinstance(data, dict) and data.get("hash") and data.get("salt") else None
            return self._record

    def is_set(self) -> bool:
        return self._current() is not None

    def version(self) -> str:
        """Changes whenever the password is set or changed ("" when none is set)."""
        record = self._current()
        if record is None:
            return ""
        return hashlib.sha256(str(record["salt"]).encode("ascii")).hexdigest()[:16]

    def set(self, password: str) -> None:
        validate(password)
        salt = secrets.token_bytes(16)
        record = {"v": 1, "kdf": "scrypt", "n": _N, "r": _R, "p": _P,
                  "salt": _b64(salt), "hash": _b64(_hash(password, salt))}
        atomic_write_json(self.path, record)

    def verify(self, password: str | None) -> bool:
        record = self._current()
        if record is None or not isinstance(password, str) or not password or len(password) > MAX_LENGTH:
            return False
        try:
            salt = base64.b64decode(record["salt"])
            expected = base64.b64decode(record["hash"])
            actual = _hash(password, salt, int(record.get("n", _N)), int(record.get("r", _R)), int(record.get("p", _P)))
        except (KeyError, ValueError, TypeError):
            return False
        return hmac.compare_digest(actual, expected)
