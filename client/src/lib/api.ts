/**
 * Auth-aware HTTP client.
 *
 * - The access token (JWT, ~10 min) lives only in memory: never in localStorage,
 *   so an XSS bug cannot exfiltrate a long-lived credential from storage.
 * - The refresh token is an HttpOnly + Secure + SameSite=Strict cookie scoped to
 *   /api/auth: JavaScript can never read it. It is rotated on every refresh.
 */

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
  listeners.forEach((fn) => fn(accessToken !== null))
}

export function currentDeviceId() {
  return deviceId
}

export function tokenExpiry() {
  return accessExp
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: Record<string, unknown> = {}
  try {
    const body = await res.json()
    if (body && typeof body.detail === 'object' && !Array.isArray(body.detail)) detail = body.detail
  } catch {
    /* non-JSON error body */
  }
  const code = typeof detail.code === 'string' ? detail.code : `http_${res.status}`
  const message = typeof detail.message === 'string' ? detail.message : `Errore ${res.status}`
  return new ApiError(res.status, code, message, detail)
}

async function rawRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'network', 'PC non raggiungibile')
  }
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

export async function pair(secret: string, deviceName: string): Promise<void> {
  const t = await rawRequest<TokenResponse>('/api/auth/pair', {
    method: 'POST',
    body: JSON.stringify({ secret, device_name: deviceName }),
  })
  setAuth(t)
}

/** Exchanges the refresh cookie for a new access token. Concurrent calls share one request. */
export function refresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = rawRequest<TokenResponse>('/api/auth/refresh', { method: 'POST', body: '{}' })
      .then((t) => {
        setAuth(t)
        return true
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) setAuth(null)
        if (err instanceof ApiError && err.code === 'network') throw err
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

export async function authedRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const call = async () => {
    const token = await getAccessToken()
    if (!token) throw new ApiError(401, 'unauthorized', 'Sessione scaduta')
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
}

export const api = {
  devices: () => authedRequest<{ current: string; devices: Device[] }>('/api/devices'),
  revokeDevice: (id: string) => authedRequest<{ ok: boolean }>(`/api/devices/${id}`, { method: 'DELETE' }),
  system: (action: 'lock' | 'sleep' | 'shutdown') =>
    authedRequest<{ ok: boolean }>(`/api/system/${action}`, {
      method: 'POST',
      body: JSON.stringify({ confirm: action }),
    }),
}
