"""Open applications (top-level windows) of the interactive desktop: list and manipulate.

Only windows that appear in the taskbar / Alt+Tab are exposed. Every action
re-checks that the handle is still one of those windows, so a client can never
target hidden, system or other-session windows by guessing handles.

Windows only (Win32 via ctypes); on other platforms the list is empty.
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

ACTIONS = ("focus", "minimize", "maximize", "restore", "close", "kill")

# Processes PadLink never force-terminates: killing them would break or log off Windows.
# They can still be focused/minimized like any other window.
PROTECTED = frozenset({
    "explorer.exe", "csrss.exe", "winlogon.exe", "wininit.exe", "dwm.exe", "lsass.exe", "services.exe",
    "smss.exe", "svchost.exe", "system", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe", "taskhostw.exe",
    "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe", "textinputhost.exe",
    "applicationframehost.exe", "lockapp.exe", "logonui.exe", "runtimebroker.exe", "securityhealthsystray.exe",
})


class WindowError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class WindowInfo:
    id: int
    title: str
    app: str
    exe: str
    pid: int
    minimized: bool
    maximized: bool
    focused: bool
    protected: bool


if sys.platform == "win32":
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi")
    version = ctypes.WinDLL("version")

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]

    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_NOACTIVATE = 0x08000000
    DWMWA_CLOAKED = 14
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_TERMINATE = 0x0001
    SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
    WM_CLOSE = 0x0010
    VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002

    def _title(hwnd: int) -> str:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def _is_app_window(hwnd: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or not _title(hwnd):
            return False
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex & WS_EX_APPWINDOW == 0:
            if ex & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) or user32.GetWindow(hwnd, GW_OWNER):
                return False
        cloaked = ctypes.c_int(0)  # suspended UWP apps / windows on other virtual desktops
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 \
                and cloaked.value:
            return False
        return True

    def _pid(hwnd: int) -> int:
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _exe_path(pid: int) -> str:
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value
            return ""
        finally:
            kernel32.CloseHandle(h)

    @lru_cache(maxsize=256)
    def _friendly_name(path: str) -> str:
        """FileDescription from the exe version resource ("Google Chrome"), else the file name."""
        fallback = Path(path).stem if path else "?"
        if not path:
            return fallback
        try:
            size = version.GetFileVersionInfoSizeW(path, None)
            if not size:
                return fallback
            data = ctypes.create_string_buffer(size)
            if not version.GetFileVersionInfoW(path, 0, size, data):
                return fallback
            ptr, length = ctypes.c_void_p(), wintypes.UINT()
            if not version.VerQueryValueW(data, r"\VarFileInfo\Translation", ctypes.byref(ptr), ctypes.byref(length)) \
                    or length.value < 4:
                return fallback
            lang, cp = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD * 2)).contents
            key = rf"\StringFileInfo\{lang:04x}{cp:04x}\FileDescription"
            if version.VerQueryValueW(data, key, ctypes.byref(ptr), ctypes.byref(length)) and length.value > 1:
                desc = ctypes.wstring_at(ptr, length.value - 1).strip()
                if desc:
                    return desc[:60]
        except (OSError, ValueError):
            pass
        return fallback

    def _enum() -> list[int]:
        handles: list[int] = []

        @EnumWindowsProc
        def cb(hwnd: int, _lparam: int) -> bool:
            if _is_app_window(hwnd):
                handles.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        return handles

    def list_windows() -> list[dict]:
        own = os.getpid()
        fg = user32.GetForegroundWindow()
        out = []
        for hwnd in _enum():
            pid = _pid(hwnd)
            if pid == own:
                continue  # PadLink's own window
            path = _exe_path(pid)
            exe = Path(path).name.lower() if path else ""
            out.append(asdict(WindowInfo(
                id=int(hwnd),
                title=_title(hwnd)[:200],
                app=_friendly_name(path),
                exe=exe,
                pid=pid,
                minimized=bool(user32.IsIconic(hwnd)),
                maximized=bool(user32.IsZoomed(hwnd)),
                focused=hwnd == fg,
                protected=exe in PROTECTED or not exe,
            )))
        return out

    def _focus(hwnd: int) -> None:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        fg = user32.GetForegroundWindow()
        me = kernel32.GetCurrentThreadId()
        target = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = bool(target and target != me and user32.AttachThreadInput(me, target, True))
        try:
            user32.BringWindowToTop(hwnd)
            ok = user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(me, target, False)
        if not ok:
            # Foreground lock: a synthetic Alt tap lets this process change the foreground window.
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            user32.SetForegroundWindow(hwnd)

    def window_action(hwnd: int, action: str) -> dict:
        if action not in ACTIONS:
            raise WindowError("unknown_action", "Azione sconosciuta")
        current = {w["id"]: w for w in list_windows()}
        info = current.get(hwnd)
        if info is None:
            raise WindowError("not_found", "Finestra non trovata (forse è stata chiusa)")
        if action == "focus":
            _focus(hwnd)
        elif action == "minimize":
            user32.ShowWindow(hwnd, SW_MINIMIZE)
        elif action == "maximize":
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
        elif action == "restore":
            user32.ShowWindow(hwnd, SW_RESTORE)
        elif action == "close":
            # Same as clicking X: the app may ask to save unsaved work.
            if not user32.PostMessageW(hwnd, WM_CLOSE, 0, 0):
                raise WindowError("access_denied", "Windows non permette di chiudere questa finestra "
                                                   "(probabilmente è un programma avviato come amministratore)")
        elif action == "kill":
            if info["protected"]:
                raise WindowError("protected", "Processo di sistema: non può essere terminato da PadLink")
            h = kernel32.OpenProcess(PROCESS_TERMINATE, False, info["pid"])
            if not h:
                raise WindowError("access_denied", "Accesso negato (programma avviato come amministratore?)")
            try:
                if not kernel32.TerminateProcess(h, 1):
                    raise WindowError("access_denied", "Impossibile terminare il processo")
            finally:
                kernel32.CloseHandle(h)
        return info

else:  # pragma: no cover - non-Windows hosts
    def list_windows() -> list[dict]:
        return []

    def window_action(hwnd: int, action: str) -> dict:
        raise WindowError("unsupported", "Disponibile solo su Windows")
