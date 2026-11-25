"""mDNS / DNS-SD announcement: ``_padlink._tcp.local.``

Lets the phone app find the PC again after its IP changes (DHCP). The TXT record
carries the CA fingerprint (``fp``): the app only reconnects to a PC whose
fingerprint equals the pinned one, so a spoofed announcement is useless (and the
TLS pinning would refuse it anyway). Nothing secret is announced.
"""

from __future__ import annotations

import logging
import socket

log = logging.getLogger(__name__)
SERVICE = "_padlink._tcp.local."


class Announcer:
    def __init__(self) -> None:
        self._zc = None
        self._info = None

    def start(self, port: int, ips: list[str], name: str, fp: str | None) -> bool:
        try:
            from zeroconf import IPVersion, ServiceInfo, Zeroconf
        except ImportError:
            log.info("zeroconf not installed: mDNS discovery disabled")
            return False
        if not ips:
            return False
        safe = "".join(c for c in name if c.isalnum() or c in "-_")[:40] or "pc"
        props = {"v": "1", "name": name[:60]}
        if fp:
            props["fp"] = fp
        try:
            self._info = ServiceInfo(
                SERVICE,
                f"PadLink-{safe}.{SERVICE}",
                addresses=[socket.inet_aton(ip) for ip in ips],
                port=port,
                properties=props,
                server=f"{safe}.local.",
            )
            self._zc = Zeroconf(interfaces=ips, ip_version=IPVersion.V4Only)
            self._zc.register_service(self._info, allow_name_change=True)
            log.info("mDNS: announced %s on %s", SERVICE, ", ".join(ips))
            return True
        except Exception:  # noqa: BLE001 - discovery is a convenience, never fatal
            log.exception("mDNS announcement failed")
            self.stop()
            return False

    def stop(self) -> None:
        try:
            if self._zc is not None:
                if self._info is not None:
                    self._zc.unregister_service(self._info)
                self._zc.close()
        except Exception:  # noqa: BLE001
            pass
        self._zc = None
        self._info = None
