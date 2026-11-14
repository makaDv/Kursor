/**
 * Authenticated, self-healing WebSocket.
 *
 * The access token is sent as the first message (never in the URL). Before it
 * expires a fresh token is pushed over the open socket, so the connection
 * survives token rotation without reconnecting.
 */
import { forgetSession, getAccessToken, refresh } from './api'

export type SocketStatus = 'idle' | 'connecting' | 'open' | 'offline' | 'revoked'

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
  private ws: WebSocket | null = null
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
    if (this.status !== 'open' || !this.ws || this.ws.readyState !== WebSocket.OPEN) return false
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

  private scheduleRetry() {
    if (this.stopped) return
    this.setStatus('offline')
    window.clearTimeout(this.retryTimer)
    this.retryTimer = window.setTimeout(() => void this.connect(), this.backoff)
    this.backoff = Math.min(MAX_BACKOFF, this.backoff * 2)
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
    } catch {
      this.scheduleRetry()
      return
    }
    if (!token) {
      this.setStatus('revoked')
      return
    }
    if (this.stopped) return

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}${this.opts.path}`)
    ws.binaryType = 'arraybuffer'
    this.ws = ws

    ws.onopen = () => ws.send(JSON.stringify({ t: 'auth', token }))

    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') {
        this.opts.onBinary?.(ev.data as ArrayBuffer)
        return
      }
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(ev.data)
      } catch {
        return
      }
      if (msg.t === 'ready') {
        this.backoff = 500
        if (Array.isArray(msg.monitors)) this.monitors = msg.monitors as Monitor[]
        this.setStatus('open')
        this.scheduleReauth(Number(msg.exp))
        this.pingTimer = window.setInterval(() => this.send({ t: 'ping', ts: Date.now() }), 15_000)
      } else if (msg.t === 'reauth_ok') {
        this.scheduleReauth(Number(msg.exp))
      }
      this.opts.onMessage?.(msg)
    }

    ws.onclose = async (ev) => {
      if (this.ws !== ws) return
      this.ws = null
      this.clearTimers()
      if (this.stopped) return
      if (ev.code === 4409) {
        forgetSession()
        this.setStatus('revoked')
        return
      }
      if (ev.code === 4401 || ev.code === 4408) {
        try {
          const ok = await refresh()
          if (!ok) {
            this.setStatus('revoked')
            return
          }
        } catch {
          /* offline: retry below */
        }
      }
      this.scheduleRetry()
    }
  }
}
