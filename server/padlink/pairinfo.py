"""Pairing link shared by the CLI and the desktop app.

The QR code encodes ``https://<LAN IP>:<port>/#pair=<code>&fp=<pin>[&ts=<Tailscale IP>]``:

* ``pair`` is the single-use, 5-minute pairing secret;
* ``fp`` is base64url(SHA-256) of the local CA certificate. The store apps pin it,
  so scanning the QR both authenticates the phone to the PC *and* the PC to the
  phone, with nothing to install. Both live in the URL fragment, which browsers
  never send over the network.
* ``ts`` is the PC's Tailscale address: the app falls back to it (same pinned CA)
  when the LAN address is unreachable, e.g. away from home.

``fp`` is omitted behind a tunnel (``--public-origin``): the tunnel presents a
public certificate, validated with the normal system trust store.
"""

from __future__ import annotations

from cryptography import x509

from .certs import ca_pin, verification_code
from .config import Settings
from .netutil import primary_lan_ip, tailscale_ipv4


def base_url(s: Settings) -> str:
    if s.public_origin:
        return s.public_origin
    ip = primary_lan_ip() or "127.0.0.1"
    return f"{s.scheme}://{ip}:{s.port}"


def current_ca_pin(s: Settings) -> str | None:
    if not s.tls or s.public_origin:
        return None
    path = s.cert_dir / "padlink-ca.crt"
    try:
        return ca_pin(x509.load_pem_x509_certificate(path.read_bytes()))
    except (OSError, ValueError):
        return None


def pairing_url(s: Settings, code: str) -> str:
    url = f"{base_url(s)}/#pair={code}"
    pin = current_ca_pin(s)
    if not pin:
        return url
    url = f"{url}&fp={pin}"
    ts = tailscale_ipv4()
    if ts and ts != primary_lan_ip():
        url = f"{url}&ts={ts}"
    return url


def current_verification_code(s: Settings) -> str | None:
    pin = current_ca_pin(s)
    return verification_code(pin) if pin else None
