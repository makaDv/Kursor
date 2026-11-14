"""Shared server bootstrap for the CLI (`python -m kursor run`) and the desktop app."""

from __future__ import annotations

import os

# PadLink sends no telemetry. FastAPI pulls in opentelemetry-api (a no-op without
# an SDK); disable any SDK/exporter that might be present so nothing can ever leave the PC.
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OTEL_TRACES_EXPORTER"] = "none"
os.environ["OTEL_METRICS_EXPORTER"] = "none"
os.environ["OTEL_LOGS_EXPORTER"] = "none"

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn

from .app import create_app
from .certs import CertBundle, ensure_certificates
from .config import Settings
from .control import enable_dpi_awareness
from .logging_setup import setup_logging
from .discovery import Announcer
from .netutil import hostname, primary_mac
from .services import Services


@dataclass
class Runtime:
    settings: Settings
    svc: Services
    audit_path: Path
    bundle: CertBundle | None
    ssl_kwargs: dict[str, Any] = field(default_factory=dict)
    announcer: Announcer = field(default_factory=Announcer)

    def start_discovery(self) -> bool:
        """Announce the PC on the LAN (mDNS) if enabled, with the pinned CA fingerprint."""
        s = self.settings
        if s.public_origin or not (self.svc.prefs and self.svc.prefs.value.discoverable):
            return False
        from .netutil import is_private_ipv4

        ips = [ip for ip in self.svc.lan_ips if is_private_ipv4(ip) and not ip.startswith("127.")]
        return self.announcer.start(s.port, ips, self.svc.pc_name, self.bundle.ca_pin if self.bundle else None)

    def stop_discovery(self) -> None:
        self.announcer.stop()

    def uvicorn_config(self) -> uvicorn.Config:
        s = self.settings
        return uvicorn.Config(
            create_app(self.svc),
            host=s.host,
            port=s.port,
            log_level=s.log_level.lower(),
            server_header=False,
            proxy_headers=False,
            access_log=False,
            ws_max_size=1024 * 1024,
            ws_ping_interval=20,
            ws_ping_timeout=20,
            **self.ssl_kwargs,
        )


def prepare(s: Settings) -> Runtime:
    audit_path = setup_logging(s.log_dir, s.log_level)
    enable_dpi_awareness()
    svc = Services.build(s)
    bundle = None
    ssl_kwargs: dict[str, Any] = {}
    if s.tls:
        bundle = ensure_certificates(s.cert_dir, svc.lan_ips, hostname())
        ssl_kwargs = {
            "ssl_certfile": str(bundle.server_fullchain),
            "ssl_keyfile": str(bundle.server_key),
            "ssl_ciphers": "ECDHE+AESGCM:ECDHE+CHACHA20",
        }
    svc.pc_mac = primary_mac()
    return Runtime(s, svc, audit_path, bundle, ssl_kwargs)
