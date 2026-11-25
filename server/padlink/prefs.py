"""PC-side preferences chosen in the desktop window (data_dir/settings.json)."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .fsutil import atomic_write_json, read_json

INACTIVE_CHOICES = (0, 30, 90, 180)  # days; 0 = never


@dataclass
class PcPrefs:
    # Revoke devices not seen for this many days (0 = never).
    inactive_days: int = 90
    # Ask on the PC "Allow / Deny" the first time each device connects in a session.
    require_approval: bool = False
    # Announce the PC on the local network (mDNS) so the app finds it again after an IP change.
    discoverable: bool = True


class PrefsStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        data = read_json(path, {}) or {}
        known = {f.name for f in fields(PcPrefs)}
        self.value = PcPrefs(**{k: v for k, v in data.items() if k in known})
        if self.value.inactive_days not in INACTIVE_CHOICES:
            self.value.inactive_days = 90

    def update(self, **changes: object) -> PcPrefs:
        with self._lock:
            for k, v in changes.items():
                if hasattr(self.value, k):
                    setattr(self.value, k, v)
            atomic_write_json(self.path, asdict(self.value))
            return self.value
