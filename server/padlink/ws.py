"""WebSocket endpoints: low-latency input control and adaptive screen streaming.

Protocol (both channels):
  1. Server checks Host + Origin *before* accepting the upgrade.
  2. Client must send ``{"t": "auth", "token": "<access JWT>"}`` within 5 s.
     Tokens never travel in the URL, so they never end up in logs or history.
  3. Server replies ``{"t": "ready"}``. Before the access token expires the
     client sends a fresh ``auth`` message, otherwise the socket is closed (4401).

Close codes: 4400 bad request, 4401 unauthorized/expired, 4403 forbidden
origin, 4408 auth timeout, 4409 device revoked, 4423 paused on the PC, 4429 locked out.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import WebSocket, WebSocketDisconnect

from .control.screen import FrameGrabber, StreamParams
from .logging_setup import audit
from .netutil import is_lan_peer, resolve_client_ip, tailscale_ipv4
from .security.ratelimit import LocalBucket
from .services import Services

log = logging.getLogger(__name__)

AUTH_TIMEOUT = 5.0


@dataclass
class WsSession:
    device_id: str
    exp: float
    ip: str


def _svc(ws: WebSocket) -> Services:
    return ws.app.state.svc


async def _send(ws: WebSocket, payload: dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(payload))
    except Exception:  # noqa: BLE001
        pass


def _parse(text: str) -> dict[str, Any] | None:
    try:
        msg = json.loads(text)
    except (ValueError, TypeError):
        return None
    return msg if isinstance(msg, dict) else None


def _verify(svc: Services, token: Any) -> tuple[str, float] | str:
    if not isinstance(token, str) or len(token) > 4096:
        return "bad_token"
    try:
        claims = svc.tokens.verify_access(token, svc.password.version())
    except jwt.ExpiredSignatureError:
        return "token_expired"
    except jwt.InvalidTokenError:
        return "invalid_token"
    if not svc.store.exists(claims["sub"]):
        return "device_revoked"
    return claims["sub"], float(claims["exp"])


async def authenticate(ws: WebSocket, channel: str) -> WsSession | None:
    svc = _svc(ws)
    ip = resolve_client_ip(ws.client.host if ws.client else None, ws.headers, svc.settings.trust_proxy)
    origin = ws.headers.get("origin")

    if not is_lan_peer(ws.client.host if ws.client else None):
        audit("ws_rejected_public_peer", logging.WARNING, ip=ip, channel=channel)
        await ws.close(code=4403)
        return None
    if not svc.origin.host_ok(ws.headers.get("host")) or not svc.origin.origin_ok(origin):
        audit("ws_rejected_origin", logging.WARNING, ip=ip, origin=origin, host=ws.headers.get("host"), channel=channel)
        await ws.close(code=4403)
        return None
    if svc.guard.retry_after(ip):
        await ws.close(code=4429)
        return None
    await ws.accept()
    if svc.paused:
        # Accept first so the client receives the 4423 code and can show "paused".
        await ws.close(code=4423, reason="paused")
        return None
    try:
        text = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_TIMEOUT)
    except asyncio.TimeoutError:
        await ws.close(code=4408, reason="auth_timeout")
        return None
    except (WebSocketDisconnect, KeyError, RuntimeError):
        return None

    msg = _parse(text)
    if not msg or msg.get("t") != "auth":
        await ws.close(code=4400, reason="auth_required")
        return None

    result = _verify(svc, msg.get("token"))
    if isinstance(result, str):
        level = logging.INFO if result == "token_expired" else logging.WARNING
        audit("ws_auth_failed", level, ip=ip, reason=result, channel=channel)
        await ws.close(code=4409 if result == "device_revoked" else 4401, reason=result)
        return None

    device_id, exp = result
    device = svc.store.get(device_id)
    if device is None:
        await ws.close(code=4409, reason="device_revoked")
        return None
    if channel == "screen" and not device.can("screen"):
        await ws.close(code=4403, reason="no_permission")
        return None

    # Optional "ask on the PC" mode: the PC user allows each device once per session.
    if device_id not in svc.approved and svc.prefs and svc.prefs.value.require_approval and svc.approver_available:
        await _send(ws, {"t": "approval_pending"})
        if not await svc.request_approval(device_id):
            audit("ws_denied_on_pc", logging.WARNING, device=device_id, ip=ip, channel=channel)
            await ws.close(code=4403, reason="denied")
            return None

    svc.registry.add(device_id, ws)
    svc.store.touch(device_id, ip)
    audit("ws_connect", device=device_id, ip=ip, channel=channel)
    await _send(ws, {"t": "ready", "exp": exp, "monitors": svc.monitors(), "perms": device.perms,
                     "pc": {"name": svc.pc_name, "mac": svc.pc_mac, "ts": tailscale_ipv4(svc.lan_ips)}})
    return WsSession(device_id, exp, ip)


async def _handle_reauth(ws: WebSocket, svc: Services, session: WsSession, msg: dict[str, Any]) -> bool:
    result = _verify(svc, msg.get("token"))
    if isinstance(result, str) or result[0] != session.device_id:
        await ws.close(code=4401, reason="reauth_failed")
        return False
    session.exp = result[1]
    await _send(ws, {"t": "reauth_ok", "exp": session.exp})
    return True


async def _dispatch_input(svc: Services, msg: dict[str, Any]) -> None:
    if svc.paused:
        return
    inp = svc.input
    t = msg.get("t")
    if t == "move":
        inp.move_relative(msg.get("dx", 0), msg.get("dy", 0))
    elif t == "abs":
        mon = msg.get("m", 1)
        inp.move_absolute(msg.get("x"), msg.get("y"), svc.monitor_rect(mon if isinstance(mon, int) else 1))
    elif t == "click":
        inp.click(msg.get("b", "left"), msg.get("n", 1))
    elif t == "down":
        inp.button(msg.get("b", "left"), True)
    elif t == "up":
        inp.button(msg.get("b", "left"), False)
    elif t == "scroll":
        inp.scroll(msg.get("dx", 0), msg.get("dy", 0))
    elif t == "text":
        await asyncio.to_thread(inp.type_text, msg.get("s"))
    elif t == "keys":
        await asyncio.to_thread(inp.key_combo, msg.get("k"))
    else:
        raise ValueError("unknown command")


async def control_endpoint(ws: WebSocket) -> None:
    session = await authenticate(ws, "control")
    if session is None:
        return
    svc = _svc(ws)
    bucket = LocalBucket(rate=400, capacity=800)
    try:
        while True:
            text = await ws.receive_text()
            if time.time() > session.exp:
                await ws.close(code=4401, reason="token_expired")
                break
            msg = _parse(text)
            if msg is None:
                continue
            t = msg.get("t")
            if t == "auth":
                if not await _handle_reauth(ws, svc, session, msg):
                    break
                continue
            if t == "ping":
                await _send(ws, {"t": "pong", "ts": msg.get("ts")})
                continue
            if not bucket.allow():
                continue
            try:
                await _dispatch_input(svc, msg)
            except ValueError as exc:
                await _send(ws, {"t": "error", "message": str(exc)[:100]})
            except Exception:  # noqa: BLE001
                log.exception("Input command failed")
                await _send(ws, {"t": "error", "message": "input_failed"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        svc.registry.remove(session.device_id, ws)
        svc.input.release_all()
        audit("ws_disconnect", device=session.device_id, ip=session.ip, channel="control")


async def screen_endpoint(ws: WebSocket) -> None:
    session = await authenticate(ws, "screen")
    if session is None:
        return
    svc = _svc(ws)
    loop = asyncio.get_running_loop()
    grabber = FrameGrabber()
    params = StreamParams()
    state = {"running": False, "seq": 0, "acked": 0, "quality": params.quality, "scale": 1.0}
    wake = asyncio.Event()
    ack_event = asyncio.Event()

    async def receiver() -> None:
        while True:
            msg = _parse(await ws.receive_text())
            if msg is None:
                continue
            t = msg.get("t")
            if t == "auth":
                if not await _handle_reauth(ws, svc, session, msg):
                    return
            elif t == "start":
                if not state["running"]:
                    svc.screen_viewers[session.device_id] += 1
                params.update(msg.get("params") or {})
                state.update(running=True, quality=params.quality, scale=1.0, acked=state["seq"])
                grabber.reset()
                wake.set()
                audit("stream_start", device=session.device_id, fps=params.fps, quality=params.quality)
            elif t == "stop":
                if state["running"]:
                    svc.screen_viewers[session.device_id] -= 1
                state["running"] = False
            elif t == "config":
                params.update(msg.get("params") or {})
                state.update(quality=params.quality, scale=1.0)
                grabber.reset()
            elif t == "ack":
                seq = msg.get("seq")
                if isinstance(seq, int) and state["acked"] < seq <= state["seq"]:
                    state["acked"] = seq
                    ack_event.set()
            elif t == "ping":
                await _send(ws, {"t": "pong", "ts": msg.get("ts")})

    async def sender() -> None:
        last_sent = 0.0
        good_streak = 0
        while True:
            if not state["running"]:
                wake.clear()
                await wake.wait()
                continue
            if time.time() > session.exp:
                await ws.close(code=4401, reason="token_expired")
                return
            started = loop.time()

            # Backpressure: never more than 2 frames in flight. Waiting for acks is
            # the bandwidth signal that drives adaptive quality.
            if state["seq"] - state["acked"] >= 2:
                ack_event.clear()
                try:
                    await asyncio.wait_for(ack_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    good_streak = 0
                    if params.auto:
                        state["quality"] = max(20, state["quality"] - 10)
                        state["scale"] = max(0.4, round(state["scale"] - 0.15, 2))
                    if loop.time() - last_sent > 3:
                        state["acked"] = state["seq"]  # frames lost, resync
                continue

            force = loop.time() - last_sent > 2.0
            quality = state["quality"] if params.auto else params.quality
            scale = state["scale"] if params.auto else 1.0
            frame = await loop.run_in_executor(
                grabber.executor, grabber.grab, state["seq"] + 1, params, quality, scale, force
            )
            if frame is not None:
                state["seq"] += 1
                await ws.send_bytes(frame)
                last_sent = loop.time()

            if params.auto:
                good_streak += 1
                if good_streak >= params.fps * 3:
                    good_streak = 0
                    state["quality"] = min(params.quality, state["quality"] + 5)
                    state["scale"] = min(1.0, round(state["scale"] + 0.1, 2))

            await asyncio.sleep(max(0.0, 1.0 / params.fps - (loop.time() - started)))

    tasks = [asyncio.create_task(receiver()), asyncio.create_task(sender())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, (WebSocketDisconnect, RuntimeError)):
                log.error("Screen stream error: %r", exc)
    finally:
        for task in tasks:
            task.cancel()
        svc.registry.remove(session.device_id, ws)
        if state["running"]:
            svc.screen_viewers[session.device_id] -= 1
        if svc.screen_viewers.get(session.device_id, 0) <= 0:
            svc.screen_viewers.pop(session.device_id, None)
        grabber.close()
        audit("ws_disconnect", device=session.device_id, ip=session.ip, channel="screen")
