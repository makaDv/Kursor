"""Paired-device registry with rotating, hashed refresh tokens.

The file is shared with the CLI (``python -m kursor devices revoke ...``), so
every read checks the file mtime and reloads when another process changed it.

Refresh tokens are ``<device_id>.<256-bit random>``; only their SHA-256 is
stored. Each refresh rotates the token. Presenting an already-rotated token
(outside a short grace window for concurrent tabs) is treated as theft and
revokes the device.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..fsutil import atomic_write_json, mtime_ns, read_json

REUSE_GRACE_SECONDS = 15


class RefreshError(Exception):
    def __init__(self, reason: str, device_id: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.device_id = device_id


@dataclass
class DeviceInfo:
    id: str
    name: str
    created_at: float
    last_seen: float
    last_ip: str
    user_agent: str

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "last_ip": self.last_ip,
            "user_agent": self.user_agent,
        }


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DeviceStore:
    def __init__(self, path: Path, refresh_ttl: int):
        self.path = path
        self.refresh_ttl = refresh_ttl
        self._lock = threading.RLock()
        self._mtime: int | None = None
        self._devices: dict[str, dict[str, Any]] = {}
        with self._lock:
            self._reload(force=True)

    # ---- persistence ---------------------------------------------------------
    def _reload(self, force: bool = False) -> None:
        current = mtime_ns(self.path)
        if force or current != self._mtime:
            data = read_json(self.path, {"devices": {}})
            self._devices = dict(data.get("devices", {}))
            self._mtime = current

    def _save(self) -> None:
        atomic_write_json(self.path, {"version": 1, "devices": self._devices})
        self._mtime = mtime_ns(self.path)

    def sync(self) -> None:
        with self._lock:
            self._reload()

    # ---- queries -------------------------------------------------------------
    @staticmethod
    def _info(device_id: str, d: dict[str, Any]) -> DeviceInfo:
        return DeviceInfo(
            id=device_id,
            name=d.get("name", "?"),
            created_at=d.get("created_at", 0),
            last_seen=d.get("last_seen", 0),
            last_ip=d.get("last_ip", ""),
            user_agent=d.get("user_agent", ""),
        )

    def list(self) -> list[DeviceInfo]:
        with self._lock:
            self._reload()
            items = [self._info(k, v) for k, v in self._devices.items()]
        return sorted(items, key=lambda d: d.created_at)

    def exists(self, device_id: str) -> bool:
        with self._lock:
            self._reload()
            return device_id in self._devices

    def ids(self) -> set[str]:
        with self._lock:
            self._reload()
            return set(self._devices)

    def resolve(self, id_or_prefix: str) -> str | None:
        matches = [d for d in self.ids() if d.startswith(id_or_prefix)]
        return matches[0] if len(matches) == 1 else None

    # ---- mutations -----------------------------------------------------------
    def create(self, name: str, ip: str, user_agent: str) -> tuple[str, str]:
        device_id = secrets.token_hex(8)
        token = f"{device_id}.{secrets.token_urlsafe(32)}"
        now = time.time()
        with self._lock:
            self._reload()
            self._devices[device_id] = {
                "name": name,
                "created_at": now,
                "last_seen": now,
                "last_ip": ip,
                "user_agent": user_agent[:200],
                "refresh_hash": _hash(token),
                "prev_refresh_hash": None,
                "rotated_at": now,
                "refresh_expires": now + self.refresh_ttl,
            }
            self._save()
        return device_id, token

    def rotate_refresh(self, token: str, ip: str) -> tuple[str, str]:
        device_id, sep, _ = token.partition(".")
        if not sep or not device_id:
            raise RefreshError("malformed")
        presented = _hash(token)
        now = time.time()
        with self._lock:
            self._reload()
            dev = self._devices.get(device_id)
            if dev is None:
                raise RefreshError("unknown_device", device_id)

            matches_current = hmac.compare_digest(presented, dev["refresh_hash"])
            prev = dev.get("prev_refresh_hash") or ""
            matches_prev = bool(prev) and hmac.compare_digest(presented, prev)

            if matches_current:
                if now > dev.get("refresh_expires", 0):
                    raise RefreshError("expired", device_id)
                dev["prev_refresh_hash"] = dev["refresh_hash"]
                dev["rotated_at"] = now
            elif matches_prev:
                if now - dev.get("rotated_at", 0) > REUSE_GRACE_SECONDS:
                    # A rotated token came back: someone else holds a copy.
                    del self._devices[device_id]
                    self._save()
                    raise RefreshError("reuse_detected", device_id)
                # Concurrent refresh from a second tab: allow inside grace window.
            else:
                raise RefreshError("invalid", device_id)

            new_token = f"{device_id}.{secrets.token_urlsafe(32)}"
            dev["refresh_hash"] = _hash(new_token)
            dev["refresh_expires"] = now + self.refresh_ttl
            dev["last_seen"] = now
            dev["last_ip"] = ip
            self._save()
        return device_id, new_token

    def touch(self, device_id: str, ip: str) -> None:
        with self._lock:
            self._reload()
            dev = self._devices.get(device_id)
            if dev is None:
                return
            dev["last_seen"] = time.time()
            dev["last_ip"] = ip
            self._save()

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            self._reload()
            if self._devices.pop(device_id, None) is None:
                return False
            self._save()
            return True

    def revoke_all(self) -> int:
        with self._lock:
            self._reload()
            count = len(self._devices)
            self._devices = {}
            self._save()
            return count
