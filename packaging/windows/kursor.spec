# PyInstaller spec for the Kursor Windows program.
# Build with packaging/windows/build.ps1 (it compiles the web client first).
#
# One-folder layout on purpose:
#   * starts faster and triggers fewer antivirus false positives than one-file;
#   * keeps LGPL libraries (pynput, pystray) replaceable by the user.
# -*- mode: python -*-
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
SERVER = ROOT / "server"

datas = [
    (str(ROOT / "client" / "dist"), "client_dist"),
    (str(SERVER / "kursor" / "assets"), "kursor/assets"),
    (str(ROOT / "docs" / "legal"), "legal"),
]

hiddenimports = [
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "pystray._win32",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [str(SERVER / "kursor_desktop.py")],
    pathex=[str(SERVER)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "IPython", "matplotlib", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kursor",
    icon=str(SERVER / "kursor" / "assets" / "kursor.ico"),
    version=str(Path(SPECPATH) / "version_info.txt"),
    console=False,
    disable_windowed_traceback=False,
    upx=False,  # UPX-packed binaries are a classic antivirus false-positive trigger
)

coll = COLLECT(exe, a.binaries, a.datas, name="Kursor", upx=False)
