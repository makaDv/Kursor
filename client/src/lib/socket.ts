/**
 * Authenticated, self-healing WebSocket.
 *
 * The access token is sent as the first message (never in the URL). Before it
 * expires a fresh token is pushed over the open socket, so the connection
 * survives token rotation without reconnecting.
 */
import { forgetSession, getAccessToken, isPasswordError, refresh } from './api'
import { wsUrl } from './platform'
import { openSocket, type SocketLike } from './transport'
import { maybeRediscover } from './pc'

export type SocketStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'offline'
  | 'paused'
  | 'approval' // waiting for "Allow" on the PC
  | 'denied' // the PC user refused this connection
  | 'forbidden' // this device lacks the permission (e.g. screen)
  | 'revoked'
  | 'untrusted'

export interface Monitor {
  index: number
  left: number
  top: number
  width: number
  height: number
}

interface Options {
  path: string
  onStatus?: (s: SocketStatus) => void
  onMessage?: (msg: Record<string, unknown>) => void
  onBinary?: (data: ArrayBuffer) => void
}

const MAX_BACKOFF = 10_000

export class KursorSocket {
  private ws: SocketLike | null = null
  private opts: Options
  private status: SocketStatus = 'idle'
  private stopped = false
  private backoff = 500
  private retryTimer: number | undefined
  private reauthTimer: number | undefined
  private pingTimer: number | undefined
  monitors: Monitor[] = []

  constructor(opts: Options) {
    this.opts = opts
  }

  get isOpen() {
    return this.status === 'open'
  }

  private setStatus(s: SocketStatus) {
    this.status = s
    this.opts.onStatus?.(s)
  }

  start() {
    this.stopped = false
    void this.connect()
  }

  stop() {
    this.stopped = true
    this.clearTimers()
    this.ws?.close(1000)
    this.ws = null
    this.setStatus('idle')
  }

  send(msg: Record<string, unknown>): boolean {
    if (this.status !== 'open' || !this.ws || !this.ws.isOpen) return false
    // Drop input instead of queueing when the link is congested: stale mouse
    // moves are worse than missing ones.
    if (this.ws.bufferedAmount > 256 * 1024) return false
    this.ws.send(JSON.stringify(msg))
    return true
  }

  private clearTimers() {
    window.clearTimeout(this.retryTimer)
    window.clearTimeout(this.reauthTimer)
    window.clearInterval(this.pingTimer)
  }

  private failures = 0

  private scheduleRetry(status: SocketStatus = 'offline') {
    if (this.stopped) return
    this.setStatus(status)
    window.clearTimeout(this.retryTimer)
    this.retryTimer = window.setTimeout(() => void this.connect(), this.backoff)
    this.backoff = Math.min(MAX_BACKOFF, this.backoff * 2)
    // PC unreachable for a while: maybe its IP changed (DHCP). Look for it on the LAN.
    if (status === 'offline' && ++this.failures % 3 === 0) {
      void maybeRediscover().then((moved) => {
        if (moved && !this.stopped) {
          window.clearTimeout(this.retryTimer)
          this.backoff = 500
          void this.connect()
        }
      })
    }
  }

  private scheduleReauth(exp: number) {
    window.clearTimeout(this.reauthTimer)
    const ms = Math.max(5_000, (exp - Date.now() / 1000 - 90) * 1000)
    this.reauthTimer = window.setTimeout(async () => {
      try {
        await refresh()
        const token = await getAccessToken()
        if (token) this.send({ t: 'auth', token })
      } catch {
        /* network error: the socket will drop and reconnect */
      }
    }, ms)
  }

  private async connect() {
    if (this.stopped) return
    this.clearTimers()
    this.setStatus('connecting')
    let token: string | null
    try {
      token = await getAccessToken()
    } catch (err) {
      // PC password needed: the app shows the unlock screen and restarts the socket after.
      if (isPasswordError(err)) return this.setStatus('idle')
      this.scheduleRetry()
      return
    }
    if (!token) {
      this.setStatus('revoked')
      return
    }
    if (this.stopped) return

    const ws = openSocket(wsUrl(this.opts.path))
    this.ws = ws

    ws.onopen = () => ws.send(JSON.stringify({ t: 'auth', token }))

    ws.onmessage = (data) => {
      if (typeof data !== 'string') {
        this.opts.onBinary?.(data)
        return
      }
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(data)
      } catch {
        return
      }
      if (msg.t === 'ready') {
        this.backoff = 500
        if (Array.isArray(msg.monitors)) this.monitors = msg.monitors as Monitor[]
        this.failures = 0
        this.setStatus('open')
        this.scheduleReauth(Number(msg.exp))
        this.pingTimer = window.setInterval(() => this.send({ t: 'ping', ts: Date.now() }), 15_000)
      } else if (msg.t === 'approval_pending') {
        this.setStatus('approval')
      } else if (msg.t === 'reauth_ok') {
        this.scheduleReauth(Number(msg.exp))
      }
      this.opts.onMessage?.(msg)
    }

    ws.onclose = async (code, reason) => {
      if (this.ws !== ws) return
      this.ws = null
      this.clearTimers()
      if (this.stopped) return
      if (reason === 'pin_mismatch') {
        this.setStatus('untrusted')
        return
      }
      if (code === 4409) {
        forgetSession()
        this.setStatus('revoked')
        return
      }
      if (reason === 'denied') {
        // Refused on the PC: try again only much later (the user can retry manually).
        this.backoff = MAX_BACKOFF * 3
        this.scheduleRetry('denied')
        this.backoff = MAX_BACKOFF
        return
      }
      if (reason === 'no_permission') {
        this.setStatus('forbidden')
        return
      }
      if (code === 4423) {
        // Paused from the PC window: keep retrying slowly until it is resumed.
        this.backoff = MAX_BACKOFF
        this.scheduleRetry('paused')
        return
      }
      if (code === 4401 || code === 4408) {
        try {
          const ok = await refresh()
          if (!ok) {
            this.setStatus('revoked')
            return
          }
        } catch (err) {
          if (isPasswordError(err)) return this.setStatus('idle')
          /* offline: retry below */
        }
      }
      this.scheduleRetry()
    }
  }
}
