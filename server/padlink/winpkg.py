"""Detects whether PadLink runs as an MSIX package (Microsoft Store build).

Packaged builds are updated by the Store (the self-updater is off, as Store policy
requires) and use the manifest's StartupTask instead of the HKCU Run key.
"""

from __future__ import annotations

import sys

APPMODEL_ERROR_NO_PACKAGE = 15700


def is_packaged() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        length = wintypes.UINT(0)
        rc = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
    except (AttributeError, OSError):
        return False
    return rc != APPMODEL_ERROR_NO_PACKAGE


def started_at_logon(max_uptime_s: float = 180.0) -> bool:
    """StartupTask cannot pass --minimized: a packaged launch right after boot counts as autostart."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        return ctypes.windll.kernel32.GetTickCount64() / 1000 < max_uptime_s
    except (AttributeError, OSError):
        return False
