/**
 * Auth-aware HTTP client.
 *
 * - The access token (JWT, ~10 min) lives only in memory: never in localStorage,
 *   so an XSS bug cannot exfiltrate a long-lived credential from storage.
 * - The refresh token is an HttpOnly + Secure + SameSite=Strict cookie scoped to
 *   /api/auth: JavaScript can never read it. It is rotated on every refresh.
 * - Store apps: cookies would be cross-site, so the server returns the refresh
 *   token in the body and it is kept in the Android Keystore / iOS Keychain.
 */
import { apiUrl, isNative, loadRefreshToken, saveRefreshToken } from './platform'
import { httpRequest, TransportError } from './transport'
import { t } from './i18n'

export class ApiError extends Error {
  status: number
  code: string
  retryAfter?: number
  remainingAttempts?: number

  constructor(status: number, code: string, message: string, extra: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    if (typeof extra.retry_after === 'number') this.retryAfter = extra.retry_after
    if (typeof extra.remaining_attempts === 'number') this.remainingAttempts = extra.remaining_attempts
  }
}

interface TokenResponse {
  access_token: string
  expires_at: number
  device_id: string
  refresh_token?: string
}

type AuthListener = (authed: boolean) => void

let accessToken: string | null = null
let accessExp = 0
let deviceId: string | null = null
let refreshing: Promise<boolean> | null = null
const listeners = new Set<AuthListener>()

export function onAuthChange(fn: AuthListener): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function setAuth(t: TokenResponse | null) {
  accessToken = t?.access_token ?? null
  accessExp = t?.expires_at ?? 0
  deviceId = t?.device_id ?? null
  if (t?.refresh_token) void saveRefreshToken(t.refresh_token)
  else if (!t) void saveRefreshToken(null)
  listeners.forEach((fn) => fn(accessToken !== null))
}

export function currentDeviceId() {
  return deviceId
}

export function tokenExpiry() {
  return accessExp
}

function toApiError(status: number, body: unknown): ApiError {
  let detail: Record<string, unknown> = {}
  const d = (body as { detail?: unknown } | null)?.detail
  if (d && typeof d === 'object' && !Array.isArray(d)) detail = d as Record<string, unknown>
  const code = typeof detail.code === 'string' ? detail.code : `http_${status}`
  const message = typeof detail.message === 'string' ? t(detail.message) : `${t('Errore')} ${status}`
  return new ApiError(status, code, message, detail)
}

const TRANSPORT_MESSAGES: Record<string, string> = {
  network: 'PC non raggiungibile',
  tls: 'Connessione sicura non riuscita',
  pin_mismatch:
    'Il certificato del PC non corrisponde a quello associato. Potrebbe essere un tentativo di intercettazione, oppure il PC ha rigenerato i certificati: associa di nuovo.',
}

async function rawRequest<T>(path: string, init: { method?: string; body?: string; headers?: Record<string, string> } = {}): Promise<T> {
  let res
  try {
    res = await httpRequest(apiUrl(path), {
      method: init.method,
      body: init.body,
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    })
  } catch (err) {
    const code = err instanceof TransportError ? err.code : 'network'
    throw new ApiError(0, code === 'pin_mismatch' ? 'pin_mismatch' : 'network', t(TRANSPORT_MESSAGES[code] ?? TRANSPORT_MESSAGES.network))
  }
  if (!res.ok) throw toApiError(res.status, res.json())
  return res.json() as T
}

export async function pair(secret: string, deviceName: string): Promise<void> {
  const t = await rawRequest<TokenResponse>('/api/auth/pair', {
    method: 'POST',
    body: JSON.stringify({ secret, device_name: deviceName, client: isNative ? 'app' : 'web' }),
  })
  setAuth(t)
}

/** Exchanges the refresh cookie for a new access token. Concurrent calls share one request. */
export function refresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      let body = '{}'
      if (isNative) {
        const stored = await loadRefreshToken()
        if (!stored) throw new ApiError(401, 'no_session', t('Sessione assente'))
        body = JSON.stringify({ refresh_token: stored })
      }
      return rawRequest<TokenResponse>('/api/auth/refresh', { method: 'POST', body })
    })()
      .then((t) => {
        setAuth(t)
        return true
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) setAuth(null)
        if (err instanceof ApiError && (err.code === 'network' || err.code === 'pin_mismatch')) throw err
        return false
      })
      .finally(() => {
        refreshing = null
      })
  }
  return refreshing
}

/** Valid access token, refreshed when it expires within 60 s. */
export async function getAccessToken(): Promise<string | null> {
  if (accessToken && accessExp - Date.now() / 1000 > 60) return accessToken
  const ok = await refresh()
  return ok ? accessToken : null
}

export async function authedRequest<T>(
  path: string,
  init: { method?: string; body?: string; headers?: Record<string, string> } = {},
): Promise<T> {
  const call = async () => {
    const token = await getAccessToken()
    if (!token) throw new ApiError(401, 'unauthorized', t('Sessione scaduta'))
    return rawRequest<T>(path, { ...init, headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` } })
  }
  try {
    return await call()
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && err.code === 'token_expired') {
      accessExp = 0
      return call()
    }
    if (err instanceof ApiError && err.status === 401) setAuth(null)
    throw err
  }
}

export async function logout(): Promise<void> {
  try {
    await authedRequest('/api/auth/logout', { method: 'POST', body: '{}' })
  } finally {
    setAuth(null)
  }
}

export function forgetSession() {
  setAuth(null)
}

// ---- typed endpoints ----------------------------------------------------------
export interface Device {
  id: string
  name: string
  created_at: number
  last_seen: number
  last_ip: string
  user_agent: string
  current: boolean
  perms?: Record<string, boolean>
}

export interface PcWindow {
  id: number
  title: string
  app: string
  exe: string
  pid: number
  minimized: boolean
  maximized: boolean
  focused: boolean
  protected: boolean
  icon?: string | null
}

export type WindowAction = 'focus' | 'minimize' | 'maximize' | 'restore' | 'close' | 'kill'

export const api = {
  devices: () => authedRequest<{ current: string; devices: Device[] }>('/api/devices'),
  revokeDevice: (id: string) => authedRequest<{ ok: boolean }>(`/api/devices/${id}`, { method: 'DELETE' }),
  clipboardGet: () => authedRequest<{ text: string }>('/api/clipboard/get', { method: 'POST', body: '{}' }),
  clipboardSet: (text: string) =>
    authedRequest<{ ok: boolean }>('/api/clipboard/set', { method: 'POST', body: JSON.stringify({ text }) }),
  windows: () => authedRequest<{ windows: PcWindow[] }>('/api/windows'),
  windowAction: (id: number, action: WindowAction) =>
    authedRequest<{ ok: boolean }>(`/api/windows/${id}/${action}`, {
      method: 'POST',
      body: JSON.stringify(action === 'close' || action === 'kill' ? { confirm: action } : {}),
    }),
  system: (action: 'lock' | 'sleep' | 'shutdown') =>
    authedRequest<{ ok: boolean }>(`/api/system/${action}`, {
      method: 'POST',
      body: JSON.stringify({ confirm: action }),
    }),
}
