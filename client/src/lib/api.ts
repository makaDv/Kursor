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
type PasswordListener = (needed: boolean) => void

/** Server answers meaning "ask the user for the PC password" (the session itself is still valid). */
export const PASSWORD_CODES = new Set(['password_required', 'invalid_password', 'locked_out', 'password_not_set'])
export const isPasswordError = (err: unknown): err is ApiError =>
  err instanceof ApiError && PASSWORD_CODES.has(err.code)

let accessToken: string | null = null
let accessExp = 0
let deviceId: string | null = null
let refreshing: Promise<boolean> | null = null
const listeners = new Set<AuthListener>()
// PC password: kept only in memory for this app session, never written to storage.
let sessionPassword: string | null = null
let passwordNeeded = false
const pwListeners = new Set<PasswordListener>()

function setPasswordNeeded(needed: boolean) {
  if (passwordNeeded === needed) return
  passwordNeeded = needed
  pwListeners.forEach((fn) => fn(needed))
}

export function onPasswordNeeded(fn: PasswordListener): () => void {
  pwListeners.add(fn)
  return () => pwListeners.delete(fn)
}

export function isPasswordNeeded() {
  return passwordNeeded
}

export function setSessionPassword(pw: string) {
  sessionPassword = pw
}

/**
 * Forgets the PC password and the access token (e.g. after minutes in the background):
 * the next use asks for the password again. The paired session (refresh token) stays.
 */
export function lockSession() {
  sessionPassword = null
  accessToken = null
  accessExp = 0
  setPasswordNeeded(true)
}

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

export async function pair(secret: string, deviceName: string, password: string): Promise<void> {
  const t = await rawRequest<TokenResponse>('/api/auth/pair', {
    method: 'POST',
    body: JSON.stringify({ secret, password, device_name: deviceName, client: isNative ? 'app' : 'web' }),
  })
  sessionPassword = password
  setPasswordNeeded(false)
  setAuth(t)
}

/**
 * Exchanges the refresh token (cookie or secure storage) for a new access token,
 * proving the PC password. Concurrent calls share one request.
 * Throws ApiError for network/pin problems and when the PC password is needed
 * (isPasswordError): the paired session is kept in that case.
 */
export function refresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      const payload: Record<string, string> = {}
      if (isNative) {
        const stored = await loadRefreshToken()
        if (!stored) throw new ApiError(401, 'no_session', t('Sessione assente'))
        payload.refresh_token = stored
      }
      // Without a password the server still tells "password_required" (valid session)
      // from "no_session", and never spends the refresh token.
      if (sessionPassword) payload.password = sessionPassword
      return rawRequest<TokenResponse>('/api/auth/refresh', { method: 'POST', body: JSON.stringify(payload) })
    })()
      .then((t) => {
        setPasswordNeeded(false)
        setAuth(t)
        return true
      })
      .catch((err: unknown) => {
        if (isPasswordError(err)) {
          if (err.code === 'invalid_password') sessionPassword = null
          accessToken = null
          accessExp = 0
          setPasswordNeeded(true)
          throw err
        }
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
    if (err instanceof ApiError && err.status === 401 && !isPasswordError(err)) setAuth(null)
    throw err
  }
}

export async function logout(): Promise<void> {
  try {
    await authedRequest('/api/auth/logout', { method: 'POST', body: '{}' })
  } finally {
    sessionPassword = null
    setPasswordNeeded(false)
    setAuth(null)
  }
}

export function forgetSession() {
  sessionPassword = null
  setPasswordNeeded(false)
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
