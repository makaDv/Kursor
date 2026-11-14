/**
 * HTTP + WebSocket transport.
 *
 * PWA: plain fetch/WebSocket (same origin, browser-validated TLS).
 * Store apps: everything goes through the KursorNative plugin, which pins the
 * PC's CA certificate. The WebView itself never talks to the network.
 */
import { KursorNative, type NativeWsEvent } from './native'
import { getServer, isNative } from './platform'

export interface HttpResponse {
  status: number
  ok: boolean
  json(): unknown
}

export class TransportError extends Error {
  /** network | tls | pin_mismatch */
  code: string
  constructor(code: string) {
    super(code)
    this.code = code
  }
}

function nativeCode(err: unknown): string {
  const code = (err as { code?: unknown } | null)?.code
  return code === 'pin_mismatch' || code === 'tls' ? code : 'network'
}

export async function httpRequest(
  url: string,
  init: { method?: string; headers?: Record<string, string>; body?: string; sameOrigin?: boolean } = {},
): Promise<HttpResponse> {
  const method = init.method ?? 'GET'
  if (!isNative) {
    let res: Response
    try {
      res = await fetch(url, {
        method,
        headers: init.headers,
        body: init.body,
        credentials: 'same-origin',
        cache: 'no-store',
      })
    } catch {
      throw new TransportError('network')
    }
    let parsed: unknown = null
    try {
      parsed = await res.json()
    } catch {
      parsed = null
    }
    return { status: res.status, ok: res.ok, json: () => parsed }
  }

  try {
    const r = await KursorNative.request({
      url,
      method,
      headers: init.headers,
      body: init.body,
      pin: getServer()?.pin ?? undefined,
    })
    let parsed: unknown = null
    try {
      parsed = r.body ? JSON.parse(r.body) : null
    } catch {
      parsed = null
    }
    return { status: r.status, ok: r.status >= 200 && r.status < 300, json: () => parsed }
  } catch (err) {
    throw new TransportError(nativeCode(err))
  }
}

// ---- WebSocket --------------------------------------------------------------------------
export interface SocketLike {
  readonly bufferedAmount: number
  readonly isOpen: boolean
  onopen: (() => void) | null
  onmessage: ((data: string | ArrayBuffer) => void) | null
  onclose: ((code: number, reason: string) => void) | null
  send(text: string): void
  close(code?: number): void
}

class BrowserSocket implements SocketLike {
  private ws: WebSocket
  onopen: (() => void) | null = null
  onmessage: ((data: string | ArrayBuffer) => void) | null = null
  onclose: ((code: number, reason: string) => void) | null = null

  constructor(url: string) {
    this.ws = new WebSocket(url)
    this.ws.binaryType = 'arraybuffer'
    this.ws.onopen = () => this.onopen?.()
    this.ws.onmessage = (ev) => this.onmessage?.(ev.data as string | ArrayBuffer)
    this.ws.onclose = (ev) => this.onclose?.(ev.code, ev.reason)
  }

  get bufferedAmount() {
    return this.ws.bufferedAmount
  }

  get isOpen() {
    return this.ws.readyState === WebSocket.OPEN
  }

  send(text: string) {
    this.ws.send(text)
  }

  close(code = 1000) {
    this.ws.close(code)
  }
}

// One global listener dispatches native events to sockets by id. Events that
// arrive before wsOpen() resolves (e.g. "open") are parked until registration.
const handlers = new Map<string, (ev: NativeWsEvent) => void>()
const parked = new Map<string, NativeWsEvent[]>()
let listening: Promise<unknown> | null = null

function ensureListener() {
  if (!listening) {
    listening = KursorNative.addListener('ws', (ev) => {
      const h = handlers.get(ev.id)
      if (h) h(ev)
      else {
        const q = parked.get(ev.id) ?? []
        q.push(ev)
        parked.set(ev.id, q)
        if (parked.size > 32) parked.delete(parked.keys().next().value as string)
      }
    })
  }
  return listening
}

function base64ToBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out.buffer
}

class NativeSocket implements SocketLike {
  private id: string | null = null
  private open = false
  private done = false
  private inflight = 0
  private queued = 0
  onopen: (() => void) | null = null
  onmessage: ((data: string | ArrayBuffer) => void) | null = null
  onclose: ((code: number, reason: string) => void) | null = null

  constructor(url: string) {
    void this.start(url)
  }

  private async start(url: string) {
    try {
      await ensureListener()
      const { id } = await KursorNative.wsOpen({ url, pin: getServer()?.pin ?? undefined })
      this.id = id
      if (this.done) {
        void KursorNative.wsClose({ id })
        return
      }
      handlers.set(id, (ev) => this.handle(ev))
      const early = parked.get(id) ?? []
      parked.delete(id)
      early.forEach((ev) => this.handle(ev))
    } catch (err) {
      this.finish(1006, nativeCode(err))
    }
  }

  private handle(ev: NativeWsEvent) {
    switch (ev.type) {
      case 'open':
        this.open = true
        this.onopen?.()
        break
      case 'text':
        this.onmessage?.(ev.data)
        break
      case 'binary':
        this.onmessage?.(base64ToBuffer(ev.data))
        break
      case 'close':
        this.finish(ev.code, ev.reason ?? '')
        break
    }
  }

  private reported = false

  /** Reports the close exactly once, like a browser WebSocket. */
  private finish(code: number, reason: string) {
    this.done = true
    this.open = false
    if (this.id) handlers.delete(this.id)
    if (this.reported) return
    this.reported = true
    this.onclose?.(code, reason)
  }

  get bufferedAmount() {
    return this.inflight + this.queued
  }

  get isOpen() {
    return this.open
  }

  send(text: string) {
    if (!this.open || !this.id) return
    this.inflight += text.length
    void KursorNative.wsSend({ id: this.id, data: text })
      .then((r) => {
        this.queued = r.buffered
      })
      .catch(() => undefined)
      .finally(() => {
        this.inflight -= text.length
      })
  }

  close(code = 1000) {
    if (this.done) return
    this.done = true
    this.open = false
    // The native "close" event (still routed to this socket) reports it via finish().
    if (this.id) void KursorNative.wsClose({ id: this.id, code })
  }
}

export function openSocket(url: string): SocketLike {
  return isNative ? new NativeSocket(url) : new BrowserSocket(url)
}
