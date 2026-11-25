"""Brute-force guard (lockouts persisted to disk) and token-bucket rate limiter."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field

MAX_TRACKED_KEYS = 10_000


@dataclass
class _Entry:
    failures: deque[float] = field(default_factory=deque)
    locked_until: float = 0.0
    lockouts: int = 0
    touched: float = 0.0


class LoginGuard:
    """Locks a client out after ``max_failed`` failures within ``window`` seconds.

    Each further lockout doubles the duration (capped at ``max_lockout``).
    """

    def __init__(self, max_failed: int = 5, window: int = 900, base_lockout: int = 900, max_lockout: int = 86_400,
                 path: Path | None = None):
        self.max_failed = max_failed
        self.window = window
        self.base_lockout = base_lockout
        self.max_lockout = max_lockout
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        # Active lockouts survive a restart of PadLink (otherwise restarting would reset them).
        self.path = path
        self._load()

    def _load(self) -> None:
        if not self.path:
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        now = time.time()
        for key, (locked_until, lockouts) in (data.get("locked") or {}).items():
            if isinstance(key, str) and float(locked_until) > now:
                self._entries[key] = _Entry(locked_until=float(locked_until), lockouts=int(lockouts), touched=now)

    def _persist(self) -> None:
        """Write active lockouts (caller holds the lock)."""
        if not self.path:
            return
        now = time.time()
        locked = {k: [e.locked_until, e.lockouts] for k, e in self._entries.items() if e.locked_until > now}
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps({"locked": locked}), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _prune(self, now: float) -> None:
        if len(self._entries) < MAX_TRACKED_KEYS:
            return
        stale = [k for k, e in self._entries.items() if e.locked_until < now and now - e.touched > self.window]
        for k in stale:
            del self._entries[k]

    def retry_after(self, key: str) -> int:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return 0
            remaining = entry.locked_until - time.time()
            return max(0, int(remaining + 0.999))

    def fail(self, key: str) -> int:
        """Record a failure. Returns lockout seconds if the client is now locked."""
        now = time.time()
        with self._lock:
            self._prune(now)
            entry = self._entries.setdefault(key, _Entry())
            entry.touched = now
            while entry.failures and now - entry.failures[0] > self.window:
                entry.failures.popleft()
            entry.failures.append(now)
            if len(entry.failures) >= self.max_failed:
                duration = min(self.max_lockout, self.base_lockout * (2**entry.lockouts))
                entry.lockouts += 1
                entry.locked_until = now + duration
                entry.failures.clear()
                self._persist()
                return int(duration)
            return 0

    def remaining_attempts(self, key: str) -> int:
        with self._lock:
            entry = self._entries.get(key)
            return self.max_failed - (len(entry.failures) if entry else 0)

    def success(self, key: str) -> None:
        with self._lock:
            if self._entries.pop(key, None) is not None:
                self._persist()


class RateLimiter:
    """Token bucket per key: ``rate`` tokens/second, burst ``capacity``."""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) > MAX_TRACKED_KEYS:
                self._buckets.clear()
            tokens, last = self._buckets.get(key, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < cost:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - cost, now)
            return True


class LocalBucket:
    """Single-owner token bucket (one per WebSocket connection, no locking)."""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True
