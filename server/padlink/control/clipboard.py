"""Read/write the PC clipboard (Unicode text only). Windows via ctypes; other OS unsupported."""

from __future__ import annotations

import ctypes
import sys
import time

MAX_CHARS = 100_000


class ClipboardError(Exception):
    pass


if sys.platform == "win32":
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    def _open() -> None:
        for _ in range(10):  # another app may hold the clipboard for a moment
            if user32.OpenClipboard(None):
                return
            time.sleep(0.03)
        raise ClipboardError("Appunti occupati da un altro programma")

    def get_text() -> str:
        _open()
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)[:MAX_CHARS]
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def set_text(text: str) -> None:
        text = text[:MAX_CHARS]
        data = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(data)
        _open()
        try:
            user32.EmptyClipboard()
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
            if not handle:
                raise ClipboardError("Memoria insufficiente")
            ptr = kernel32.GlobalLock(handle)
            ctypes.memmove(ptr, data, size)
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                raise ClipboardError("Impossibile scrivere negli appunti")
        finally:
            user32.CloseClipboard()

else:  # pragma: no cover
    def get_text() -> str:
        raise ClipboardError("Disponibile solo su Windows")

    def set_text(text: str) -> None:
        raise ClipboardError("Disponibile solo su Windows")
