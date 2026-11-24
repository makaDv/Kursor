"""FastAPI application: auth API, device management, system actions, PWA hosting."""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .control import clipboard, system, windows
from .fsutil import mtime_ns
from .logging_setup import audit
from .netutil import is_lan_peer, resolve_client_ip
from .security.pairing import PairResult
from .security.store import RefreshError
from .services import Services
from .ws import control_endpoint, screen_endpoint

log = logging.getLogger(__name__)

REFRESH_COOKIE = "kursor_rt"
REFRESH_COOKIE_PATH = "/api/auth"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SAFE_HOST = re.compile(r"^[A-Za-z0-9.\-:\[\]]{1,255}$")


# ---- helpers ----------------------------------------------------------------
def _svc(request: Request) -> Services:
    return request.app.state.svc


def client_ip(request: Request) -> str:
    svc = _svc(request)
    return resolve_client_ip(request.client.host if request.client else None, request.headers, svc.settings.trust_proxy)


def error(status: int, code: str, message: str, *, retry_after: int | None = None, clear_cookie: bool = False,
          svc: Services | None = None) -> JSONResponse:
    detail: dict[str, Any] = {"code": code, "message": message}
    headers = {}
    if retry_after:
        detail["retry_after"] = retry_after
        headers["Retry-After"] = str(retry_after)
    resp = JSONResponse({"detail": detail}, status_code=status, headers=headers)
    if clear_cookie and svc is not None:
        _clear_refresh_cookie(resp, svc)
    return resp


def _set_refresh_cookie(resp: Response, svc: Services, token: str) -> None:
    resp.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=svc.settings.refresh_ttl,
        path=REFRESH_COOKIE_PATH,
        secure=svc.settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(resp: Response, svc: Services) -> None:
    resp.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, secure=svc.settings.secure_cookies, httponly=True, samesite="strict"
    )


def _token_response(svc: Services, device_id: str, refresh_token: str, app: bool = False) -> JSONResponse:
    """Browser (PWA): refresh token in an HttpOnly cookie. Native app: in the body,
    to be kept in the Android Keystore-backed secure store (cookies would be
    cross-site there and are never sent)."""
    access, exp = svc.tokens.issue_access(device_id, svc.password.version())
    body: dict[str, Any] = {"access_token": access, "token_type": "bearer", "expires_at": exp, "device_id": device_id}
    if app:
        body["refresh_token"] = refresh_token
    resp = JSONResponse(body)
    resp.headers["Cache-Control"] = "no-store"
    if not app:
        _set_refresh_cookie(resp, svc, refresh_token)
    return resp


@dataclass
class AuthContext:
    device_id: str
    ip: str


async def require_device(request: Request) -> AuthContext:
    svc = _svc(request)
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, detail={"code": "unauthorized", "message": "Token mancante"})
    try:
        claims = svc.tokens.verify_access(token.strip(), svc.password.version())
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, detail={"code": "token_expired", "message": "Token scaduto"}) from None
    except jwt.InvalidTokenError:
        audit("token_invalid", logging.WARNING, ip=client_ip(request), path=request.url.path)
        raise HTTPException(401, detail={"code": "unauthorized", "message": "Token non valido"}) from None
    if not svc.store.exists(claims["sub"]):
        raise HTTPException(401, detail={"code": "device_revoked", "message": "Dispositivo revocato"})
    return AuthContext(device_id=claims["sub"], ip=client_ip(request))


def require_perm(svc: Services, ctx: AuthContext, perm: str) -> None:
    device = svc.store.get(ctx.device_id)
    if device is None or not device.can(perm):
        raise HTTPException(403, detail={"code": "no_permission",
                                         "message": "Questo dispositivo non ha il permesso (impostalo nella finestra di PadLink sul PC)"})


# ---- request models -----------------------------------------------------------
class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret: str = Field(min_length=6, max_length=64)
    password: str = Field(default="", max_length=128)
    device_name: str = Field(min_length=1, max_length=64)
    client: Literal["web", "app"] = "web"


class SystemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: str = Field(max_length=16)


class ClipboardSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=100_000)


class WindowActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: str | None = Field(default=None, max_length=16)


# ---- background watcher -----------------------------------------------------------
async def _watch_revocations(svc: Services) -> None:
    """Applies revocations made from the CLI to live WebSocket sessions within ~2 s.

    Every 10 minutes it also revokes devices unused for longer than the
    "inactive_days" preference (0 = never), so a forgotten phone stops working.
    """
    last_purge = 0.0
    pw_mtime = mtime_ns(svc.settings.password_file)
    while True:
        await asyncio.sleep(2)
        try:
            days = svc.prefs.value.inactive_days if svc.prefs else 0
            if days and time.time() - last_purge > 600:
                last_purge = time.time()
                live = set(svc.registry.device_ids())
                for device_id in svc.store.stale(days * 86400):
                    if device_id not in live and svc.store.revoke(device_id):
                        audit("device_revoked", device=device_id, by="inactivity", days=days)
            svc.tokens.maybe_reload()
            current_pw = mtime_ns(svc.settings.password_file)
            if current_pw != pw_mtime:
                # Password set or changed (CLI or PC window): every phone must type the new one.
                pw_mtime = current_pw
                for device_id in svc.registry.device_ids():
                    await svc.registry.close_device(device_id, 4401, "password_changed")
                audit("password_changed_sessions_closed")
            alive = svc.store.ids()
            for device_id in svc.registry.device_ids():
                if device_id not in alive:
                    audit("session_terminated", device=device_id, reason="revoked")
                    await svc.registry.close_device(device_id, 4409, "revoked")
        except Exception:  # noqa: BLE001
            log.exception("Revocation watcher error")


def _run_system_action(action: str, device_id: str) -> None:
    try:
        system.perform(action)
    except Exception as exc:  # noqa: BLE001
        audit("system_action_failed", logging.ERROR, action=action, device=device_id, error=repr(exc))


# ---- application factory ------------------------------------------------------------
def create_app(svc: Services) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        svc.loop = asyncio.get_running_loop()
        task = asyncio.create_task(_watch_revocations(svc))
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="PadLink", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.svc = svc

    @app.middleware("http")
    async def security_middleware(request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        host = request.headers.get("host", "")
        ip = client_ip(request)
        path = request.url.path

        peer = request.client.host if request.client else None
        if not is_lan_peer(peer):
            audit("http_rejected_public_peer", logging.WARNING, ip=peer, path=path)
            return error(403, "lan_only", "PadLink accetta solo connessioni dalla rete locale o da un tunnel")

        if not svc.origin.host_ok(host):
            audit("http_rejected_host", logging.WARNING, ip=ip, host=host, path=path)
            return error(421, "bad_host", "Host non consentito")

        if path.startswith("/api/"):
            if request.method in UNSAFE_METHODS and not svc.origin.origin_ok(request.headers.get("origin")):
                audit("http_rejected_origin", logging.WARNING, ip=ip, origin=request.headers.get("origin"), path=path)
                return error(403, "bad_origin", "Origine non consentita")
            if not svc.api_limiter.allow(ip):
                return error(429, "rate_limited", "Troppe richieste", retry_after=2)

        try:
            response: Response = await call_next(request)
        except Exception:  # noqa: BLE001
            log.exception("Unhandled error on %s %s", request.method, path)
            response = error(500, "internal_error", "Errore interno")

        safe_host = host if _SAFE_HOST.match(host) else "'self'"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            f"connect-src 'self' wss://{safe_host} ws://{safe_host}; "
            "worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if svc.settings.secure_cookies:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            audit("http", method=request.method, path=path, status=response.status_code, ip=ip,
                  ms=round((time.perf_counter() - start) * 1000, 1))
        return response

    # Added after the security middleware so it wraps it and answers preflights.
    # Only the native app / dev server origins get CORS; no credentials (cookies).
    if svc.origin.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=sorted(svc.origin.cors_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
            max_age=600,
        )

    # ---- public endpoints ---------------------------------------------------------
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        # No version here: unauthenticated callers should not learn what to target.
        return {"status": "ok"}

    @app.get("/ca.crt")
    async def ca_certificate() -> Response:
        path = svc.settings.cert_dir / "kursor-ca.crt"
        if not path.exists():
            return error(404, "no_ca", "Nessuna CA locale (TLS disattivato?)")
        return Response(path.read_bytes(), media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": 'attachment; filename="kursor-ca.crt"'})

    # ---- authentication ---------------------------------------------------------------
    @app.post("/api/auth/pair")
    async def pair(body: PairRequest, request: Request) -> Response:
        ip = client_ip(request)
        retry = svc.guard.retry_after(ip)
        if retry:
            audit("pair_blocked", logging.WARNING, ip=ip, retry_after=retry)
            return error(429, "locked_out", "Troppi tentativi falliti. Riprova più tardi.", retry_after=retry)

        if not svc.password.is_set():
            audit("pair_failed", logging.WARNING, ip=ip, reason="password_not_set")
            return error(409, "password_not_set",
                         "Imposta prima una password nella finestra di PadLink sul PC.")
        # No pairing window: answer before checking the password, so /pair is never a password oracle.
        if svc.pairing.active_until() is None:
            await asyncio.sleep(0.4 + secrets.randbelow(400) / 1000)
            audit("pair_failed", logging.WARNING, ip=ip, reason="no_session")
            return error(401, "pairing_closed",
                         "Nessuna associazione attiva. Sul PC apri PadLink e premi «Associa un nuovo telefono».")
        # The password is checked before the PIN: a wrong password does not burn the PIN,
        # but it counts towards the per-IP lockout like a wrong PIN.
        if not await asyncio.to_thread(svc.password.verify, body.password):
            await asyncio.sleep(0.4 + secrets.randbelow(400) / 1000)
            lockout = svc.guard.fail(ip)
            audit("password_failed", logging.WARNING, ip=ip, stage="pair", lockout=lockout or None)
            if lockout:
                return error(429, "locked_out", "Troppi tentativi falliti. Riprova più tardi.", retry_after=lockout)
            return JSONResponse(
                {"detail": {"code": "invalid_password", "message": "Password errata",
                            "remaining_attempts": svc.guard.remaining_attempts(ip)}},
                status_code=401,
            )

        result = svc.pairing.verify(body.secret)
        if result is PairResult.OK:
            svc.guard.success(ip)
            name = body.device_name.strip() or "Dispositivo"
            device_id, refresh = svc.store.create(name, ip, request.headers.get("user-agent", ""))
            audit("pair_success", device=device_id, name=name, ip=ip)
            return _token_response(svc, device_id, refresh, app=body.client == "app")

        # Uniform small random delay on failure slows down automated guessing.
        await asyncio.sleep(0.4 + secrets.randbelow(400) / 1000)
        if result is PairResult.NO_SESSION:
            audit("pair_failed", logging.WARNING, ip=ip, reason="no_session")
            return error(401, "pairing_closed",
                         "Nessuna associazione attiva. Sul PC apri PadLink e premi «Associa un nuovo telefono».")

        lockout = svc.guard.fail(ip)
        if result is PairResult.EXHAUSTED:
            audit("pairing_exhausted", logging.WARNING, ip=ip)
            if lockout:
                return error(429, "locked_out", "Troppi tentativi falliti. Riprova più tardi.", retry_after=lockout)
            return error(401, "pairing_exhausted",
                         "PIN invalidato dopo troppi tentativi. Generane uno nuovo sul PC.")
        audit("pair_failed", logging.WARNING, ip=ip, reason="invalid_code", lockout=lockout or None)
        if lockout:
            return error(429, "locked_out", "Troppi tentativi falliti. Riprova più tardi.", retry_after=lockout)
        return JSONResponse(
            {"detail": {"code": "invalid_code", "message": "Codice non valido",
                        "remaining_attempts": svc.guard.remaining_attempts(ip)}},
            status_code=401,
        )

    @app.post("/api/auth/refresh")
    async def refresh(request: Request) -> Response:
        ip = client_ip(request)
        if not svc.refresh_limiter.allow(ip):
            return error(429, "rate_limited", "Troppe richieste", retry_after=5)
        body_token: str | None = None
        data: Any = None
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                data = await request.json()
            except ValueError:
                data = None
            if isinstance(data, dict) and isinstance(data.get("refresh_token"), str):
                body_token = data["refresh_token"]
        password = data.get("password") if isinstance(data, dict) else None
        app_client = body_token is not None
        token = body_token if app_client else request.cookies.get(REFRESH_COOKIE)
        if not token or len(token) > 256:
            return error(401, "no_session", "Sessione assente", clear_cookie=True, svc=svc)

        # PC password, asked on every app start. Checked before rotating, so a missing or
        # wrong password never spends the refresh token. Invalid tokens fall through to
        # rotate_refresh below, which reports them (and detects reuse) as before.
        pw_device = svc.store.peek_refresh(token)
        if pw_device is not None:
            retry = svc.guard.retry_after(ip)
            if retry:
                return error(429, "locked_out", "Troppi tentativi falliti. Riprova più tardi.", retry_after=retry)
            if not svc.password.is_set():
                return error(401, "password_not_set", "Imposta una password nella finestra di PadLink sul PC.")
            if not isinstance(password, str) or not password:
                return error(401, "password_required", "Inserisci la password del PC")
            if not await asyncio.to_thread(svc.password.verify, password):
                await asyncio.sleep(0.4 + secrets.randbelow(400) / 1000)
                lockout = svc.guard.fail(ip)
                left = svc.store.password_failed(pw_device)
                audit("password_failed", logging.WARNING, ip=ip, stage="refresh", device=pw_device,
                      device_attempts_left=left, lockout=lockout or None)
                if left == 0:
                    audit("device_revoked", logging.WARNING, device=pw_device, by="password_failures", ip=ip)
                    await svc.registry.close_device(pw_device, 4409, "revoked")
                    return error(401, "device_revoked", "Troppe password errate: telefono revocato, ripeti il pairing",
                                 clear_cookie=True, svc=svc)
                if lockout:
                    return error(429, "locked_out", "Troppi tentativi falliti. Riprova più tardi.", retry_after=lockout)
                return JSONResponse(
                    {"detail": {"code": "invalid_password", "message": "Password errata",
                                "remaining_attempts": min(svc.guard.remaining_attempts(ip), left)}},
                    status_code=401,
                )
            svc.guard.success(ip)
        try:
            device_id, new_token = svc.store.rotate_refresh(token, ip)
        except RefreshError as exc:
            reuse = exc.reason == "reuse_detected"
            audit("refresh_failed", logging.WARNING if reuse else logging.INFO, ip=ip, reason=exc.reason,
                  device=exc.device_id)
            if reuse and exc.device_id:
                await svc.registry.close_device(exc.device_id, 4409, "revoked")
            return error(401, exc.reason, "Sessione non valida, ripeti il pairing", clear_cookie=True, svc=svc)
        return _token_response(svc, device_id, new_token, app=app_client)

    @app.post("/api/auth/logout")
    async def logout(ctx: AuthContext = Depends(require_device)) -> Response:
        svc.store.revoke(ctx.device_id)
        await svc.registry.close_device(ctx.device_id, 4409, "logout")
        audit("logout", device=ctx.device_id, ip=ctx.ip)
        resp = JSONResponse({"ok": True})
        _clear_refresh_cookie(resp, svc)
        return resp

    # ---- devices ----------------------------------------------------------------------
    @app.get("/api/devices")
    async def devices(ctx: AuthContext = Depends(require_device)) -> dict[str, Any]:
        return {
            "current": ctx.device_id,
            "devices": [d.public() | {"current": d.id == ctx.device_id} for d in svc.store.list()],
        }

    @app.delete("/api/devices/{device_id}")
    async def revoke_device(device_id: str, ctx: AuthContext = Depends(require_device)) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{16}", device_id) or not svc.store.revoke(device_id):
            raise HTTPException(404, detail={"code": "not_found", "message": "Dispositivo non trovato"})
        await svc.registry.close_device(device_id, 4409, "revoked")
        audit("device_revoked", device=device_id, by=ctx.device_id, ip=ctx.ip)
        return {"ok": True}

    # ---- screen & system ------------------------------------------------------------------
    @app.get("/api/screen/monitors")
    async def monitors(ctx: AuthContext = Depends(require_device)) -> dict[str, Any]:
        require_perm(svc, ctx, "screen")
        return {"monitors": svc.monitors()}

    # ---- open applications (windows) -------------------------------------------------
    @app.get("/api/windows")
    async def list_open_windows(ctx: AuthContext = Depends(require_device)) -> Any:
        require_perm(svc, ctx, "apps")
        if svc.paused:
            return error(423, "paused", "Controllo in pausa sul PC")
        if not svc.api_limiter.allow(ctx.device_id):
            return error(429, "rate_limited", "Troppe richieste", retry_after=2)
        return {"windows": await asyncio.to_thread(windows.list_windows)}

    @app.post("/api/windows/{window_id}/{action}")
    async def act_on_window(window_id: int, action: str, body: WindowActionRequest,
                            ctx: AuthContext = Depends(require_device)) -> Any:
        if action not in windows.ACTIONS:
            raise HTTPException(404, detail={"code": "unknown_action", "message": "Azione sconosciuta"})
        if svc.paused:
            return error(423, "paused", "Controllo in pausa sul PC")
        require_perm(svc, ctx, "apps")
        destructive = action in ("close", "kill")
        if action == "kill":
            require_perm(svc, ctx, "power")
        if destructive and body.confirm != action:
            raise HTTPException(400, detail={"code": "confirmation_required", "message": "Conferma mancante"})
        limiter = svc.system_limiter if action == "kill" else svc.api_limiter
        if not limiter.allow(ctx.device_id):
            return error(429, "rate_limited", "Attendi qualche secondo", retry_after=3)
        try:
            info = await asyncio.to_thread(windows.window_action, window_id, action)
        except windows.WindowError as exc:
            status = {"not_found": 404, "protected": 403, "access_denied": 403, "unsupported": 501}.get(exc.code, 400)
            return error(status, exc.code, exc.message)
        # Audit the application, never the window title (it may contain private data).
        audit("window_action", logging.WARNING if destructive else logging.INFO, action=action, app=info["exe"],
              device=ctx.device_id, ip=ctx.ip)
        if destructive:
            verb = "ha chiuso" if action == "close" else "ha terminato"
            svc.notify(f"{svc.device_name(ctx.device_id)} {verb} {info['app']}")
        return {"ok": True}

    @app.post("/api/system/{action}")
    async def system_action(action: str, body: SystemRequest, ctx: AuthContext = Depends(require_device)) -> Any:
        if action not in system.ACTIONS:
            raise HTTPException(404, detail={"code": "unknown_action", "message": "Azione sconosciuta"})
        if body.confirm != action:
            raise HTTPException(400, detail={"code": "confirmation_required", "message": "Conferma mancante"})
        require_perm(svc, ctx, "power")
        if svc.paused:
            return error(423, "paused", "Controllo in pausa sul PC")
        if not svc.system_limiter.allow(ctx.device_id):
            return error(429, "rate_limited", "Attendi qualche secondo", retry_after=5)
        audit("system_action", logging.WARNING, action=action, device=ctx.device_id, ip=ctx.ip)
        label = {"lock": "ha bloccato", "sleep": "sta sospendendo", "shutdown": "sta spegnendo"}[action]
        svc.notify(f"{svc.device_name(ctx.device_id)} {label} il PC")
        if action == "lock":
            try:
                await asyncio.to_thread(system.perform, action)
            except Exception as exc:  # noqa: BLE001
                audit("system_action_failed", logging.ERROR, action=action, device=ctx.device_id, error=repr(exc))
                return error(500, "action_failed", "Azione non riuscita")
        else:
            # Delay so the HTTP response reaches the phone before the PC goes down.
            loop = asyncio.get_running_loop()
            loop.call_later(1.0, lambda: loop.run_in_executor(None, _run_system_action, action, ctx.device_id))
        return {"ok": True, "action": action}

    # ---- clipboard (text only, on explicit request) ----------------------------------
    @app.post("/api/clipboard/get")
    async def clipboard_get(ctx: AuthContext = Depends(require_device)) -> Any:
        require_perm(svc, ctx, "clipboard")
        if svc.paused:
            return error(423, "paused", "Controllo in pausa sul PC")
        if not svc.api_limiter.allow(ctx.device_id):
            return error(429, "rate_limited", "Troppe richieste", retry_after=2)
        try:
            text = await asyncio.to_thread(clipboard.get_text)
        except clipboard.ClipboardError as exc:
            return error(409, "clipboard_busy", str(exc))
        audit("clipboard_read", logging.INFO, device=ctx.device_id, ip=ctx.ip, chars=len(text))  # never the content
        svc.notify(f"{svc.device_name(ctx.device_id)} ha copiato gli appunti del PC")
        return {"text": text}

    @app.post("/api/clipboard/set")
    async def clipboard_set(body: ClipboardSetRequest, ctx: AuthContext = Depends(require_device)) -> Any:
        require_perm(svc, ctx, "clipboard")
        if svc.paused:
            return error(423, "paused", "Controllo in pausa sul PC")
        if not svc.api_limiter.allow(ctx.device_id):
            return error(429, "rate_limited", "Troppe richieste", retry_after=2)
        try:
            await asyncio.to_thread(clipboard.set_text, body.text)
        except clipboard.ClipboardError as exc:
            return error(409, "clipboard_busy", str(exc))
        audit("clipboard_write", logging.INFO, device=ctx.device_id, ip=ctx.ip, chars=len(body.text))
        return {"ok": True}

    @app.get("/api/pc")
    async def pc_info(ctx: AuthContext = Depends(require_device)) -> dict[str, Any]:
        device = svc.store.get(ctx.device_id)
        return {"name": svc.pc_name, "mac": svc.pc_mac, "version": __version__,
                "perms": device.perms if device else {}}

    # ---- websockets ------------------------------------------------------------------
    app.add_api_websocket_route("/ws/control", control_endpoint)
    app.add_api_websocket_route("/ws/screen", screen_endpoint)

    # ---- PWA static hosting --------------------------------------------------------------
    static_dir: Path = svc.settings.static_dir.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        if full_path.startswith(("api/", "ws/")):
            raise HTTPException(404, detail={"code": "not_found", "message": "Not found"})
        index = static_dir / "index.html"
        if not index.exists():
            return Response(
                "Client non compilato. Esegui: cd client && npm install && npm run build",
                media_type="text/plain; charset=utf-8",
                status_code=503,
            )
        candidate = (static_dir / full_path).resolve() if full_path else index
        if not candidate.is_relative_to(static_dir) or not candidate.is_file():
            candidate = index
        headers = {}
        if candidate.name in ("index.html", "sw.js", "manifest.webmanifest"):
            headers["Cache-Control"] = "no-cache"
        elif "assets" in candidate.relative_to(static_dir).parts:
            headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return FileResponse(candidate, headers=headers)

    return app
