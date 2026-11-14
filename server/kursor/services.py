"""Container wiring all long-lived components together."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .config import Settings
from .control import screen
from .control.input import InputController
from .fsutil import ensure_private_dir
from .netutil import hostname, lan_ipv4_addresses
from .security.origin import OriginPolicy
from .security.pairing import PairingManager
from .security.ratelimit import LoginGuard, RateLimiter
from .security.store import DeviceStore
from .security.tokens import TokenService

log = logging.getLogger(__name__)


class ConnectionRegistry:
    """Tracks live WebSockets per device so revocation can terminate them instantly."""

    def __init__(self) -> None:
        self._conns: dict[str, set[WebSocket]] = defaultdict(set)

    def add(self, device_id: str, ws: WebSocket) -> None:
        self._conns[device_id].add(ws)

    def remove(self, device_id: str, ws: WebSocket) -> None:
        conns = self._conns.get(device_id)
        if conns is not None:
            conns.discard(ws)
            if not conns:
                del self._conns[device_id]

    def device_ids(self) -> list[str]:
        return list(self._conns)

    def count(self) -> int:
        return sum(len(v) for v in self._conns.values())

    async def close_device(self, device_id: str, code: int = 4409, reason: str = "revoked") -> None:
        for ws in list(self._conns.get(device_id, ())):
            try:
                await ws.close(code=code, reason=reason)
            except Exception:  # noqa: BLE001 - socket may already be gone
                pass
        self._conns.pop(device_id, None)


@dataclass
class Services:
    settings: Settings
    store: DeviceStore
    pairing: PairingManager
    tokens: TokenService
    guard: LoginGuard
    refresh_limiter: RateLimiter
    api_limiter: RateLimiter
    system_limiter: RateLimiter
    origin: OriginPolicy
    input: InputController
    registry: ConnectionRegistry = field(default_factory=ConnectionRegistry)
    lan_ips: list[str] = field(default_factory=list)
    # Set from the desktop app: refuse remote control without unpairing anyone.
    paused: bool = False
    # Event loop running the app (lets the desktop UI thread close sockets).
    loop: Any = None
    _monitors: list[dict[str, int]] = field(default_factory=list)
    _monitors_at: float = 0.0

    @classmethod
    def build(cls, settings: Settings) -> "Services":
        ensure_private_dir(settings.data_dir)
        ips = lan_ipv4_addresses()
        tokens = TokenService(settings.secret_file, settings.access_ttl)
        return cls(
            settings=settings,
            store=DeviceStore(settings.devices_file, settings.refresh_ttl),
            pairing=PairingManager(
                settings.pairing_file, tokens.secret, settings.pairing_ttl, settings.max_failed_attempts
            ),
            tokens=tokens,
            guard=LoginGuard(
                max_failed=settings.max_failed_attempts,
                window=settings.lockout_seconds,
                base_lockout=settings.lockout_seconds,
            ),
            refresh_limiter=RateLimiter(rate=0.5, capacity=10),
            api_limiter=RateLimiter(rate=20, capacity=60),
            system_limiter=RateLimiter(rate=0.2, capacity=1),
            origin=OriginPolicy(settings, ips, hostname()),
            input=InputController(),
            lan_ips=ips,
        )

    def monitors(self) -> list[dict[str, int]]:
        """Cached monitor geometry (refreshed every 10 s, cheap enough to call per event)."""
        now = time.monotonic()
        if not self._monitors or now - self._monitors_at > 10:
            try:
                self._monitors = screen.list_monitors()
                self._monitors_at = now
            except Exception:  # noqa: BLE001
                log.exception("Unable to enumerate monitors")
                if not self._monitors:
                    self._monitors = [{"index": 0, "left": 0, "top": 0, "width": 1920, "height": 1080}]
        return self._monitors

    def monitor_rect(self, index: int) -> dict[str, int]:
        mons = self.monitors()
        if 0 <= index < len(mons):
            return mons[index]
        return mons[1] if len(mons) > 1 else mons[0]
