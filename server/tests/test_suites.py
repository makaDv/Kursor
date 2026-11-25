"""Runs every end-to-end suite in tests/suites (each prints PASS/FAIL lines and RESULT).

    cd server && .venv/Scripts/python -m pytest -q tests

suite_api / suite_app_client need a server: they get a fresh one on port 18443.
suite_windows and suite_features touch the real Windows desktop (a throw-away test
window, the clipboard is saved and restored), so they are skipped off Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent
SUITES = HERE / "suites"


def _run(script: str, env: dict | None = None, timeout: int = 240) -> str:
    out = subprocess.run([sys.executable, str(SUITES / script)], cwd=SERVER, env=env or os.environ.copy(),
                         capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    text = out.stdout + out.stderr
    assert "RESULT: ALL PASSED" in out.stdout, text[-4000:]
    return text


@pytest.mark.parametrize("script", ["suite_api.py", "suite_app_client.py"])
def test_against_live_server(script: str) -> None:
    data = Path(tempfile.mkdtemp(prefix="padlink-test-"))
    env = {**os.environ, "PADLINK_DATA_DIR": str(data), "PYTHONIOENCODING": "utf-8"}
    srv = subprocess.Popen([sys.executable, "-m", "padlink", "run", "--port", "18443", "--no-pair",
                            "--log-level", "WARNING"], cwd=SERVER, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(3)
        _run(script, env)
    finally:
        srv.terminate()
        srv.wait(10)
        shutil.rmtree(data, ignore_errors=True)


def test_pause() -> None:
    _run("suite_pause.py")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop APIs")
def test_windows_control() -> None:
    _run("suite_windows.py")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop APIs (clipboard, mDNS on LAN)")
def test_features() -> None:
    _run("suite_features.py")
