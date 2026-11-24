"""New server features: permissions, PC approval, clipboard, persisted lockout, QR cleanup,
inactive-device purge, PC info in 'ready', mDNS announcement."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import asyncio, json, shutil, ssl, sys, threading, time, urllib.request, urllib.error
from pathlib import Path

import websockets
from kursor.config import Settings
from kursor.runtime import prepare
from kursor.desktop import ServerThread
from kursor.control import clipboard
from kursor.security.ratelimit import LoginGuard

import tempfile
DATA = Path(tempfile.gettempdir()) / "padlink-test-features"
shutil.rmtree(DATA, ignore_errors=True)
s = Settings(); s.data_dir = DATA; s.port = 18445; s.log_level = "WARNING"
rt = prepare(s)
srv = ServerThread(rt.uvicorn_config()); srv.start(); assert srv.wait_started()
svc = rt.svc
PW = "test-password-123"
svc.password.set(PW)
ctx = ssl.create_default_context(cafile=str(DATA / "certs" / "kursor-ca.crt"))
BASE, ORIGIN = "https://127.0.0.1:18445", "https://localhost"
fails = []
def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name, "" if ok else extra)
    if not ok: fails.append(name)

def call(method, path, body=None, token=None):
    h = {"Content-Type": "application/json", "Origin": ORIGIN}
    if token: h["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, context=ctx) as resp: return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

def pair(name):
    pin = svc.pairing.new_session().pin
    _, tok = call("POST", "/api/auth/pair", {"secret": pin, "password": PW, "device_name": name, "client": "app"})
    return tok

async def ws_first(path, token, read=2):
    out = []
    w = await websockets.connect(f"wss://127.0.0.1:18445{path}", ssl=ctx, origin=ORIGIN)
    try:
        await w.send(json.dumps({"t": "auth", "token": token}))
    except websockets.ConnectionClosed:
        pass
    try:
        for _ in range(read):
            out.append(json.loads(await asyncio.wait_for(w.recv(), 8)))
            if out[-1].get("t") == "ready": break
    except websockets.ConnectionClosed as e:
        out.append({"closed": e.rcvd.code if e.rcvd else None, "reason": e.rcvd.reason if e.rcvd else None})
    except asyncio.TimeoutError:
        out.append({"timeout": True})
    await w.close()
    return out

A = pair("Pixel A")
at = A["access_token"]; dev = A["device_id"]

# ---- ready carries perms + pc info
msgs = asyncio.run(ws_first("/ws/control", at))
ready = msgs[-1]
check("ready has perms", ready.get("perms") == {"screen": True, "apps": True, "clipboard": True, "power": True}, ready)
check("ready has pc name+mac", bool(ready.get("pc", {}).get("name")) and "mac" in ready.get("pc", {}), ready.get("pc"))

# ---- permissions
svc.store.set_perms(dev, {"screen": False, "apps": False, "clipboard": False, "power": False})
check("screen WS refused (no_permission)", asyncio.run(ws_first("/ws/screen", at))[-1] == {"closed": 4403, "reason": "no_permission"})
check("control WS still allowed", asyncio.run(ws_first("/ws/control", at))[-1].get("t") == "ready")
check("power -> 403", call("POST", "/api/system/lock", {"confirm": "lock"}, at)[0] == 403)
check("windows list -> 403", call("GET", "/api/windows", None, at)[0] == 403)
check("clipboard -> 403", call("POST", "/api/clipboard/get", {}, at)[0] == 403)
check("monitors -> 403 without screen perm", call("GET", "/api/screen/monitors", None, at)[0] == 403)
st, body = call("GET", "/api/pc", None, at)
check("/api/pc reports limited perms", st == 200 and body["perms"]["power"] is False, body)
svc.store.set_perms(dev, {"screen": True, "apps": True, "clipboard": True, "power": True})

# ---- clipboard round trip (restores the user's clipboard afterwards)
saved = clipboard.get_text()
try:
    st, _ = call("POST", "/api/clipboard/set", {"text": "padlink-test-✓"}, at)
    st2, got = call("POST", "/api/clipboard/get", {}, at)
    check("clipboard set/get round trip", st == 200 and got.get("text") == "padlink-test-✓", (st, got))
    check("clipboard read notifies the PC", any("appunti" in e[1] for e in svc.events))
finally:
    clipboard.set_text(saved)

# ---- approval on the PC
svc.prefs.update(require_approval=True); svc.approver_available = True
async def approval(allow):
    w = await websockets.connect("wss://127.0.0.1:18445/ws/control", ssl=ctx, origin=ORIGIN)
    await w.send(json.dumps({"t": "auth", "token": at}))
    first = json.loads(await asyncio.wait_for(w.recv(), 5))
    for _ in range(50):
        if dev in svc.approvals: break
        await asyncio.sleep(0.05)
    svc.answer_approval(dev, allow)  # what the "Consenti / Rifiuta" dialog calls
    try:
        second = json.loads(await asyncio.wait_for(w.recv(), 5))
    except websockets.ConnectionClosed as e:
        second = {"closed": e.rcvd.code, "reason": e.rcvd.reason}
    await w.close()
    return first, second
svc.approved.clear()
f, sec = asyncio.run(approval(False))
check("approval_pending sent", f.get("t") == "approval_pending", f)
check("denied on PC -> 4403 denied", sec == {"closed": 4403, "reason": "denied"}, sec)
f, sec = asyncio.run(approval(True))
check("allowed on PC -> ready", sec.get("t") == "ready", sec)
check("allowed device not asked again", asyncio.run(ws_first("/ws/control", at))[0].get("t") == "ready")
svc.prefs.update(require_approval=False); svc.approver_available = False

# ---- persisted lockout
svc.pairing.new_session()  # failures only count while a pairing window is open
for _ in range(5):
    call("POST", "/api/auth/pair", {"secret": "000000", "password": PW, "device_name": "x", "client": "app"})
g = LoginGuard(path=s.lockout_file)
check("lockout survives restart (file)", g.retry_after("127.0.0.1") > 0, s.lockout_file.read_text() if s.lockout_file.exists() else "no file")
svc.guard.success("127.0.0.1")

# ---- PC password: wrong passwords on refresh, revocation after 10, change invalidates tokens
C = pair("Pw phone")
st, body = call("POST", "/api/auth/refresh", {"refresh_token": C["refresh_token"], "password": "nope-nope"})
check("refresh wrong password -> 401 invalid_password", st == 401 and body["detail"]["code"] == "invalid_password", body)
st, body = call("POST", "/api/auth/refresh", {"refresh_token": C["refresh_token"], "password": PW})
check("refresh token not spent by wrong password", st == 200 and body.get("refresh_token"), body)
check("successful refresh resets device counter", svc.store._devices[C["device_id"]].get("pw_failures") == 0)
svc.guard.success("127.0.0.1")
left = [svc.store.password_failed(C["device_id"]) for _ in range(10)]
check("device revoked after 10 wrong passwords", left[-2] == 1 and left[-1] == 0 and not svc.store.exists(C["device_id"]), left)
D = pair("Pw change")
check("access token works", call("GET", "/api/pc", None, D["access_token"])[0] == 200)
svc.password.set("another-password-456")
st, body = call("GET", "/api/pc", None, D["access_token"])
check("password change -> old access token reported expired", st == 401 and body["detail"]["code"] == "token_expired", body)
st, body = call("POST", "/api/auth/refresh", {"refresh_token": D["refresh_token"], "password": PW})
check("old password refused after change", st == 401 and body["detail"]["code"] == "invalid_password", body)
st, body = call("POST", "/api/auth/refresh", {"refresh_token": D["refresh_token"], "password": "another-password-456"})
check("new password accepted", st == 200, body)
svc.password.set(PW); svc.guard.success("127.0.0.1")

# ---- QR image removed when the pairing ends
png = DATA / "pairing-qr.png"
png.write_bytes(b"x"); svc.pairing.new_session(); svc.pairing.close()
check("pairing-qr.png deleted on close", not png.exists())
png.write_bytes(b"x"); pin = svc.pairing.new_session().pin; svc.pairing.verify(pin)
check("pairing-qr.png deleted after use", not png.exists())

# ---- inactive purge helper
B = pair("Old phone")
d = svc.store._devices[B["device_id"]]; d["last_seen"] = time.time() - 100 * 86400; svc.store._save()
check("stale() finds 100-day-old device", B["device_id"] in svc.store.stale(90 * 86400))

# ---- mDNS announcement (browse it back with zeroconf)
started = rt.start_discovery()
from zeroconf import Zeroconf, ServiceBrowser
found = []
class L:
    def add_service(self, zc, t, name):
        info = zc.get_service_info(t, name, 3000)
        if info: found.append(info)
    def update_service(self, *a): pass
    def remove_service(self, *a): pass
zc = Zeroconf(); ServiceBrowser(zc, "_padlink._tcp.local.", L())
for _ in range(40):
    if found: break
    time.sleep(0.1)
zc.close(); rt.stop_discovery()
fp = found[0].properties.get(b"fp", b"").decode() if found else ""
check("mDNS announced with fp", started and fp == rt.bundle.ca_pin, (started, fp))

srv.stop(); srv.join(5)
print("RESULT:", "FAILED " + str(fails) if fails else "ALL PASSED")
