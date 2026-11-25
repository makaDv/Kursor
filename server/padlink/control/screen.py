"""Screen capture (mss) + JPEG/WebP encoding (Pillow) for the streaming WebSocket."""

from __future__ import annotations

import io
import struct
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import mss
from PIL import Image
from pynput.mouse import Controller as MouseController

# Frame header: seq (uint32), cursor_x, cursor_y (float32, normalized, <0 = off-screen),
# width, height (uint16), format (uint8: 0=jpeg, 1=webp), 3 bytes padding. 20 bytes total.
HEADER = struct.Struct("<IffHHB3x")
FORMATS = {"jpeg": 0, "webp": 1}


def list_monitors() -> list[dict[str, int]]:
    """Index 0 is the union of all monitors, 1..N the physical displays (mss convention)."""
    with mss.mss() as sct:
        return [
            {"index": i, "left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
            for i, m in enumerate(sct.monitors)
        ]


@dataclass
class StreamParams:
    fps: int = 12
    quality: int = 60  # target quality chosen by the user
    max_width: int = 1280
    fmt: str = "jpeg"
    monitor: int = 1
    auto: bool = True

    def update(self, data: dict) -> None:
        if isinstance(data.get("fps"), int):
            self.fps = max(1, min(30, data["fps"]))
        if isinstance(data.get("quality"), int):
            self.quality = max(10, min(95, data["quality"]))
        if isinstance(data.get("max_width"), int):
            self.max_width = max(320, min(3840, data["max_width"]))
        if data.get("format") in FORMATS:
            self.fmt = data["format"]
        if isinstance(data.get("monitor"), int):
            self.monitor = max(0, min(16, data["monitor"]))
        if isinstance(data.get("auto"), bool):
            self.auto = data["auto"]


class FrameGrabber:
    """Owns a dedicated thread: mss handles are not shareable across threads."""

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="padlink-grab")
        self._local = threading.local()
        self._last_crc: int | None = None
        self._mouse = MouseController()

    def _sct(self) -> mss.base.MSSBase:
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = mss.mss()
            self._local.sct = sct
        return sct

    def monitor_rect(self, index: int) -> dict[str, int]:
        monitors = self._sct().monitors
        return monitors[index] if 0 <= index < len(monitors) else monitors[1 if len(monitors) > 1 else 0]

    def grab(self, seq: int, params: StreamParams, quality: int, scale: float, force: bool) -> bytes | None:
        """Runs in the grabber thread. Returns an encoded frame, or None if unchanged."""
        sct = self._sct()
        mon = self.monitor_rect(params.monitor)
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        target_w = min(img.width, int(params.max_width * scale))
        if target_w < img.width:
            target_h = max(1, round(img.height * target_w / img.width))
            img = img.resize((target_w, target_h), Image.Resampling.BILINEAR)

        try:
            cx, cy = self._mouse.position
            nx = (cx - mon["left"]) / mon["width"]
            ny = (cy - mon["top"]) / mon["height"]
            if not (0 <= nx <= 1 and 0 <= ny <= 1):
                nx = ny = -1.0
        except Exception:  # noqa: BLE001
            nx = ny = -1.0

        crc = zlib.crc32(img.tobytes(), int((nx + 2) * 10_000) ^ int((ny + 2) * 10_000))
        if not force and crc == self._last_crc:
            return None
        self._last_crc = crc

        buf = io.BytesIO()
        if params.fmt == "webp":
            img.save(buf, "WEBP", quality=quality, method=0)
        else:
            img.save(buf, "JPEG", quality=quality, optimize=False, progressive=False)
        header = HEADER.pack(seq & 0xFFFFFFFF, nx, ny, img.width, img.height, FORMATS[params.fmt])
        return header + buf.getvalue()

    def reset(self) -> None:
        self._last_crc = None

    def close(self) -> None:
        def _close() -> None:
            sct = getattr(self._local, "sct", None)
            if sct is not None:
                sct.close()

        try:
            self.executor.submit(_close).result(timeout=2)
        except Exception:  # noqa: BLE001
            pass
        self.executor.shutdown(wait=False, cancel_futures=True)
