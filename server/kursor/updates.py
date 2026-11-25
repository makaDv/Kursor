"""Update check for the Windows program, with a signed manifest.

Disabled until you publish releases: set UPDATE_URL and UPDATE_PUBLIC_KEY below
(generate the key pair with ``scripts/release_keys.py``). The manifest is a small
JSON file signed with Ed25519; an attacker who controls the network or the web
host cannot fake an update notice without the private key, which never leaves
your release machine.

Only a plain GET of the manifest is made, once a day, with no identifiers. It is
declared in the privacy policy and can be turned off in the PC window.

Manifest (``latest.json``)::

    {"version": "1.2.0", "url": "https://.../PadLink-Setup-1.2.0.exe",
     "notes": "...", "sha256": "<hex of the installer>"}

Signature (``latest.json.sig``): base64 Ed25519 signature of the exact manifest bytes.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.request
from dataclasses import dataclass

from . import __version__

log = logging.getLogger(__name__)

# ---- release configuration (fill in when you publish) -------------------------------
UPDATE_URL: str | None = None          # e.g. "https://padlink.example.com/releases/latest.json"
UPDATE_PUBLIC_KEY: str | None = None   # base64 raw Ed25519 public key (32 bytes)
CHECK_INTERVAL_S = 24 * 3600


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str


def _parse_version(v: str) -> tuple[int, ...]:
    out = []
    for part in v.split(".")[:4]:
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


def enabled() -> bool:
    from .winpkg import is_packaged

    # Microsoft Store builds are updated by the Store only (its policy forbids self-updaters).
    if is_packaged():
        return False
    return bool(UPDATE_URL and UPDATE_PUBLIC_KEY and UPDATE_URL.startswith("https://"))


def verify(manifest: bytes, signature_b64: str, public_key_b64: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        key.verify(base64.b64decode(signature_b64.strip()), manifest)
        return True
    except (InvalidSignature, ValueError):
        return False


def _get(url: str, limit: int = 64 * 1024) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "PadLink-updater"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - https enforced in enabled()
        return resp.read(limit)


def check() -> UpdateInfo | None:
    """Newer signed release, or None (also on any error or when disabled)."""
    if not enabled():
        return None
    try:
        manifest = _get(UPDATE_URL)  # type: ignore[arg-type]
        signature = _get(UPDATE_URL + ".sig").decode("ascii")  # type: ignore[operator]
        if not verify(manifest, signature, UPDATE_PUBLIC_KEY):  # type: ignore[arg-type]
            log.warning("Update manifest signature INVALID: ignored")
            return None
        data = json.loads(manifest)
        version, url = str(data["version"]), str(data["url"])
        if not url.startswith("https://"):
            return None
        if _parse_version(version) > _parse_version(__version__):
            return UpdateInfo(version, url, str(data.get("notes", ""))[:500])
    except Exception:  # noqa: BLE001 - offline, server down...: try again tomorrow
        log.info("Update check failed", exc_info=True)
    return None
