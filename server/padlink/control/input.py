"""Mouse and keyboard injection via pynput, with strict validation of every command."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any

from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

log = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 2000
MAX_COMBO_KEYS = 5
MAX_DELTA = 4000.0
MAX_SCROLL = 50.0

BUTTONS = {"left": Button.left, "right": Button.right, "middle": Button.middle}

_KEY_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "altgr": "alt_gr",
    "shift": "shift",
    "win": "cmd",
    "meta": "cmd",
    "cmd": "cmd",
    "super": "cmd",
    "esc": "esc",
    "escape": "esc",
    "enter": "enter",
    "return": "enter",
    "tab": "tab",
    "space": "space",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "insert": "insert",
    "home": "home",
    "end": "end",
    "pageup": "page_up",
    "page_up": "page_up",
    "pagedown": "page_down",
    "page_down": "page_down",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "capslock": "caps_lock",
    "printscreen": "print_screen",
    "print_screen": "print_screen",
    "menu": "menu",
    "volume_up": "media_volume_up",
    "volume_down": "media_volume_down",
    "volume_mute": "media_volume_mute",
    "play_pause": "media_play_pause",
    "next_track": "media_next",
    "prev_track": "media_previous",
}
_KEY_ALIASES.update({f"f{i}": f"f{i}" for i in range(1, 21)})


def _resolve_key(name: str) -> Key | KeyCode:
    if not isinstance(name, str) or not name:
        raise ValueError("invalid key")
    if len(name) == 1:
        return KeyCode.from_char(name.lower() if name.isalpha() else name)
    attr = _KEY_ALIASES.get(name.lower())
    key = getattr(Key, attr, None) if attr else None
    if key is None:
        raise ValueError(f"unknown key: {name[:20]}")
    return key


def _num(value: Any, limit: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected number")
    v = float(value)
    if v != v:  # NaN
        raise ValueError("NaN")
    return max(-limit, min(limit, v))


class InputController:
    def __init__(self) -> None:
        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self._lock = threading.Lock()
        self._rem_x = 0.0
        self._rem_y = 0.0
        self._scroll_rem_x = 0.0
        self._scroll_rem_y = 0.0
        self._held_buttons: set[Button] = set()

    # ---- mouse ---------------------------------------------------------------
    def move_relative(self, dx: Any, dy: Any) -> None:
        fx = _num(dx, MAX_DELTA) + self._rem_x
        fy = _num(dy, MAX_DELTA) + self._rem_y
        ix, iy = int(fx), int(fy)
        self._rem_x, self._rem_y = fx - ix, fy - iy
        if ix or iy:
            with self._lock:
                self.mouse.move(ix, iy)

    def move_absolute(self, nx: Any, ny: Any, monitor: dict[str, int]) -> None:
        x = min(1.0, max(0.0, _num(nx, 1.0)))
        y = min(1.0, max(0.0, _num(ny, 1.0)))
        px = monitor["left"] + round(x * (monitor["width"] - 1))
        py = monitor["top"] + round(y * (monitor["height"] - 1))
        with self._lock:
            self.mouse.position = (px, py)

    def click(self, button: Any, count: Any = 1) -> None:
        btn = BUTTONS.get(button)
        if btn is None:
            raise ValueError("invalid button")
        n = int(count) if isinstance(count, int) and 1 <= count <= 3 else 1
        with self._lock:
            self.mouse.click(btn, n)

    def button(self, button: Any, down: bool) -> None:
        btn = BUTTONS.get(button)
        if btn is None:
            raise ValueError("invalid button")
        with self._lock:
            if down:
                self.mouse.press(btn)
                self._held_buttons.add(btn)
            else:
                self.mouse.release(btn)
                self._held_buttons.discard(btn)

    def scroll(self, dx: Any, dy: Any) -> None:
        sx = _num(dx, MAX_SCROLL)
        sy = _num(dy, MAX_SCROLL)
        with self._lock:
            if sys.platform == "win32":
                # Windows accepts fractional wheel deltas (smooth scrolling).
                self.mouse.scroll(sx, sy)
                return
            fx, fy = sx + self._scroll_rem_x, sy + self._scroll_rem_y
            ix, iy = int(fx), int(fy)
            self._scroll_rem_x, self._scroll_rem_y = fx - ix, fy - iy
            if ix or iy:
                self.mouse.scroll(ix, iy)

    # ---- keyboard ------------------------------------------------------------
    def type_text(self, text: Any) -> None:
        if not isinstance(text, str) or not text:
            raise ValueError("invalid text")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError("text too long")
        with self._lock:
            self.keyboard.type(text)

    def key_combo(self, keys: Any) -> None:
        if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_COMBO_KEYS:
            raise ValueError("invalid key combo")
        resolved = [_resolve_key(k) for k in keys]
        with self._lock:
            pressed: list[Key | KeyCode] = []
            try:
                for k in resolved:
                    self.keyboard.press(k)
                    pressed.append(k)
            finally:
                for k in reversed(pressed):
                    self.keyboard.release(k)

    # ---- safety --------------------------------------------------------------
    def release_all(self) -> None:
        """Called when a client disconnects so no button stays stuck down."""
        with self._lock:
            for btn in list(self._held_buttons):
                try:
                    self.mouse.release(btn)
                except Exception:  # noqa: BLE001
                    log.exception("Failed to release %s", btn)
            self._held_buttons.clear()
