"""Kursor command line.

    python -m kursor run            start the daemon (opens a pairing window)
    python -m kursor pair           open a new 5-minute pairing window (PIN + QR)
    python -m kursor devices        list paired devices
    python -m kursor revoke <id>    revoke one device (live sessions closed within ~2 s)
    python -m kursor revoke-all     revoke every device and rotate the signing secret
    python -m kursor cert [--force] create/renew the local CA and server certificate
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import logging
import sys
import time
from pathlib import Path

from . import __version__
from .config import Settings


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", line_buffering=True)  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _settings_from_args(args: argparse.Namespace) -> Settings:
    s = Settings()
    if getattr(args, "data_dir", None):
        s.data_dir = Path(args.data_dir).expanduser()
    if getattr(args, "host", None):
        s.host = args.host
    if getattr(args, "port", None):
        s.port = args.port
    if getattr(args, "no_tls", False):
        s.tls = False
    if getattr(args, "public_origin", None):
        s.public_origin = args.public_origin.rstrip("/")
    if getattr(args, "allow_origin", None):
        s.extra_origins = list(args.allow_origin)
    if getattr(args, "trust_proxy", False):
        s.trust_proxy = True
    if getattr(args, "dev", False):
        s.dev = True
    if getattr(args, "log_level", None):
        s.log_level = args.log_level
    return s


def _base_url(s: Settings) -> str:
    if s.public_origin:
        return s.public_origin
    from .netutil import primary_lan_ip

    ip = primary_lan_ip() or "127.0.0.1"
    return f"{s.scheme}://{ip}:{s.port}"


def _print_pairing(s: Settings, pin: str, code: str, expires_at: float) -> None:
    import qrcode

    url = f"{_base_url(s)}/#pair={code}"
    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    png_path = s.data_dir / "pairing-qr.png"
    try:
        qr.make_image().save(png_path)
    except Exception:  # noqa: BLE001
        png_path = None

    expires = dt.datetime.fromtimestamp(expires_at).strftime("%H:%M:%S")
    print()
    print("  ┌─ PAIRING ─────────────────────────────────────────────")
    print(f"  │ PIN:     {pin[:3]} {pin[3:]}   (valido fino alle {expires}, monouso)")
    print("  │ Oppure inquadra il QR con la fotocamera del telefono:")
    print("  └───────────────────────────────────────────────────────")
    print(buf.getvalue())
    if png_path:
        print(f"  QR salvato anche in: {png_path}")
    print("  Non condividere PIN/QR: chi li usa entro la scadenza ottiene il controllo del PC.\n")


def cmd_run(args: argparse.Namespace) -> int:
    import uvicorn

    from .app import create_app
    from .certs import ensure_certificates
    from .control import enable_dpi_awareness
    from .logging_setup import audit, setup_logging
    from .netutil import hostname
    from .services import Services

    s = _settings_from_args(args)
    if not s.tls and s.host not in ("127.0.0.1", "localhost", "::1") and not args.insecure_lan:
        print("ERRORE: --no-tls è consentito solo con --host 127.0.0.1 (dietro un tunnel cifrato).\n"
              "Usa --insecure-lan solo se sai esattamente cosa stai facendo.", file=sys.stderr)
        return 2

    audit_path = setup_logging(s.log_dir, s.log_level)
    enable_dpi_awareness()
    svc = Services.build(s)

    ssl_kwargs: dict = {}
    ca_info = ""
    if s.tls:
        bundle = ensure_certificates(s.cert_dir, svc.lan_ips, hostname())
        ssl_kwargs = {
            "ssl_certfile": str(bundle.server_cert),
            "ssl_keyfile": str(bundle.server_key),
            "ssl_ciphers": "ECDHE+AESGCM:ECDHE+CHACHA20",
        }
        ca_info = bundle.ca_fingerprint

    base = _base_url(s)
    print(f"\n  Kursor v{__version__}")
    print(f"  URL:            {base}")
    if s.tls:
        print(f"  Certificato CA: {base}/ca.crt")
        print(f"  CA SHA-256:     {ca_info}")
    if s.public_origin:
        print(f"  Origine tunnel: {s.public_origin}")
    print(f"  Dispositivi:    {len(svc.store.list())} associati")
    print(f"  Log accessi:    {audit_path}")
    if not (s.static_dir / "index.html").exists():
        print(f"  ATTENZIONE: client non compilato in {s.static_dir} (cd client && npm run build)")

    if not args.no_pair:
        session = svc.pairing.new_session()
        _print_pairing(s, session.pin, session.code, session.expires_at)
        audit("pairing_opened", source="startup")
    else:
        svc.pairing.close()

    audit("server_start", version=__version__, host=s.host, port=s.port, tls=s.tls)
    uvicorn.run(
        create_app(svc),
        host=s.host,
        port=s.port,
        log_level=s.log_level.lower(),
        server_header=False,
        proxy_headers=False,
        access_log=False,
        ws_max_size=1024 * 1024,
        ws_ping_interval=20,
        ws_ping_timeout=20,
        **ssl_kwargs,
    )
    return 0


def cmd_pair(args: argparse.Namespace) -> int:
    from .fsutil import ensure_private_dir
    from .logging_setup import audit, setup_logging
    from .security.pairing import PairingManager
    from .security.tokens import load_or_create_secret

    s = _settings_from_args(args)
    ensure_private_dir(s.data_dir)
    setup_logging(s.log_dir, "WARNING")
    secret = load_or_create_secret(s.secret_file)
    mgr = PairingManager(s.pairing_file, secret, s.pairing_ttl, s.max_failed_attempts)
    session = mgr.new_session()
    audit("pairing_opened", source="cli")
    _print_pairing(s, session.pin, session.code, session.expires_at)
    return 0


def _store(s: Settings):
    from .security.store import DeviceStore

    return DeviceStore(s.devices_file, s.refresh_ttl)


def cmd_devices(args: argparse.Namespace) -> int:
    s = _settings_from_args(args)
    devices = _store(s).list()
    if not devices:
        print("Nessun dispositivo associato.")
        return 0
    fmt = "%Y-%m-%d %H:%M"
    print(f"{'ID':<18}{'NOME':<24}{'ASSOCIATO':<18}{'ULTIMO ACCESSO':<18}IP")
    for d in devices:
        print(
            f"{d.id:<18}{d.name[:22]:<24}"
            f"{time.strftime(fmt, time.localtime(d.created_at)):<18}"
            f"{time.strftime(fmt, time.localtime(d.last_seen)):<18}{d.last_ip}"
        )
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    from .logging_setup import audit, setup_logging

    s = _settings_from_args(args)
    setup_logging(s.log_dir, "WARNING")
    store = _store(s)
    device_id = store.resolve(args.device_id)
    if not device_id or not store.revoke(device_id):
        print("Dispositivo non trovato (o prefisso ambiguo).", file=sys.stderr)
        return 1
    audit("device_revoked", device=device_id, by="cli")
    print(f"Revocato {device_id}. Le sessioni attive verranno chiuse entro pochi secondi.")
    return 0


def cmd_revoke_all(args: argparse.Namespace) -> int:
    from .logging_setup import audit, setup_logging
    from .security.tokens import rotate_secret

    s = _settings_from_args(args)
    setup_logging(s.log_dir, "WARNING")
    count = _store(s).revoke_all()
    rotate_secret(s.secret_file)
    s.pairing_file.unlink(missing_ok=True)  # its MAC key changed with the secret
    audit("all_devices_revoked", count=count, by="cli")
    print(f"Revocati {count} dispositivi, chiave di firma ruotata.")
    return 0


def cmd_cert(args: argparse.Namespace) -> int:
    from .certs import ensure_certificates
    from .logging_setup import setup_logging
    from .netutil import hostname, lan_ipv4_addresses

    s = _settings_from_args(args)
    setup_logging(s.log_dir, "INFO")
    bundle = ensure_certificates(s.cert_dir, lan_ipv4_addresses(), hostname(), force=args.force)
    print(f"CA:          {bundle.ca_cert}")
    print(f"CA SHA-256:  {bundle.ca_fingerprint}")
    print(f"Server cert: {bundle.server_cert}")
    if args.force:
        print("ATTENZIONE: nuova CA generata. Reinstallala sul telefono.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kursor", description="Kursor: controllo remoto sicuro del PC")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--data-dir", help="cartella dati (default ~/.kursor o $KURSOR_DATA_DIR)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def url_opts(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--port", type=int, default=8443)
        sp.add_argument("--no-tls", action="store_true", help="HTTP in chiaro (solo dietro tunnel su 127.0.0.1)")
        sp.add_argument("--public-origin", help="es. https://kursor.tuodominio.it (tunnel)")

    r = sub.add_parser("run", help="avvia il server")
    url_opts(r)
    r.add_argument("--host", default="0.0.0.0")
    r.add_argument("--allow-origin", action="append", help="origine aggiuntiva consentita (ripetibile)")
    r.add_argument("--trust-proxy", action="store_true", help="usa CF-Connecting-IP/X-Forwarded-For da 127.0.0.1")
    r.add_argument("--dev", action="store_true", help="consenti il dev server Vite (porta 5173)")
    r.add_argument("--no-pair", action="store_true", help="non aprire una finestra di pairing all'avvio")
    r.add_argument("--insecure-lan", action="store_true", help=argparse.SUPPRESS)
    r.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    r.set_defaults(func=cmd_run)

    pa = sub.add_parser("pair", help="genera un nuovo PIN/QR di pairing")
    url_opts(pa)
    pa.set_defaults(func=cmd_pair)

    sub.add_parser("devices", help="elenca i dispositivi associati").set_defaults(func=cmd_devices)

    rv = sub.add_parser("revoke", help="revoca un dispositivo")
    rv.add_argument("device_id", help="ID o prefisso univoco")
    rv.set_defaults(func=cmd_revoke)

    sub.add_parser("revoke-all", help="revoca tutti i dispositivi").set_defaults(func=cmd_revoke_all)

    c = sub.add_parser("cert", help="genera/rinnova i certificati TLS locali")
    c.add_argument("--force", action="store_true", help="rigenera anche la CA")
    c.set_defaults(func=cmd_cert)
    return p


def main(argv: list[str] | None = None) -> int:
    _utf8_console()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 0
    except Exception:  # noqa: BLE001
        logging.getLogger("kursor").exception("Errore fatale")
        return 1


if __name__ == "__main__":
    sys.exit(main())
