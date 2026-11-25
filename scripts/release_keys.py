"""Release signing for the PadLink update manifest (see server/padlink/updates.py).

    python scripts/release_keys.py keygen  <dir-outside-the-repo>
    python scripts/release_keys.py sign    <private.key> latest.json   -> writes latest.json.sig

Keep private.key OFFLINE and out of the repository (*.key is git-ignored).
Paste the printed public key into UPDATE_PUBLIC_KEY.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def keygen(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    (out / "padlink-release.key").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print("Private key:", out / "padlink-release.key", "(keep it offline, back it up)")
    print("UPDATE_PUBLIC_KEY =", repr(base64.b64encode(pub).decode()))


def sign(private_key: str, manifest: str) -> None:
    key = serialization.load_pem_private_key(Path(private_key).read_bytes(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    data = Path(manifest).read_bytes()
    sig = base64.b64encode(key.sign(data)).decode()
    Path(manifest + ".sig").write_text(sig, encoding="ascii")
    print("Signed:", manifest + ".sig")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "keygen":
        keygen(sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] == "sign":
        sign(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(2)
