import { useRef, useState } from 'react'
import { api, ApiError } from '../lib/api'
import { t, useLang } from '../lib/i18n'
import type { PadLinkSocket } from '../lib/socket'
import { getPrefs, haptic, usePrefs } from '../lib/settings'
import { Icon } from './Icon'

type Mod = 'ctrl' | 'alt' | 'shift' | 'win'

const SPECIAL: [string, string][] = [
  ['Esc', 'esc'],
  ['Tab', 'tab'],
  ['⌫', 'backspace'],
  ['Canc', 'delete'],
  ['Invio', 'enter'],
  ['Home', 'home'],
  ['Fine', 'end'],
  ['PgSu', 'page_up'],
  ['PgGiù', 'page_down'],
  ['Stamp', 'print_screen'],
]

const ARROWS: [string, string][] = [
  ['←', 'left'],
  ['↑', 'up'],
  ['↓', 'down'],
  ['→', 'right'],
]

// Slides / presentations (PowerPoint, Google Slides, PDF viewers).
const PRESENTATION: [string, string[]][] = [
  ['◀ Indietro', ['left']],
  ['Avanti ▶', ['right']],
  ['Avvia (F5)', ['f5']],
  ['Schermo nero', ['b']],
  ['Esci', ['esc']],
]

const SHORTCUTS: [string, string[]][] = [
  ['Alt+Tab', ['alt', 'tab']],
  ['Copia', ['ctrl', 'c']],
  ['Incolla', ['ctrl', 'v']],
  ['Taglia', ['ctrl', 'x']],
  ['Annulla', ['ctrl', 'z']],
  ['Ripeti', ['ctrl', 'y']],
  ['Tutto', ['ctrl', 'a']],
  ['Salva', ['ctrl', 's']],
  ['Trova', ['ctrl', 'f']],
  ['Desktop', ['win', 'd']],
  ['Esplora', ['win', 'e']],
  ['Task Mgr', ['ctrl', 'shift', 'esc']],
  ['Nuova tab', ['ctrl', 't']],
  ['Chiudi tab', ['ctrl', 'w']],
  ['Alt+F4', ['alt', 'f4']],
  ['Win', ['win']],
]

const MEDIA: [string, string][] = [
  ['⏮', 'prev_track'],
  ['⏯', 'play_pause'],
  ['⏭', 'next_track'],
  ['🔉', 'volume_down'],
  ['🔇', 'volume_mute'],
  ['🔊', 'volume_up'],
]

function commonPrefix(a: string, b: string) {
  let i = 0
  while (i < a.length && i < b.length && a[i] === b[i]) i++
  return i
}

export default function KeyboardPanel({ socket, canClipboard = true }: { socket: PadLinkSocket; canClipboard?: boolean }) {
  useLang()
  const [prefs, setPrefs] = usePrefs()
  const [clipNote, setClipNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [mods, setMods] = useState<Set<Mod>>(new Set())
  const [live, setLive] = useState(true)
  const [text, setText] = useState('')
  const [showF, setShowF] = useState(false)
  const prev = useRef('')

  const keys = (k: string[]) => {
    socket.send({ t: 'keys', k })
    haptic(8)
  }

  const tapKey = (key: string) => {
    keys([...mods, key])
    if (mods.size) setMods(new Set())
  }

  const toggleMod = (m: Mod) => {
    const next = new Set(mods)
    if (next.has(m)) next.delete(m)
    else next.add(m)
    setMods(next)
    haptic(5)
  }

  // Live mode: diff the field against what we already sent, so mobile autocorrect
  // and word suggestions turn into backspaces + new text on the PC.
  const onLiveChange = (value: string) => {
    const p = commonPrefix(prev.current, value)
    const deletions = prev.current.length - p
    for (let i = 0; i < deletions; i++) socket.send({ t: 'keys', k: ['backspace'] })
    const added = value.slice(p)
    if (added) socket.send({ t: 'text', s: added })
    prev.current = value
    setText(value.length > 500 ? '' : value)
    if (value.length > 500) prev.current = ''
  }

  /** Remembers the last 8 phrases sent (only on this phone, never on the PC). */
  const remember = (phrase: string) => {
    const p = phrase.trim()
    if (p.length < 2 || p.length > 300) return
    setPrefs({ phrases: [p, ...getPrefs().phrases.filter((x) => x !== p)].slice(0, 8) })
  }

  const sendBuffered = () => {
    if (!text) return
    socket.send({ t: 'text', s: text.slice(0, 2000) })
    remember(text)
    setText('')
    haptic(10)
  }

  // ---- clipboard (explicit buttons only; nothing is synced automatically) ----
  const copyFromPc = async () => {
    try {
      const { text: pcText } = await api.clipboardGet()
      if (!pcText) return setClipNote({ ok: false, text: t('Gli appunti del PC sono vuoti.') })
      await navigator.clipboard.writeText(pcText)
      setClipNote({ ok: true, text: t('Copiato sul telefono ({n} caratteri).', { n: pcText.length }) })
    } catch (err) {
      setClipNote({ ok: false, text: err instanceof ApiError ? err.message : t('Impossibile copiare negli appunti del telefono.') })
    }
  }

  const pasteToPc = async () => {
    try {
      const phoneText = text || (await navigator.clipboard.readText())
      if (!phoneText) return setClipNote({ ok: false, text: t('Niente da incollare: scrivi o copia un testo sul telefono.') })
      await api.clipboardSet(phoneText)
      setClipNote({ ok: true, text: t('Negli appunti del PC: premi Ctrl+V dove vuoi incollarlo.') })
    } catch (err) {
      setClipNote({ ok: false, text: err instanceof ApiError ? err.message : t('Impossibile leggere gli appunti del telefono: scrivi il testo nel campo sopra.') })
    }
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-3 pb-6">
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span>{live ? t('Digitazione in tempo reale') : t('Scrivi e invia')}</span>
          <button
            className={`rounded-full px-3 py-1 ${live ? 'bg-accent text-white' : 'bg-ink-800'}`}
            onClick={() => {
              setLive(!live)
              setText('')
              prev.current = ''
            }}
          >
            {t('In diretta')} {live ? 'ON' : 'OFF'}
          </button>
        </div>
        <div className="flex gap-2">
          <textarea
            rows={2}
            value={text}
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            placeholder={live ? t('Tocca qui e scrivi…') : t('Testo da inviare')}
            aria-label={t('Testo da inviare')}
            onChange={(e) => (live ? onLiveChange(e.target.value) : setText(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                if (live) {
                  remember(text)
                  socket.send({ t: 'keys', k: ['enter'] })
                  setText('')
                  prev.current = ''
                } else sendBuffered()
              }
            }}
            className="min-w-0 flex-1 resize-none rounded-xl bg-ink-800 p-3 text-base outline-none focus:ring-2 focus:ring-accent"
          />
          {!live && (
            <button className="key w-14" onClick={sendBuffered} aria-label={t('Invia')}>
              <Icon name="send" />
            </button>
          )}
        </div>
        {prefs.phrases.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1" aria-label={t('Frasi recenti')}>
            {prefs.phrases.map((ph) => (
              <button
                key={ph}
                className="chip shrink-0 border border-white/5 bg-ink-800 px-3 py-1.5 text-xs text-gray-300"
                onClick={() => {
                  socket.send({ t: 'text', s: ph })
                  haptic(8)
                }}
              >
                {ph.length > 24 ? `${ph.slice(0, 24)}…` : ph}
              </button>
            ))}
          </div>
        )}
        {canClipboard && (
          <div className="grid grid-cols-2 gap-2">
            <button className="key text-xs" onClick={() => void copyFromPc()}>
              {t('Copia dal PC')}
            </button>
            <button className="key text-xs" onClick={() => void pasteToPc()}>
              {t('Incolla sul PC')}
            </button>
          </div>
        )}
        {clipNote && (
          <p className={`text-center text-xs ${clipNote.ok ? 'text-emerald-300' : 'text-red-300'}`} role="status">
            {clipNote.text}
          </p>
        )}
      </section>

      <section className="grid grid-cols-4 gap-2">
        {(['ctrl', 'alt', 'shift', 'win'] as Mod[]).map((m) => (
          <button key={m} className={`key ${mods.has(m) ? 'key-on' : ''}`} onClick={() => toggleMod(m)}>
            {m === 'win' ? 'Win' : m[0].toUpperCase() + m.slice(1)}
          </button>
        ))}
      </section>

      <section className="grid grid-cols-5 gap-2">
        {SPECIAL.map(([label, k]) => (
          <button key={k} className="key" onClick={() => tapKey(k)}>
            {label}
          </button>
        ))}
        {ARROWS.map(([label, k]) => (
          <button key={k} className="key text-lg" onClick={() => tapKey(k)}>
            {label}
          </button>
        ))}
        <button className={`key ${showF ? 'key-on' : ''}`} onClick={() => setShowF(!showF)}>
          F1-12
        </button>
      </section>

      {showF && (
        <section className="grid grid-cols-6 gap-2">
          {Array.from({ length: 12 }, (_, i) => `f${i + 1}`).map((k) => (
            <button key={k} className="key" onClick={() => tapKey(k)}>
              {k.toUpperCase()}
            </button>
          ))}
        </section>
      )}

      <section className="flex flex-col gap-2">
        <h3 className="section-title">{t('Scorciatoie')}</h3>
        <div className="grid grid-cols-4 gap-2">
          {SHORTCUTS.map(([label, k]) => (
            <button key={label} className="key text-xs" onClick={() => keys(k)}>
              {t(label)}
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="section-title">{t('Multimedia')}</h3>
        <div className="grid grid-cols-6 gap-2">
          {MEDIA.map(([label, k]) => (
            <button key={k} className="key text-lg" onClick={() => keys([k])}>
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="section-title">{t('Presentazioni')}</h3>
        <div className="grid grid-cols-5 gap-2">
          {PRESENTATION.map(([label, k]) => (
            <button key={label} className="key text-xs" onClick={() => keys(k)}>
              {t(label)}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
