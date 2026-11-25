import { useCallback, useEffect, useState } from 'react'

/** Per-device UI preferences. Nothing sensitive is stored here. */
export interface Prefs {
  sensitivity: number
  acceleration: number
  scrollSpeed: number
  naturalScroll: boolean
  haptics: boolean
  streamFps: number
  streamQuality: number
  streamWidth: number
  streamFormat: 'jpeg' | 'webp'
  streamAuto: boolean
  monitor: number
  /** Appearance & accessibility */
  theme: 'auto' | 'dark' | 'light'
  textScale: number
  leftHanded: boolean
  lang: 'auto' | 'it' | 'en'
  /** Security */
  biometricLock: boolean
  biometricPower: boolean
  /** Android: hardware volume keys control the PC volume while the app is open */
  volumeKeys: boolean
  /** Recently typed phrases (Tastiera), newest first */
  phrases: string[]
}

export const DEFAULT_PREFS: Prefs = {
  sensitivity: 1.4,
  acceleration: 0.8,
  scrollSpeed: 1,
  naturalScroll: true,
  haptics: true,
  streamFps: 12,
  streamQuality: 60,
  streamWidth: 1280,
  streamFormat: 'jpeg',
  streamAuto: true,
  monitor: 1,
  theme: 'auto',
  textScale: 1,
  leftHanded: false,
  lang: 'auto',
  biometricLock: false,
  biometricPower: true,
  volumeKeys: false,
  phrases: [],
}

const KEY = 'padlink.prefs.v1'
const LEGACY_KEY = 'kursor.prefs.v1' // used before the rename

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY) ?? localStorage.getItem(LEGACY_KEY)
    if (raw) return { ...DEFAULT_PREFS, ...JSON.parse(raw) }
  } catch {
    /* storage unavailable (private mode) */
  }
  return DEFAULT_PREFS
}

let current = load()
const subs = new Set<(p: Prefs) => void>()

export function getPrefs() {
  return current
}

export function usePrefs(): [Prefs, (patch: Partial<Prefs>) => void] {
  const [prefs, setPrefs] = useState(current)
  useEffect(() => {
    subs.add(setPrefs)
    return () => {
      subs.delete(setPrefs)
    }
  }, [])
  const update = useCallback((patch: Partial<Prefs>) => {
    current = { ...current, ...patch }
    try {
      localStorage.setItem(KEY, JSON.stringify(current))
    } catch {
      /* ignore */
    }
    subs.forEach((fn) => fn(current))
  }, [])
  return [prefs, update]
}

export function haptic(ms = 10) {
  if (current.haptics && 'vibrate' in navigator) {
    try {
      navigator.vibrate(ms)
    } catch {
      /* unsupported */
    }
  }
}

/** Applies theme and text size to the document (called on boot and whenever prefs change). */
export function applyAppearance(p: Prefs = current) {
  const root = document.documentElement
  const light = p.theme === 'light' || (p.theme === 'auto' && window.matchMedia?.('(prefers-color-scheme: light)').matches)
  root.dataset.theme = light ? 'light' : 'dark'
  root.style.fontSize = `${Math.round(16 * Math.min(1.4, Math.max(0.85, p.textScale)))}px`
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', light ? '#f6f7fb' : '#0b0f17')
}

subs.add(applyAppearance)
window.matchMedia?.('(prefers-color-scheme: light)').addEventListener?.('change', () => applyAppearance())
