"""Runtime configuration for the Kursor daemon."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    env = os.environ.get("KURSOR_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".kursor"


def default_static_dir() -> Path:
    env = os.environ.get("KURSOR_STATIC_DIR")
    if env:
        return Path(env).expanduser()
    return REPO_ROOT / "client" / "dist"


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8443
    tls: bool = True
    data_dir: Path = field(default_factory=default_data_dir)
    static_dir: Path = field(default_factory=default_static_dir)

    # Public origin when exposed through a tunnel, e.g. "https://kursor.example.com".
    public_origin: str | None = None
    # Additional explicitly allowed origins (scheme://host[:port]).
    extra_origins: list[str] = field(default_factory=list)
    # Trust CF-Connecting-IP / X-Forwarded-For, only from loopback peers (tunnel mode).
    trust_proxy: bool = False
    # Allow the Vite dev server origins (http://localhost:5173).
    dev: bool = False

    access_ttl: int = 10 * 60  # seconds
    refresh_ttl: int = 30 * 24 * 3600  # seconds, sliding
    pairing_ttl: int = 5 * 60  # seconds
    max_failed_attempts: int = 5
    lockout_seconds: int = 15 * 60  # first lockout, doubles each time
    log_level: str = "INFO"

    @property
    def scheme(self) -> str:
        return "https" if self.tls else "http"

    @property
    def secure_cookies(self) -> bool:
        if self.tls:
            return True
        return bool(self.public_origin and self.public_origin.startswith("https://"))

    # ---- data file locations -------------------------------------------------
    @property
    def devices_file(self) -> Path:
        return self.data_dir / "devices.json"

    @property
    def pairing_file(self) -> Path:
        return self.data_dir / "pairing.json"

    @property
    def secret_file(self) -> Path:
        return self.data_dir / "secret.key"

    @property
    def cert_dir(self) -> Path:
        return self.data_dir / "certs"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"
