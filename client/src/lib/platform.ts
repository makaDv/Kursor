/**
 * Runtime differences between the PWA (served by the PC itself, same origin)
 * and the Android app (assets bundled in the APK, PC reached cross-origin).
 */
import { Capacitor, registerPlugin } from '@capacitor/core'

export const isNative = Capacitor.isNativePlatform()

// ---- PC address (native only; not secret) ------------------------------------
const SERVER_KEY = 'kursor.server.v1'

/** Normalises "192.168.1.10", "192.168.1.10:8443" or a full URL to an https origin. */
export function normalizeServer(input: string): string | null {
  let s = input.trim()
  if (!s) return null
  if (!/^https?:\/\//i.test(s)) s = `https://${s}`
  try {
    const u = new URL(s)
    if (u.protocol !== 'https:') return null // the app never talks plain HTTP
    if (!u.port && /^\d{1,3}(\.\d{1,3}){3}$/.test(u.hostname)) u.port = '8443'
    return u.origin
  } catch {
    return null
  }
}

export function getServer(): string | null {
  if (!isNative) return null
  try {
    return localStorage.getItem(SERVER_KEY)
  } catch {
    return null
  }
}

export function setServer(origin: string) {
  try {
    localStorage.setItem(SERVER_KEY, origin)
  } catch {
    /* ignore */
  }
}

/** Absolute URL for an API path ("" prefix on the PWA = same origin). */
export function apiUrl(path: string): string {
  return isNative ? `${getServer() ?? ''}${path}` : path
}

export function wsUrl(path: string): string {
  const base = isNative ? new URL(getServer() ?? 'https://invalid') : new URL(location.href)
  const proto = base.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${base.host}${path}`
}

// ---- secure storage (Android Keystore AES-GCM, see SecureStorePlugin.java) ----
interface SecureStorePlugin {
  get(opts: { key: string }): Promise<{ value?: string | null }>
  set(opts: { key: string; value: string }): Promise<void>
  remove(opts: { key: string }): Promise<void>
}

const SecureStore = registerPlugin<SecureStorePlugin>('SecureStore')
const REFRESH_KEY = 'refresh_token'

export async function loadRefreshToken(): Promise<string | null> {
  if (!isNative) return null
  try {
    const { value } = await SecureStore.get({ key: REFRESH_KEY })
    return value ?? null
  } catch {
    return null
  }
}

export async function saveRefreshToken(token: string | null): Promise<void> {
  if (!isNative) return
  try {
    if (token) await SecureStore.set({ key: REFRESH_KEY, value: token })
    else await SecureStore.remove({ key: REFRESH_KEY })
  } catch {
    /* keystore unavailable: session will not survive a restart */
  }
}
