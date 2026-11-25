"""OS-level control: input injection, screen capture, power actions."""

import sys


def enable_dpi_awareness() -> None:
    """Make Windows report physical pixels so mss and pynput share one coordinate space."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass
