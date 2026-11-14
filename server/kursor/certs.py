"""Local certificate authority + LAN server certificate.

A private CA signs a short-lived server certificate that covers every private
LAN IP of this PC. The store apps *pin* this CA (its SHA-256 travels in the
pairing QR code), so nothing has to be installed on the phone; the PWA instead
needs the CA installed once. The CA carries X.509 *name
constraints*: even if its key leaked, it could only sign certificates for
private IP ranges, ``localhost`` and ``*.local``, never for public websites.
The server certificate is re-issued automatically when the LAN IP changes,
without having to reinstall anything on the phone.
"""

from __future__ import annotations

import base64
import datetime as dt
import ipaddress
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .fsutil import atomic_write_bytes, ensure_private_dir
from .netutil import PRIVATE_NETWORKS, is_private_ipv4

log = logging.getLogger(__name__)

CA_VALIDITY_DAYS = 3650
SERVER_VALIDITY_DAYS = 397  # Apple/Chrome maximum for TLS server certificates
RENEW_BEFORE_DAYS = 30


@dataclass
class CertBundle:
    ca_cert: Path
    server_cert: Path
    server_key: Path
    ca_fingerprint: str
    issued_new_server_cert: bool
    # Leaf + CA, served by uvicorn so clients can find the pinned CA in the chain.
    server_fullchain: Path
    # base64url(SHA-256(CA DER)), no padding: the pin carried by the QR code (fp=).
    ca_pin: str

    @property
    def verification_code(self) -> str:
        return verification_code(self.ca_pin)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _fingerprint(cert: x509.Certificate) -> str:
    raw = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(raw[i : i + 2] for i in range(0, len(raw), 2))


def ca_pin(cert: x509.Certificate) -> str:
    return base64.urlsafe_b64encode(cert.fingerprint(hashes.SHA256())).rstrip(b"=").decode()


def verification_code(pin: str) -> str:
    """First 48 bits of the CA hash, XXXX-XXXX-XXXX (same as client verificationCode())."""
    raw = base64.urlsafe_b64decode(pin + "=" * (-len(pin) % 4))[:6].hex().upper()
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def _write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    atomic_write_bytes(
        path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def _load_key(path: Path) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    return key


def _create_ca(cert_path: Path, key_path: Path) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Kursor"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Kursor Local CA"),
        ]
    )
    permitted: list[x509.GeneralName] = [x509.DNSName("localhost"), x509.DNSName("local")]
    permitted += [x509.IPAddress(net) for net in PRIVATE_NETWORKS]
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - dt.timedelta(minutes=5))
        .not_valid_after(_now() + dt.timedelta(days=CA_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.NameConstraints(permitted_subtrees=permitted, excluded_subtrees=None), critical=True)
        .add_extension(ski, critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_key(key_path, key)
    atomic_write_bytes(cert_path, cert.public_bytes(serialization.Encoding.PEM))
    log.info("Created new local CA at %s", cert_path)
    return cert, key


def _valid_dns_label(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?", name))


def _server_names(ips: list[str], host: str) -> tuple[list[str], list[str]]:
    dns = ["localhost"]
    if _valid_dns_label(host):
        dns.append(f"{host}.local")
    ip_list = ["127.0.0.1"] + [ip for ip in ips if is_private_ipv4(ip) and ip != "127.0.0.1"]
    return dns, ip_list


def _server_cert_needs_renewal(cert_path: Path, key_path: Path, ca: x509.Certificate, ips: list[str]) -> bool:
    if not cert_path.exists() or not key_path.exists():
        return True
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except ValueError:
        return True
    if cert.issuer != ca.subject:
        return True
    if cert.not_valid_after_utc - _now() < dt.timedelta(days=RENEW_BEFORE_DAYS):
        return True
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return True
    present = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    return any(ip not in present for ip in ips)


def _issue_server_cert(
    ca: x509.Certificate, ca_key: ec.EllipticCurvePrivateKey, ips: list[str], host: str, cert_path: Path, key_path: Path
) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    dns, ip_list = _server_names(ips, host)
    alt_names: list[x509.GeneralName] = [x509.DNSName(d) for d in dns]
    alt_names += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ip_list]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip_list[-1])]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() - dt.timedelta(minutes=5))
        .not_valid_after(_now() + dt.timedelta(days=SERVER_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(key_path, key)
    atomic_write_bytes(cert_path, cert.public_bytes(serialization.Encoding.PEM))
    log.info("Issued server certificate for %s", ", ".join(dns + ip_list))


def ensure_certificates(cert_dir: Path, ips: list[str], host: str, force: bool = False) -> CertBundle:
    ensure_private_dir(cert_dir)
    ca_cert_path = cert_dir / "kursor-ca.crt"
    ca_key_path = cert_dir / "kursor-ca.key"
    srv_cert_path = cert_dir / "server.crt"
    srv_key_path = cert_dir / "server.key"

    if force or not ca_cert_path.exists() or not ca_key_path.exists():
        ca, ca_key = _create_ca(ca_cert_path, ca_key_path)
        force = True
    else:
        ca = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
        ca_key = _load_key(ca_key_path)

    wanted_ips = [ip for ip in ips if is_private_ipv4(ip)]
    issued = False
    if force or _server_cert_needs_renewal(srv_cert_path, srv_key_path, ca, wanted_ips):
        _issue_server_cert(ca, ca_key, wanted_ips, host, srv_cert_path, srv_key_path)
        issued = True

    fullchain_path = cert_dir / "server-fullchain.pem"
    fullchain = srv_cert_path.read_bytes().rstrip(b"\n") + b"\n" + ca.public_bytes(serialization.Encoding.PEM)
    if not fullchain_path.exists() or fullchain_path.read_bytes() != fullchain:
        atomic_write_bytes(fullchain_path, fullchain)

    return CertBundle(ca_cert_path, srv_cert_path, srv_key_path, _fingerprint(ca), issued, fullchain_path, ca_pin(ca))
