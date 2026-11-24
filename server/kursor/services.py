"""Container wiring all long-lived components together."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
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
from .security.password import PasswordStore
from .security.ratelimit import LoginGuard, RateLimiter
from .prefs import PrefsStore
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
    password: PasswordStore
    registry: ConnectionRegistry = field(default_factory=ConnectionRegistry)
    lan_ips: list[str] = field(default_factory=list)
    # device_id -> number of live screen streams (drives the "watching your screen" indicator).
    screen_viewers: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    # Set from the desktop app: refuse remote control without unpairing anyone.
    paused: bool = False
    # Event loop running the app (lets the desktop UI thread close sockets).
    loop: Any = None
    prefs: PrefsStore | None = None
    # Human-readable events for the PC window ("Pixel ha spento il PC"), drained by the desktop UI.
    events: deque = field(default_factory=lambda: deque(maxlen=50))
    # Devices allowed for this run when "ask on the PC" is on, and pending approval futures.
    approved: set = field(default_factory=set)
    approvals: dict = field(default_factory=dict)
    # True while a UI able to answer approval requests is running (desktop app).
    approver_available: bool = False
    # Shown to the app (header, Wake-on-LAN). MAC is looked up once at startup.
    pc_name: str = ""
    pc_mac: str | None = None
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
                path=settings.lockout_file,
            ),
            prefs=PrefsStore(settings.prefs_file),
            refresh_limiter=RateLimiter(rate=0.5, capacity=10),
            api_limiter=RateLimiter(rate=20, capacity=60),
            system_limiter=RateLimiter(rate=0.2, capacity=1),
            origin=OriginPolicy(settings, ips, hostname()),
            input=InputController(),
            password=PasswordStore(settings.password_file),
            lan_ips=ips,
            pc_name=hostname(),
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


    # ---- helpers used by the API and the desktop window ------------------------
    def device_name(self, device_id: str) -> str:
        d = self.store.get(device_id)
        return d.name if d else "Un dispositivo"

    def notify(self, text: str) -> None:
        """Queue a notification for the PC user (shown by the desktop app, if running)."""
        self.events.append((time.time(), text))

    async def request_approval(self, device_id: str, timeout: float = 30.0) -> bool:
        """Ask the PC user to allow this device for the current session (desktop app only)."""
        prefs = self.prefs.value if self.prefs else None
        if not prefs or not prefs.require_approval or not self.approver_available:
            return True
        if device_id in self.approved:
            return True
        import asyncio

        fut = self.approvals.get(device_id)
        if fut is None or fut.done():
            fut = asyncio.get_running_loop().create_future()
            self.approvals[device_id] = fut
        try:
            ok = await asyncio.wait_for(asyncio.shield(fut), timeout)
        except asyncio.TimeoutError:
            ok = False
        finally:
            if fut.done():
                self.approvals.pop(device_id, None)
        if ok:
            self.approved.add(device_id)
        return ok

    def answer_approval(self, device_id: str, allow: bool) -> None:
        """Called from the desktop UI thread."""
        fut = self.approvals.get(device_id)
        if fut is not None and self.loop is not None:
            self.loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(allow))
