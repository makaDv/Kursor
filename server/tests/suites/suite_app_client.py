import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import asyncio, json, os, ssl, sys, time, urllib.request, urllib.error
from pathlib import Path
from kursor.security.pairing import PairingManager
from kursor.security.tokens import load_or_create_secret
import websockets

DATA = Path(os.environ["KURSOR_DATA_DIR"]); BASE = "https://127.0.0.1:18443"; APP = "https://localhost"
ctx = ssl.create_default_context(cafile=str(DATA / "certs" / "kursor-ca.crt"))
fails = []
def check(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: fails.append(n)
def req(method, path, body=None, headers=None):
    r = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(r, context=ctx) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, (lambda d: json.loads(d) if d[:1] in (b"{", b"[") else d)(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, (lambda d: json.loads(d) if d[:1] in (b"{", b"[") else d)(e.read())

for _ in range(50):
    try: req("GET", "/api/health"); break
    except Exception: time.sleep(0.2)

s, h, _ = req("OPTIONS", "/api/auth/pair", headers={"Origin": APP, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
check("CORS preflight app origin", s == 200 and h.get("access-control-allow-origin") == APP, (s, h))
s, h, _ = req("OPTIONS", "/api/auth/pair", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
check("CORS preflight evil rejected", h.get("access-control-allow-origin") is None, (s, h))
check("no credentials in CORS", "access-control-allow-credentials" not in h)

mgr = PairingManager(DATA / "pairing.json", load_or_create_secret(DATA / "secret.key"), 300, 5)
pin = mgr.new_session().pin
s, h, b = req("POST", "/api/auth/pair", {"secret": pin, "device_name": "Pixel", "client": "app"}, {"Origin": APP})
check("app pair -> refresh in body, no cookie", s == 200 and b.get("refresh_token") and "set-cookie" not in h, (s, b, h.get("set-cookie")))
check("CORS header on response", h.get("access-control-allow-origin") == APP)
rt, at = b["refresh_token"], b["access_token"]

s, h, b = req("POST", "/api/auth/refresh", {"refresh_token": rt}, {"Origin": APP})
check("app refresh via body rotates", s == 200 and b.get("refresh_token") and b["refresh_token"] != rt, b)
rt2 = b["refresh_token"]

async def ws():
    async with websockets.connect("wss://127.0.0.1:18443/ws/control", ssl=ctx, origin=APP) as w:
        await w.send(json.dumps({"t": "auth", "token": at}))
        check("ws from app origin", json.loads(await w.recv())["t"] == "ready")
asyncio.run(ws())

time.sleep(16)  # past reuse grace window
s, _, b = req("POST", "/api/auth/refresh", {"refresh_token": rt}, {"Origin": APP})
check("reused old refresh -> revoked", s == 401 and b["detail"]["code"] == "reuse_detected", b)
s, _, b = req("POST", "/api/auth/refresh", {"refresh_token": rt2}, {"Origin": APP})
check("device gone after reuse", s == 401, b)
print("RESULT:", "FAILED " + str(fails) if fails else "ALL PASSED")
