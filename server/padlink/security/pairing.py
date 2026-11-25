"""Time-limited, single-use pairing secrets (6-digit PIN + high-entropy QR code).

State lives in ``pairing.json`` so ``python -m padlink pair`` can open a new
pairing window while the server is running. Only HMACs of the secrets are
written to disk.

Brute-force protection: besides the per-IP lockout, the pairing window is
destroyed after ``max_failed`` wrong attempts *from any source*. An attacker
therefore gets at most 5 guesses on a 1,000,000 PIN space per window.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..fsutil import atomic_write_json, read_json


class PairResult(enum.Enum):
    OK = "ok"
    INVALID = "invalid"
    NO_SESSION = "no_session"
    EXHAUSTED = "exhausted"


@dataclass
class PairingSession:
    pin: str
    code: str
    expires_at: float


class PairingManager:
    def __init__(self, path: Path, key: bytes, ttl: int, max_failed: int):
        self.path = path
        self._key = hmac.new(key, b"padlink-pairing-v1", hashlib.sha256).digest()
        self.ttl = ttl
        self.max_failed = max_failed
        self._lock = threading.Lock()

    def _mac(self, value: str) -> str:
        return hmac.new(self._key, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def new_session(self) -> PairingSession:
        pin = f"{secrets.randbelow(1_000_000):06d}"
        code = secrets.token_urlsafe(18)
        expires = time.time() + self.ttl
        with self._lock:
            atomic_write_json(
                self.path,
                {
                    "pin_mac": self._mac(pin),
                    "code_mac": self._mac(code),
                    "expires_at": expires,
                    "failed": 0,
                },
            )
        return PairingSession(pin=pin, code=code, expires_at=expires)

    def _end(self) -> None:
        """Pairing window over (used, exhausted, closed, expired): remove every trace."""
        self.path.unlink(missing_ok=True)
        # QR image written by `python -m padlink pair`: it contains a live secret.
        (self.path.parent / "pairing-qr.png").unlink(missing_ok=True)

    def close(self) -> None:
        with self._lock:
            self._end()

    def active_until(self) -> float | None:
        data = read_json(self.path, None)
        if not data or time.time() > data.get("expires_at", 0):
            return None
        return float(data["expires_at"])

    def verify(self, secret: str) -> PairResult:
        candidate = secret.strip()
        if re.fullmatch(r"[\d\s-]{6,9}", candidate):
            candidate = re.sub(r"[\s-]", "", candidate)
        mac = self._mac(candidate)
        with self._lock:
            data = read_json(self.path, None)
            if not data or time.time() > data.get("expires_at", 0):
                if data:
                    self._end()
                return PairResult.NO_SESSION
            pin_ok = hmac.compare_digest(mac, data.get("pin_mac", ""))
            code_ok = hmac.compare_digest(mac, data.get("code_mac", ""))
            if pin_ok or code_ok:
                self._end()  # single use
                return PairResult.OK
            data["failed"] = int(data.get("failed", 0)) + 1
            if data["failed"] >= self.max_failed:
                self._end()
                return PairResult.EXHAUSTED
            atomic_write_json(self.path, data)
            return PairResult.INVALID
