"""Small helpers for safe file persistence."""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path, 0o700)


def restrict_permissions(path: Path) -> None:
    """Owner-only access on POSIX. On Windows the user profile ACL already applies."""
    if os.name != "nt":
        os.chmod(path, 0o600)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    restrict_permissions(tmp)
    # On Windows os.replace can fail briefly if another process has the file open.
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_bytes(path, json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))


def read_json(path: Path, default: Any) -> Any:
    for attempt in range(5):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (PermissionError, json.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(0.05)
    return default


def mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None
