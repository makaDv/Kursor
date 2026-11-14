/**
 * Minimal i18n: the Italian text IS the key, so untranslated strings fall back
 * gracefully. English strings live in ./en.ts. Use {name} placeholders:
 *   t('Associa {n} telefoni', { n: 3 })
 */
import { useEffect, useState } from 'react'
import { getPrefs, usePrefs } from './settings'
import { EN } from './en'

export type Lang = 'it' | 'en'

export function currentLang(): Lang {
  const pref = getPrefs().lang
  if (pref === 'it' || pref === 'en') return pref
  const nav = (navigator.languages?.[0] ?? navigator.language ?? 'it').toLowerCase()
  return nav.startsWith('it') ? 'it' : 'en'
}

export function t(it: string, vars?: Record<string, string | number>): string {
  let s = currentLang() === 'en' ? (EN[it] ?? it) : it
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v))
  return s
}

/** Re-renders the calling component when the language preference changes. */
export function useLang(): Lang {
  const [prefs] = usePrefs()
  const [lang, setLang] = useState(currentLang)
  useEffect(() => setLang(currentLang()), [prefs.lang])
  return lang
}
