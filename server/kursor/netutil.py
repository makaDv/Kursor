"""Network helpers: LAN address discovery and client IP resolution."""

from __future__ import annotations

import ipaddress
import socket

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT range, used by Tailscale
    ipaddress.ip_network("127.0.0.0/8"),
]


def is_private_ipv4(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.version == 4 and any(addr in net for net in PRIVATE_NETWORKS)


def primary_lan_ip() -> str | None:
    """IP of the interface holding the default route. No packet is sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))  # TEST-NET-1, never routed
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def lan_ipv4_addresses() -> list[str]:
    ips: list[str] = []
    primary = primary_lan_ip()
    if primary:
        ips.append(primary)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
    except socket.gaierror:
        pass
    return [ip for ip in ips if not ip.startswith(("127.", "169.254."))]


def hostname() -> str:
    return socket.gethostname().lower()


def is_lan_peer(ip: str | None) -> bool:
    """TCP peer on the local network, a VPN (Tailscale/WireGuard) or a local tunnel process.

    Anything else means the PC was exposed to the Internet (port forwarding, UPnP,
    DMZ): PadLink refuses it, tunnels connect from 127.0.0.1 anyway.
    """
    return bool(ip) and (is_private_ipv4(ip) or is_loopback(ip))


def is_loopback(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def resolve_client_ip(peer: str | None, headers: dict[str, str] | object, trust_proxy: bool) -> str:
    """Real client IP. Proxy headers are honoured only from a loopback peer (local tunnel)."""
    peer = peer or "unknown"
    if trust_proxy and is_loopback(peer):
        get = getattr(headers, "get")
        forwarded = get("cf-connecting-ip") or (get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            try:
                return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
    return peer


def primary_mac(ip: str | None = None) -> str | None:
    """MAC address of the LAN interface holding ``ip`` (for Wake-on-LAN), "AA:BB:CC:DD:EE:FF"."""
    import re
    import subprocess
    import sys
    import uuid

    ip = ip or primary_lan_ip()
    if sys.platform == "win32" and ip:
        try:
            out = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=5,
                                 encoding="oem", errors="replace",
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        # Adapter sections start at column 0; the MAC and the IPv4 are indented lines inside.
        for section in re.split(r"\n(?=\S)", out):
            if re.search(rf"\b{re.escape(ip)}\b", section):
                m = re.search(r"\b((?:[0-9A-F]{2}-){5}[0-9A-F]{2})\b", section, re.I)
                if m:
                    return m.group(1).replace("-", ":").upper()
    node = uuid.getnode()
    if (node >> 40) & 1:  # random (not a real NIC) address
        return None
    return ":".join(f"{(node >> s) & 0xFF:02X}" for s in range(40, -1, -8))


def public_network_profile() -> bool:
    """True if Windows classifies an active connection as a *Public* network."""
    import subprocess
    import sys

    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-NetConnectionProfile).NetworkCategory -join ','"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "Public" in out
