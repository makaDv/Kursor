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
}

const KEY = 'kursor.prefs.v1'

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY)
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
