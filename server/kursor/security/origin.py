"""Host and Origin allow-listing (CSRF, cross-site WebSocket hijacking, DNS rebinding)."""

from __future__ import annotations

from urllib.parse import urlsplit

from ..config import Settings


def _normalize_origin(origin: str) -> str | None:
    try:
        parts = urlsplit(origin.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower()
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    default_port = 443 if parts.scheme == "https" else 80
    try:
        port = parts.port
    except ValueError:
        return None
    if port and port != default_port:
        return f"{parts.scheme}://{host}:{port}"
    return f"{parts.scheme}://{host}"


def _split_host(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if ":" in host else host


class OriginPolicy:
    def __init__(self, settings: Settings, lan_ips: list[str], hostname: str):
        hosts = {"localhost", "127.0.0.1", "[::1]", *lan_ips}
        if hostname:
            hosts.update({hostname, f"{hostname}.local"})

        origins: set[str] = set()
        for h in hosts:
            o = _normalize_origin(f"{settings.scheme}://{h}:{settings.port}")
            if o:
                origins.add(o)

        if settings.public_origin:
            o = _normalize_origin(settings.public_origin)
            if o:
                origins.add(o)
                hosts.add(_split_host(urlsplit(o).netloc))

        for extra in settings.extra_origins:
            o = _normalize_origin(extra)
            if o:
                origins.add(o)
                hosts.add(_split_host(urlsplit(o).netloc))

        if settings.dev:
            for h in ("localhost", "127.0.0.1", *lan_ips):
                for scheme in ("http", "https"):
                    origins.add(f"{scheme}://{h}:5173")

        self.allowed_hosts = frozenset(hosts)
        self.allowed_origins = frozenset(origins)

    def host_ok(self, host_header: str | None) -> bool:
        if not host_header:
            return False
        return _split_host(host_header) in self.allowed_hosts

    def origin_ok(self, origin: str | None) -> bool:
        if not origin:
            return False
        normalized = _normalize_origin(origin)
        return normalized is not None and normalized in self.allowed_origins
