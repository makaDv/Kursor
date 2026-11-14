import { useEffect, useMemo, useState } from 'react'
import { ApiError, onAuthChange, refresh } from './lib/api'
import { getServer, isNative, loadServer } from './lib/platform'
import { KursorSocket, type SocketStatus } from './lib/socket'
import PairScreen from './components/PairScreen'
import Trackpad from './components/Trackpad'
import KeyboardPanel from './components/KeyboardPanel'
import ScreenPanel from './components/ScreenPanel'
import MorePanel from './components/MorePanel'
import AppsPanel from './components/AppsPanel'
import { Icon, type IconName } from './components/Icon'
import { TermsGate, termsAccepted } from './components/Legal'

type Tab = 'trackpad' | 'keyboard' | 'screen' | 'apps' | 'more'

const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: 'trackpad', label: 'Mouse', icon: 'pointer' },
  { id: 'keyboard', label: 'Tastiera', icon: 'keyboard' },
  { id: 'screen', label: 'Schermo', icon: 'monitor' },
  { id: 'apps', label: 'App', icon: 'apps' },
  { id: 'more', label: 'Altro', icon: 'menu' },
]

type Boot = 'checking' | 'paired' | 'unpaired' | 'offline' | 'untrusted'

export default function App() {
  const [boot, setBoot] = useState<Boot>('checking')
  const [accepted, setAccepted] = useState(termsAccepted)
  const [tab, setTab] = useState<Tab>('trackpad')
  const [status, setStatus] = useState<SocketStatus>('idle')

  const control = useMemo(() => new KursorSocket({ path: '/ws/control', onStatus: setStatus }), [])

  // A QR pairing link (#pair=...) always wins over an existing session.
  const pairCode = useMemo(() => {
    const m = location.hash.match(/pair=([A-Za-z0-9_-]{6,64})/)
    return m ? m[1] : null
  }, [])

  useEffect(() => {
    const off = onAuthChange((authed) => setBoot(authed ? 'paired' : 'unpaired'))
    if (pairCode) {
      setBoot('unpaired')
    } else {
      ;(async () => {
        if (isNative && !(await loadServer())) return setBoot('unpaired')
        try {
          setBoot((await refresh()) ? 'paired' : 'unpaired')
        } catch (err) {
          const code = err instanceof ApiError ? err.code : ''
          setBoot(code === 'pin_mismatch' ? 'untrusted' : code === 'network' ? 'offline' : 'unpaired')
        }
      })()
    }
    return () => {
      off()
    }
  }, [pairCode])

  useEffect(() => {
    if (boot !== 'paired') return
    control.start()
    const onVisible = () => {
      if (document.visibilityState === 'visible' && !control.isOpen) control.start()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      control.stop()
    }
  }, [boot, control])

  useEffect(() => {
    if (status === 'revoked') setBoot('unpaired')
    if (status === 'untrusted') setBoot('untrusted')
  }, [status])

  if (!accepted) return <TermsGate onAccept={() => setAccepted(true)} />
  if (boot === 'checking') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-gray-400">
        <img src="/icons/icon.svg" alt="" className="brand-glow h-14 w-14 animate-pulse" />
        Connessione al PC…
      </div>
    )
  }
  if (boot === 'offline') {
    return (
      <StateScreen
        icon="wifi-off"
        tone="muted"
        title="PC non raggiungibile"
        text="Controlla che PadLink sia aperto sul PC e che telefono e PC siano sulla stessa rete Wi-Fi."
      >
        <button className="btn-primary w-full" onClick={() => location.reload()}>
          Riprova
        </button>
        {isNative && (
          <button className="btn-ghost w-full" onClick={() => setBoot('unpaired')}>
            Cambia PC o associa di nuovo
          </button>
        )}
      </StateScreen>
    )
  }
  if (boot === 'untrusted') {
    return (
      <StateScreen
        icon="lock"
        tone="bad"
        title="Certificato del PC cambiato"
        text="Il PC ha presentato un certificato diverso da quello associato: la connessione è stata bloccata per proteggerti da intercettazioni. Se hai reinstallato PadLink sul PC, associa di nuovo."
      >
        <button className="btn-primary w-full" onClick={() => setBoot('unpaired')}>
          Associa di nuovo
        </button>
      </StateScreen>
    )
  }
  if (boot === 'unpaired') {
    return <PairScreen initialCode={pairCode} onPaired={() => setBoot('paired')} />
  }

  const pcHost = getServer()?.origin.replace(/^https:\/\//, '').replace(/:\d+$/, '') ?? location.hostname

  return (
    <div className="flex h-full flex-col">
      <header className="safe-top border-b border-white/5 bg-ink-950/95 px-4 backdrop-blur">
        <div className="flex h-14 items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <img src="/icons/icon.svg" alt="" className="brand-glow h-7 w-7" />
            <div className="min-w-0 leading-tight">
              <p className="font-semibold tracking-tight">PadLink</p>
              <p className="truncate text-[11px] text-muted">{pcHost}</p>
            </div>
          </div>
          <StatusPill status={status} />
        </div>
      </header>

      <StatusBanner status={status} />

      <main className="relative min-h-0 flex-1">
        {tab === 'trackpad' && <Trackpad socket={control} full />}
        {tab === 'keyboard' && <KeyboardPanel socket={control} />}
        {tab === 'screen' && <ScreenPanel control={control} />}
        {tab === 'apps' && <AppsPanel onShowScreen={() => setTab('screen')} />}
        {tab === 'more' && <MorePanel onLoggedOut={() => setBoot('unpaired')} />}
      </main>

      <nav className="safe-bottom grid grid-cols-5 border-t border-white/5 bg-ink-950 px-1">
        {TABS.map((t) => {
          const active = tab === t.id
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              aria-current={active ? 'page' : undefined}
              className={`flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors ${
                active ? 'text-gray-50' : 'text-muted'
              }`}
            >
              <span
                className={`flex h-7 w-12 items-center justify-center rounded-full transition-colors ${
                  active ? 'bg-accent/20 text-accent-2' : ''
                }`}
              >
                <Icon name={t.icon} className="h-5 w-5" />
              </span>
              {t.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}

/** Full-screen message with icon, used for offline / untrusted states. */
function StateScreen(props: {
  icon: IconName
  tone: 'muted' | 'bad'
  title: string
  text: string
  children: React.ReactNode
}) {
  return (
    <div className="safe-top safe-bottom flex h-full flex-col items-center justify-center gap-6 p-8 text-center">
      <span
        className={`flex h-20 w-20 items-center justify-center rounded-3xl ${
          props.tone === 'bad' ? 'bg-red-500/15 text-red-400' : 'bg-ink-800 text-muted'
        }`}
      >
        <Icon name={props.icon} className="h-10 w-10" />
      </span>
      <div className="flex max-w-xs flex-col gap-2">
        <h1 className="text-xl font-semibold">{props.title}</h1>
        <p className="text-sm text-muted">{props.text}</p>
      </div>
      <div className="flex w-full max-w-xs flex-col gap-2">{props.children}</div>
    </div>
  )
}

const STATUS: Record<SocketStatus, { dot: string; label: string }> = {
  idle: { dot: 'bg-gray-500', label: 'Inattivo' },
  connecting: { dot: 'bg-warn animate-pulse', label: 'Connessione' },
  open: { dot: 'bg-ok', label: 'Connesso' },
  offline: { dot: 'bg-bad animate-pulse', label: 'Offline' },
  paused: { dot: 'bg-warn', label: 'In pausa' },
  revoked: { dot: 'bg-bad', label: 'Revocato' },
  untrusted: { dot: 'bg-bad', label: 'Non fidato' },
}

function StatusPill({ status }: { status: SocketStatus }) {
  const s = STATUS[status]
  return (
    <span className="chip shrink-0 border border-white/5 bg-ink-900 px-3 py-1 text-xs text-gray-300">
      <span className={`h-2 w-2 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

/** Explains non-connected states right under the header, instead of a cryptic dot. */
function StatusBanner({ status }: { status: SocketStatus }) {
  const msg: Partial<Record<SocketStatus, [string, string]>> = {
    offline: ['bg-red-500/10 text-red-300', 'PC non raggiungibile: riprovo in automatico…'],
    paused: ['bg-amber-500/10 text-amber-300', 'Controllo messo in pausa dal PC. Riprende da solo quando lo riattivi.'],
  }
  const m = msg[status]
  if (!m) return null
  return <div className={`px-4 py-2 text-center text-xs ${m[0]}`}>{m[1]}</div>
}
