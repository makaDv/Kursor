/**
 * Runtime differences between the PWA (served by the PC itself, same origin)
 * and the store apps (assets bundled in the app, PC reached through the native
 * PadLinkNative plugin with certificate pinning).
 */
import { Capacitor } from '@capacitor/core'
import { PadLinkNative } from './native'

export const isNative = Capacitor.isNativePlatform()

// ---- PC address + certificate pin (native only) ---------------------------------
//
// `pin` is the base64url SHA-256 of the PC's local CA certificate. It arrives in
// the pairing QR code (`#pair=CODE&fp=PIN`) or is confirmed by the user through
// the verification code. Not secret, but it must not be changed by anyone but the
// user, so it lives in the Keystore/Keychain together with the refresh token.
export interface ServerConfig {
  origin: string
  pin: string | null
  /** Stable id (derived from the pin, else the origin): keys the refresh token of this PC. */
  id?: string
  /** PC name and MAC (Wake-on-LAN), reported by the PC after connecting. */
  name?: string
  mac?: string | null
  /** Second address of the same PC (Tailscale 100.x), tried when `origin` is unreachable. */
  alt?: string | null
}

// Several PCs (home, office) can be paired; one is "current". Everything lives in the
// Keystore/Keychain. Legacy single-PC keys ("server", "refresh_token") are migrated.
const SERVERS_KEY = 'servers'
const LEGACY_SERVER_KEY = 'server'
const LEGACY_REFRESH_KEY = 'refresh_token'
let servers: ServerConfig[] = []
let currentId: string | null = null
let server: ServerConfig | null = null

/**
 * App Store Review Guideline 4.2.7 (remote desktop clients): host and client must
 * be on the same local network. The iOS app therefore only accepts LAN addresses;
 * Android and the PWA may also use a tunnel (see README).
 */
export const LAN_ONLY = Capacitor.getPlatform() === 'ios'

export function isLanHost(hostname: string): boolean {
  const h = hostname.toLowerCase()
  if (h === 'localhost' || h.endsWith('.local')) return true
  const m = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/)
  if (!m) return false
  const [a, b] = [Number(m[1]), Number(m[2])]
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
}

/** Normalises "192.168.1.10", "192.168.1.10:8443" or a full URL to an https origin. */
export function normalizeServer(input: string): string | null {
  let s = input.trim()
  if (!s) return null
  if (!/^https?:\/\//i.test(s)) s = `https://${s}`
  try {
    const u = new URL(s)
    if (u.protocol !== 'https:') return null // the app never talks plain HTTP
    if (LAN_ONLY && !isLanHost(u.hostname)) return null
    if (!u.port && /^\d{1,3}(\.\d{1,3}){3}$/.test(u.hostname)) u.port = '8443'
    return u.origin
  } catch {
    return null
  }
}

export const PIN_RE = /^[A-Za-z0-9_-]{43}$/

/** Parses the pairing QR / link: https://IP:8443/#pair=CODE&fp=PIN[&ts=TAILSCALE_IP] */
export function parsePairingLink(text: string): { origin: string; code: string; pin: string | null; alt: string | null } | null {
  const m = text.trim().match(/^(https:\/\/[^/#\s]+)\/?#(.+)$/)
  if (!m) return null
  const params = new URLSearchParams(m[2])
  const code = params.get('pair')
  const origin = normalizeServer(m[1])
  if (!origin || !code || !/^[A-Za-z0-9_-]{6,64}$/.test(code)) return null
  const fp = params.get('fp')
  const pin = fp && PIN_RE.test(fp) ? fp : null
  // The Tailscale address is only trusted together with the pinned CA (same certificate).
  const alt = pin ? tailscaleOrigin(params.get('ts'), origin) : null
  return { origin, code, pin, alt }
}

/** https origin for a Tailscale IP (100.64.0.0/10) on the same port as `like`, else null. */
export function tailscaleOrigin(ip: string | null | undefined, like: string): string | null {
  if (!ip || !/^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}$/.test(ip)) return null
  const port = new URL(like).port || '8443'
  return normalizeServer(`${ip}:${port}`)
}

/** Short human-comparable form of a pin, also shown by the PC ("Codice di verifica"). */
export function verificationCode(pin: string): string {
  // First 48 bits of the SHA-256 as 12 hex digits: XXXX-XXXX-XXXX.
  const bin = atob(pin.replace(/-/g, '+').replace(/_/g, '/') + '=')
  let hex = ''
  for (let i = 0; i < 6; i++) hex += bin.charCodeAt(i).toString(16).padStart(2, '0')
  hex = hex.toUpperCase()
  return `${hex.slice(0, 4)}-${hex.slice(4, 8)}-${hex.slice(8, 12)}`
}

/** Short lowercase id usable as a secure-storage key suffix (keys must match ^[a-z_]{1,32}$). */
function serverId(cfg: ServerConfig): string {
  const src = cfg.pin ?? cfg.origin
  let h = 0x811c9dc5
  let out = ''
  for (let round = 0; round < 3; round++) {
    for (let i = 0; i < src.length; i++) h = Math.imul(h ^ src.charCodeAt(i), 0x01000193) >>> 0
    for (let k = 0; k < 4; k++) out += String.fromCharCode(97 + ((h >>> (k * 5)) % 26))
  }
  return out
}

function valid(cfg: ServerConfig | null | undefined): cfg is ServerConfig {
  return !!cfg && normalizeServer(cfg.origin) === cfg.origin && (cfg.pin === null || PIN_RE.test(cfg.pin))
}

async function persist(): Promise<void> {
  try {
    await PadLinkNative.secureSet({ key: SERVERS_KEY, value: JSON.stringify({ current: currentId, list: servers }) })
  } catch {
    /* keystore unavailable: config lasts until the app is closed */
  }
}

export function getServer(): ServerConfig | null {
  return isNative ? server : null
}

export function listServers(): ServerConfig[] {
  return isNative ? servers.slice() : []
}

/** Loads the saved PCs from secure storage (call once at boot). Returns the current one. */
export async function loadServer(): Promise<ServerConfig | null> {
  if (!isNative) return null
  try {
    const { value } = await PadLinkNative.secureGet({ key: SERVERS_KEY })
    if (value) {
      const data = JSON.parse(value) as { current: string | null; list: ServerConfig[] }
      servers = (data.list ?? []).filter(valid).map((c) => ({
        ...c,
        id: c.id ?? serverId(c),
        alt: c.alt && c.pin && normalizeServer(c.alt) === c.alt ? c.alt : null,
      }))
      currentId = data.current
    } else {
      // Migrate the single-PC format of earlier versions.
      const legacy = await PadLinkNative.secureGet({ key: LEGACY_SERVER_KEY })
      const cfg = legacy.value ? (JSON.parse(legacy.value) as ServerConfig) : null
      if (valid(cfg)) {
        const id = serverId(cfg)
        servers = [{ ...cfg, id }]
        currentId = id
        const rt = await PadLinkNative.secureGet({ key: LEGACY_REFRESH_KEY })
        if (rt.value) await PadLinkNative.secureSet({ key: `rt_${id}`, value: rt.value })
        await persist()
        await PadLinkNative.secureRemove({ key: LEGACY_SERVER_KEY })
        await PadLinkNative.secureRemove({ key: LEGACY_REFRESH_KEY })
      }
    }
  } catch {
    servers = []
  }
  server = servers.find((c) => c.id === currentId) ?? servers[0] ?? null
  currentId = server?.id ?? null
  return server
}

/** Adds (or updates) a PC and makes it the current one. */
export async function setServer(cfg: ServerConfig): Promise<void> {
  const id = serverId(cfg)
  const prev = servers.find((c) => c.id === id)
  const merged: ServerConfig = { ...prev, ...cfg, id }
  servers = [...servers.filter((c) => c.id !== id), merged]
  currentId = id
  server = merged
  await persist()
}

export async function switchServer(id: string): Promise<boolean> {
  const next = servers.find((c) => c.id === id)
  if (!next) return false
  server = next
  currentId = id
  await persist()
  return true
}

/** Forgets a PC (and its session). Returns the new current PC, if any. */
export async function removeServer(id: string): Promise<ServerConfig | null> {
  servers = servers.filter((c) => c.id !== id)
  try {
    await PadLinkNative.secureRemove({ key: `rt_${id}` })
  } catch {
    /* ignore */
  }
  if (currentId === id) {
    server = servers[0] ?? null
    currentId = server?.id ?? null
  }
  await persist()
  return server
}

/** Updates details of the current PC (new address found via mDNS, name/MAC reported by the PC). */
export async function updateCurrentServer(patch: Partial<Pick<ServerConfig, 'origin' | 'name' | 'mac' | 'alt'>>): Promise<void> {
  if (!server) return
  const next = { ...server, ...patch }
  if (patch.origin && normalizeServer(patch.origin) !== patch.origin) return
  if (patch.alt && normalizeServer(patch.alt) !== patch.alt) return
  if (JSON.stringify(next) === JSON.stringify(server)) return
  server = next
  servers = servers.map((c) => (c.id === next.id ? next : c))
  await persist()
}

/** Absolute URL for an API path ("" prefix on the PWA = same origin). */
export function apiUrl(path: string): string {
  return isNative ? `${server?.origin ?? ''}${path}` : path
}

export function wsUrl(path: string): string {
  const base = isNative ? new URL(server?.origin ?? 'https://invalid') : new URL(location.href)
  const proto = base.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${base.host}${path}`
}

// ---- refresh token (Keystore AES-GCM / Keychain), one per paired PC ---------------
function refreshKey(): string | null {
  return server?.id ? `rt_${server.id}` : null
}

export async function loadRefreshToken(): Promise<string | null> {
  const key = refreshKey()
  if (!isNative || !key) return null
  try {
    const { value } = await PadLinkNative.secureGet({ key })
    return value ?? null
  } catch {
    return null
  }
}

export async function saveRefreshToken(token: string | null): Promise<void> {
  const key = refreshKey()
  if (!isNative || !key) return
  try {
    if (token) await PadLinkNative.secureSet({ key, value: token })
    else await PadLinkNative.secureRemove({ key })
  } catch {
    /* keystore unavailable: session will not survive a restart */
  }
}
