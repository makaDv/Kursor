/**
 * Helpers around the paired PC: find it again after an IP change (mDNS), wake it up
 * (Wake-on-LAN), biometric checks, launcher shortcuts and the store-review prompt.
 */
import { useEffect } from 'react'
import { Capacitor } from '@capacitor/core'
import { PadLinkNative } from './native'
import { getServer, isNative, updateCurrentServer } from './platform'
import { getPrefs } from './settings'

const platform = Capacitor.getPlatform()
export const canWakeOnLan = platform === 'android'
export const canCaptureVolumeKeys = platform === 'android'

/**
 * Looks for the current PC on the LAN (mDNS) by its pinned CA fingerprint and, if it
 * now has a different address, switches to it. Only PCs presenting the SAME pinned
 * certificate are accepted, so a spoofed announcement cannot redirect the app.
 */
export async function rediscover(): Promise<boolean> {
  const cfg = getServer()
  if (!isNative || !cfg?.pin) return false
  try {
    const { pcs } = await PadLinkNative.discover({ timeout: 3000 })
    const match = pcs.find((p) => p.fp === cfg.pin)
    if (match) {
      const origin = `https://${match.host}:${match.port}`
      if (origin === cfg.origin) return false
      // Back on the LAN: keep the Tailscale address as the alternative.
      const onTailscale = /^https:\/\/100\./.test(cfg.origin)
      await updateCurrentServer({ origin, alt: onTailscale ? cfg.origin : cfg.alt })
      return true
    }
  } catch {
    /* discovery unavailable: try the other address below */
  }
  return swapToAlternate()
}

/**
 * Not found on the LAN (e.g. away from home): switch between the LAN address and the
 * Tailscale address of the same PC. The pinned CA does not change, so this never
 * lowers the trust placed in the connection.
 */
async function swapToAlternate(): Promise<boolean> {
  const cfg = getServer()
  if (!cfg?.pin || !cfg.alt || cfg.alt === cfg.origin) return false
  await updateCurrentServer({ origin: cfg.alt, alt: cfg.origin })
  return true
}

// ---- FLAG_SECURE (Android) --------------------------------------------------------------
let secureUsers = 0

/**
 * While mounted, Android blocks screenshots, screen recording and the "recent apps"
 * preview (password/PIN screens, PC screen view). Reference-counted across components.
 */
export function useSecureScreen(active = true): void {
  useEffect(() => {
    if (!isNative || !active) return
    if (secureUsers++ === 0) void PadLinkNative.setSecure({ enabled: true }).catch(() => undefined)
    return () => {
      if (--secureUsers === 0) void PadLinkNative.setSecure({ enabled: false }).catch(() => undefined)
    }
  }, [active])
}

let lastRediscover = 0
/** Rate-limited rediscover for background use (at most every 30 s). */
export async function maybeRediscover(): Promise<boolean> {
  if (Date.now() - lastRediscover < 30_000) return false
  lastRediscover = Date.now()
  return rediscover()
}

export async function wakePc(): Promise<boolean> {
  const mac = getServer()?.mac
  if (!canWakeOnLan || !mac) return false
  try {
    await PadLinkNative.wakeOnLan({ mac })
    return true
  } catch {
    return false
  }
}

// ---- biometrics ----------------------------------------------------------------------------
let bioAvailable: boolean | null = null

export async function biometricAvailable(): Promise<boolean> {
  if (!isNative) return false
  if (bioAvailable === null) {
    try {
      bioAvailable = (await PadLinkNative.biometricAvailable()).available
    } catch {
      bioAvailable = false
    }
  }
  return bioAvailable
}

/** Asks for fingerprint/face/PIN. Resolves true when not available or not required. */
export async function confirmWithBiometrics(reason: string, kind: 'unlock' | 'power'): Promise<boolean> {
  const prefs = getPrefs()
  const wanted = kind === 'unlock' ? prefs.biometricLock : prefs.biometricPower
  if (!wanted || !(await biometricAvailable())) return true
  try {
    return (await PadLinkNative.biometricAuth({ reason })).ok
  } catch {
    return false
  }
}

// ---- store review prompt ---------------------------------------------------------------------
// Asked only after 3+ sessions that connected without errors, at most every 120 days,
// never right after a problem. The stores decide whether the dialog actually appears.
const REVIEW_KEY = 'padlink.review.v1'

interface ReviewState {
  goodSessions: number
  askedAt: number
}

function readReview(): ReviewState {
  try {
    return { goodSessions: 0, askedAt: 0, ...JSON.parse(localStorage.getItem(REVIEW_KEY) ?? '{}') }
  } catch {
    return { goodSessions: 0, askedAt: 0 }
  }
}

function writeReview(s: ReviewState) {
  try {
    localStorage.setItem(REVIEW_KEY, JSON.stringify(s))
  } catch {
    /* ignore */
  }
}

let sessionCounted = false
let sessionHadError = false

export function noteSessionError() {
  sessionHadError = true
}

/** Call once the control link is open; may show the rating dialog a while later. */
export function noteGoodSession() {
  if (!isNative || sessionCounted) return
  sessionCounted = true
  const st = readReview()
  st.goodSessions += 1
  writeReview(st)
  if (st.goodSessions < 3 || Date.now() - st.askedAt < 120 * 86_400_000) return
  window.setTimeout(() => {
    if (sessionHadError || document.visibilityState !== 'visible') return
    writeReview({ ...readReview(), askedAt: Date.now() })
    void PadLinkNative.requestReview().catch(() => undefined)
  }, 120_000)
}

// ---- launcher shortcuts --------------------------------------------------------------------
export async function launchTab(): Promise<string | null> {
  if (!isNative) return null
  try {
    return (await PadLinkNative.getLaunchTab()).tab
  } catch {
    return null
  }
}
