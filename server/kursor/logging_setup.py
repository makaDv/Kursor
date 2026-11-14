"""Console logging plus a JSON-lines audit log of every security-relevant event."""

from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path
from typing import Any

from .fsutil import ensure_private_dir

AUDIT_LOGGER = "kursor.audit"
_audit = logging.getLogger(AUDIT_LOGGER)


class _JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "audit", None) or {"message": record.getMessage()}
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            **payload,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(log_dir: Path, level: str = "INFO") -> Path:
    ensure_private_dir(log_dir)
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    console.setLevel(level.upper())
    root.addHandler(console)

    audit_path = log_dir / "access.log"
    file_handler = logging.handlers.RotatingFileHandler(
        audit_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(_JsonLineFormatter())
    _audit.setLevel(logging.INFO)
    _audit.addHandler(file_handler)
    _audit.propagate = True  # also show on console

    # Our own audit middleware replaces the uvicorn access log.
    logging.getLogger("uvicorn.access").disabled = True
    return audit_path


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        # Prevent log forging through control characters and cap length.
        return value.replace("\r", "\\r").replace("\n", "\\n")[:300]
    return value


def audit(event: str, level: int = logging.INFO, **fields: Any) -> None:
    data = {"event": event, **{k: _clean(v) for k, v in fields.items() if v is not None}}
    summary = " ".join(f"{k}={v}" for k, v in data.items() if k != "event")
    _audit.log(level, f"{event} {summary}".strip(), extra={"audit": data})
