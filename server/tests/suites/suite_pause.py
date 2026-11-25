"""Pause: live sockets closed with 4423, new ones refused, system actions -> 423, resume works."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import asyncio, json, shutil, ssl, sys, threading, time, urllib.request, urllib.error
from pathlib import Path

import websockets
from padlink.config import Settings
from padlink.runtime import prepare
from padlink.desktop import ServerThread

import tempfile
DATA = Path(tempfile.gettempdir()) / "padlink-test-pause"
shutil.rmtree(DATA, ignore_errors=True)
s = Settings(); s.data_dir = DATA; s.port = 18444; s.log_level = "WARNING"
rt = prepare(s)
srv = ServerThread(rt.uvicorn_config()); srv.start(); assert srv.wait_started()
svc = rt.svc
PW = "test-password-123"
svc.password.set(PW)
ctx = ssl.create_default_context(cafile=str(DATA / "certs" / "padlink-ca.crt"))
BASE, ORIGIN = "https://127.0.0.1:18444", "https://localhost"
fails = []
def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name, "" if ok else extra)
    if not ok: fails.append(name)

def post(path, body, token=None):
    h = {"Content-Type": "application/json", "Origin": ORIGIN}
    if token: h["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, method="POST", data=json.dumps(body).encode(), headers=h)
    try:
        with urllib.request.urlopen(r, context=ctx) as resp: return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

pin = svc.pairing.new_session().pin
_, tok = post("/api/auth/pair", {"secret": pin, "password": PW, "device_name": "T", "client": "app"})
at = tok["access_token"]

async def connect():
    w = await websockets.connect("wss://127.0.0.1:18444/ws/control", ssl=ctx, origin=ORIGIN)
    try:
        await w.send(json.dumps({"t": "auth", "token": at}))
    except websockets.ConnectionClosed:
        pass  # server may close (4423) before our auth message; recv() reports the code
    return w

async def main():
    w = await connect()
    check("ready before pause", json.loads(await w.recv())["t"] == "ready")
    # what the desktop "Pausa" button does (DesktopApp.toggle_pause)
    svc.paused = True
    for dev in svc.registry.device_ids():
        asyncio.run_coroutine_threadsafe(svc.registry.close_device(dev, 4423, "paused"), svc.loop)
    try:
        await asyncio.wait_for(w.recv(), 5); code = None
    except websockets.ConnectionClosed as e: code = e.rcvd.code if e.rcvd else None
    check("live socket closed with 4423", code == 4423, code)
    w2 = await connect()
    try:
        await asyncio.wait_for(w2.recv(), 5); code = None
    except websockets.ConnectionClosed as e: code = e.rcvd.code if e.rcvd else None
    check("new socket refused with 4423", code == 4423, code)
    st, body = post("/api/system/lock", {"confirm": "lock"}, at)
    check("system action -> 423 while paused", st == 423, (st, body))
    svc.paused = False
    w3 = await connect()
    check("ready after resume", json.loads(await w3.recv())["t"] == "ready")
    await w3.close()

asyncio.run(main())
srv.stop(); srv.join(5)
print("RESULT:", "FAILED " + str(fails) if fails else "ALL PASSED")
