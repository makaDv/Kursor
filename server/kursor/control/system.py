"""Power/session actions: lock, sleep, shutdown. Fixed argument lists, never a shell."""

from __future__ import annotations

import logging
import subprocess
import sys

log = logging.getLogger(__name__)

ACTIONS = ("lock", "sleep", "shutdown")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def perform(action: str) -> None:
    if action not in ACTIONS:
        raise ValueError("unknown action")

    if sys.platform == "win32":
        import ctypes

        if action == "lock":
            if not ctypes.windll.user32.LockWorkStation():
                raise OSError("LockWorkStation failed")
        elif action == "sleep":
            # SetSuspendState(hibernate=False, force=False, disableWakeEvents=False).
            # Note: if hibernation is enabled system-wide Windows may hibernate instead.
            if not ctypes.windll.powrprof.SetSuspendState(False, False, False):
                raise OSError("SetSuspendState failed")
        else:
            _run(["shutdown", "/s", "/t", "10", "/c", "Kursor: spegnimento remoto"])
    elif sys.platform == "darwin":
        if action == "lock":
            _run(["pmset", "displaysleepnow"])
        elif action == "sleep":
            _run(["pmset", "sleepnow"])
        else:
            _run(["osascript", "-e", 'tell application "System Events" to shut down'])
    else:
        if action == "lock":
            _run(["loginctl", "lock-session"])
        elif action == "sleep":
            _run(["systemctl", "suspend"])
        else:
            _run(["systemctl", "poweroff"])
    log.info("System action executed: %s", action)
