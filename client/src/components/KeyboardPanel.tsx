import { useRef, useState } from 'react'
import type { KursorSocket } from '../lib/socket'
import { haptic } from '../lib/settings'
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

export default function KeyboardPanel({ socket }: { socket: KursorSocket }) {
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

  const sendBuffered = () => {
    if (!text) return
    socket.send({ t: 'text', s: text.slice(0, 2000) })
    setText('')
    haptic(10)
  }

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-3 pb-6">
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span>{live ? 'Digitazione in tempo reale' : 'Scrivi e invia'}</span>
          <button
            className={`rounded-full px-3 py-1 ${live ? 'bg-accent text-white' : 'bg-ink-800'}`}
            onClick={() => {
              setLive(!live)
              setText('')
              prev.current = ''
            }}
          >
            Live {live ? 'ON' : 'OFF'}
          </button>
        </div>
        <div className="flex gap-2">
          <textarea
            rows={2}
            value={text}
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            placeholder={live ? 'Tocca qui e scrivi…' : 'Testo da inviare'}
            onChange={(e) => (live ? onLiveChange(e.target.value) : setText(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                if (live) {
                  socket.send({ t: 'keys', k: ['enter'] })
                  setText('')
                  prev.current = ''
                } else sendBuffered()
              }
            }}
            className="min-w-0 flex-1 resize-none rounded-xl bg-ink-800 p-3 text-base outline-none focus:ring-2 focus:ring-accent"
          />
          {!live && (
            <button className="key w-14" onClick={sendBuffered} aria-label="Invia">
              <Icon name="send" />
            </button>
          )}
        </div>
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
        <h3 className="section-title">Scorciatoie</h3>
        <div className="grid grid-cols-4 gap-2">
          {SHORTCUTS.map(([label, k]) => (
            <button key={label} className="key text-xs" onClick={() => keys(k)}>
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="section-title">Multimedia</h3>
        <div className="grid grid-cols-6 gap-2">
          {MEDIA.map(([label, k]) => (
            <button key={k} className="key text-lg" onClick={() => keys([k])}>
              {label}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
