import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import asyncio, json, os, ssl, struct, subprocess, sys, time, urllib.request, urllib.error
from http.cookies import SimpleCookie
from pathlib import Path

from kursor.security.pairing import PairingManager
from kursor.security.tokens import load_or_create_secret
import websockets

DATA = Path(os.environ["KURSOR_DATA_DIR"])
BASE = "https://127.0.0.1:18443"
ORIGIN = BASE
ctx = ssl.create_default_context(cafile=str(DATA / "certs" / "kursor-ca.crt"))

def req(method, path, body=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    r = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, context=ctx) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read() or b"null")

def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, extra if not cond else "")
    if not cond: check.failed = True
check.failed = False

for _ in range(50):
    try:
        s, h, b = req("GET", "/api/health"); break
    except Exception: time.sleep(0.2)
check("health over verified TLS", s == 200 and b["status"] == "ok")
check("security headers", "content-security-policy" in h and h.get("x-frame-options") == "DENY", h)

mgr = PairingManager(DATA / "pairing.json", load_or_create_secret(DATA / "secret.key"), 300, 5)
sess = mgr.new_session()

s, _, b = req("POST", "/api/auth/pair", {"secret": "000000" if sess.pin != "000000" else "111111", "device_name": "t"}, {"Origin": ORIGIN})
check("wrong pin -> 401 + remaining", s == 401 and b["detail"]["remaining_attempts"] == 4, b)
s, _, b = req("POST", "/api/auth/pair", {"secret": sess.pin, "device_name": "t"})
check("no Origin -> 403", s == 403, b)
s, _, b = req("POST", "/api/auth/pair", {"secret": sess.pin, "device_name": "t"}, {"Origin": "https://evil.example"})
check("bad Origin -> 403", s == 403, b)
s, _, b = req("GET", "/api/health", headers={"Host": "evil.example"})
check("bad Host -> 421", s == 421, b)

s, h, b = req("POST", "/api/auth/pair", {"secret": sess.pin, "device_name": "Smoke"}, {"Origin": ORIGIN})
check("correct pin -> 200", s == 200 and "access_token" in b, b)
token = b["access_token"]
c = SimpleCookie(); c.load(h["set-cookie"])
rt = c["kursor_rt"].value
check("refresh cookie flags", all(x in h["set-cookie"].lower() for x in ["httponly", "secure", "samesite=strict", "path=/api/auth"]), h["set-cookie"])

s, _, b = req("POST", "/api/auth/pair", {"secret": sess.pin, "device_name": "x"}, {"Origin": ORIGIN})
check("pin single-use", s == 401 and b["detail"]["code"] == "pairing_closed", b)

s, _, b = req("GET", "/api/devices", headers={"Authorization": "Bearer " + token})
check("devices list", s == 200 and len(b["devices"]) == 1 and b["devices"][0]["current"], b)
s, _, b = req("GET", "/api/devices", headers={"Authorization": "Bearer garbage"})
check("bad bearer -> 401", s == 401, b)

s, h, b = req("POST", "/api/auth/refresh", {}, {"Origin": ORIGIN, "Cookie": f"kursor_rt={rt}"})
check("refresh rotates", s == 200 and "access_token" in b, b)
c = SimpleCookie(); c.load(h["set-cookie"]); rt2 = c["kursor_rt"].value
check("new refresh token differs", rt2 != rt)

s, _, b = req("POST", "/api/system/shutdown", {"confirm": "nope"}, {"Origin": ORIGIN, "Authorization": "Bearer " + token})
check("system action needs confirm", s == 400, b)

async def ws_tests():
    async with websockets.connect("wss://127.0.0.1:18443/ws/control", ssl=ctx, origin=ORIGIN) as ws:
        await ws.send(json.dumps({"t": "auth", "token": token}))
        ready = json.loads(await ws.recv())
        check("ws control ready", ready["t"] == "ready" and ready["monitors"], ready)
        await ws.send(json.dumps({"t": "move", "dx": 0, "dy": 0}))
        await ws.send(json.dumps({"t": "bogus"}))
        err = json.loads(await ws.recv())
        check("unknown cmd -> error", err["t"] == "error", err)
        await ws.send(json.dumps({"t": "keys", "k": ["notakey"]}))
        err = json.loads(await ws.recv())
        check("invalid key rejected", err["t"] == "error", err)
        await ws.send(json.dumps({"t": "ping", "ts": 1}))
        check("ping/pong", json.loads(await ws.recv())["t"] == "pong")

    try:
        async with websockets.connect("wss://127.0.0.1:18443/ws/control", ssl=ctx, origin="https://evil.example") as ws:
            await ws.recv()
        check("ws bad origin rejected", False)
    except Exception as e:
        check("ws bad origin rejected", True)

    async with websockets.connect("wss://127.0.0.1:18443/ws/control", ssl=ctx, origin=ORIGIN) as ws:
        await ws.send(json.dumps({"t": "auth", "token": "x.y.z"}))
        try:
            await ws.recv(); check("ws bad token closed", False)
        except websockets.ConnectionClosed as e:
            check("ws bad token -> 4401", e.rcvd.code == 4401, e)

    async with websockets.connect("wss://127.0.0.1:18443/ws/screen", ssl=ctx, origin=ORIGIN, max_size=None) as ws:
        await ws.send(json.dumps({"t": "auth", "token": token}))
        json.loads(await ws.recv())
        await ws.send(json.dumps({"t": "start", "params": {"fps": 5, "quality": 50, "max_width": 640}}))
        frame = await asyncio.wait_for(ws.recv(), 10)
        seq, cx, cy, w, hh, fmt = struct.unpack("<IffHHB3x", frame[:20])
        check("screen frame", isinstance(frame, bytes) and seq == 1 and w <= 640 and frame[20:22] == b"\xff\xd8", (seq, w, hh, fmt))
        await ws.send(json.dumps({"t": "ack", "seq": seq}))
        await ws.send(json.dumps({"t": "stop"}))

    # live revocation via CLI closes the socket with 4409
    async with websockets.connect("wss://127.0.0.1:18443/ws/control", ssl=ctx, origin=ORIGIN) as ws:
        await ws.send(json.dumps({"t": "auth", "token": token}))
        ready = json.loads(await ws.recv())
        dev = json.loads((DATA / "devices.json").read_text())["devices"]
        did = list(dev)[0]
        out = subprocess.run([sys.executable, "-m", "kursor", "revoke", did[:6]], capture_output=True, text=True,
                             cwd=r"C:\Users\david\Desktop\Kursor\server")
        check("cli revoke", out.returncode == 0, out.stderr + out.stdout)
        try:
            await asyncio.wait_for(ws.recv(), 6); check("revoked ws closed", False)
        except websockets.ConnectionClosed as e:
            check("revoked ws -> 4409", e.rcvd.code == 4409, e)

asyncio.run(ws_tests())

s, _, b = req("GET", "/api/devices", headers={"Authorization": "Bearer " + token})
check("revoked access token rejected", s == 401 and b["detail"]["code"] == "device_revoked", b)
s, _, b = req("POST", "/api/auth/refresh", {}, {"Origin": ORIGIN, "Cookie": f"kursor_rt={rt2}"})
check("revoked refresh rejected", s == 401, b)

# brute force: new session, 5 wrong attempts -> lockout + pairing destroyed
sess = mgr.new_session()
codes = []
for i in range(5):
    wrong = f"{(int(sess.pin) + 1 + i) % 1000000:06d}"
    s, _, b = req("POST", "/api/auth/pair", {"secret": wrong, "device_name": "t"}, {"Origin": ORIGIN})
    codes.append(s)
check("lockout after 5 fails", codes[-1] == 429 and codes[:3] == [401, 401, 401], codes)
s, _, b = req("POST", "/api/auth/pair", {"secret": sess.pin, "device_name": "t"}, {"Origin": ORIGIN})
check("locked even with right pin", s == 429 and b["detail"]["retry_after"] > 0, b)
check("pairing destroyed", not (DATA / "pairing.json").exists())

print("\nRESULT:", "FAILED" if check.failed else "ALL PASSED")
