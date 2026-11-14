/**
 * Runtime differences between the PWA (served by the PC itself, same origin)
 * and the store apps (assets bundled in the app, PC reached through the native
 * KursorNative plugin with certificate pinning).
 */
import { Capacitor } from '@capacitor/core'
import { KursorNative } from './native'

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
}

const SERVER_KEY = 'server'
const REFRESH_KEY = 'refresh_token'
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

/** Parses the pairing QR / link: https://IP:8443/#pair=CODE&fp=PIN */
export function parsePairingLink(text: string): { origin: string; code: string; pin: string | null } | null {
  const m = text.trim().match(/^(https:\/\/[^/#\s]+)\/?#(.+)$/)
  if (!m) return null
  const params = new URLSearchParams(m[2])
  const code = params.get('pair')
  const origin = normalizeServer(m[1])
  if (!origin || !code || !/^[A-Za-z0-9_-]{6,64}$/.test(code)) return null
  const fp = params.get('fp')
  return { origin, code, pin: fp && PIN_RE.test(fp) ? fp : null }
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

export function getServer(): ServerConfig | null {
  return isNative ? server : null
}

/** Loads the saved PC from secure storage (call once at boot). */
export async function loadServer(): Promise<ServerConfig | null> {
  if (!isNative) return null
  try {
    const { value } = await KursorNative.secureGet({ key: SERVER_KEY })
    const parsed = value ? (JSON.parse(value) as ServerConfig) : null
    if (parsed && normalizeServer(parsed.origin) === parsed.origin && (parsed.pin === null || PIN_RE.test(parsed.pin))) {
      server = parsed
    }
  } catch {
    server = null
  }
  return server
}

export async function setServer(cfg: ServerConfig): Promise<void> {
  server = cfg
  try {
    await KursorNative.secureSet({ key: SERVER_KEY, value: JSON.stringify(cfg) })
  } catch {
    /* keystore unavailable: config lasts until the app is closed */
  }
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

// ---- refresh token (Keystore AES-GCM / Keychain) ---------------------------------
export async function loadRefreshToken(): Promise<string | null> {
  if (!isNative) return null
  try {
    const { value } = await KursorNative.secureGet({ key: REFRESH_KEY })
    return value ?? null
  } catch {
    return null
  }
}

export async function saveRefreshToken(token: string | null): Promise<void> {
  if (!isNative) return
  try {
    if (token) await KursorNative.secureSet({ key: REFRESH_KEY, value: token })
    else await KursorNative.secureRemove({ key: REFRESH_KEY })
  } catch {
    /* keystore unavailable: session will not survive a restart */
  }
}
