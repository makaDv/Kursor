import { useEffect, useMemo, useState } from 'react'
import { ApiError, onAuthChange, refresh } from './lib/api'
import { isNative, loadServer } from './lib/platform'
import { KursorSocket, type SocketStatus } from './lib/socket'
import PairScreen from './components/PairScreen'
import Trackpad from './components/Trackpad'
import KeyboardPanel from './components/KeyboardPanel'
import ScreenPanel from './components/ScreenPanel'
import SystemPanel from './components/SystemPanel'
import MorePanel from './components/MorePanel'
import { Icon, type IconName } from './components/Icon'

type Tab = 'trackpad' | 'keyboard' | 'screen' | 'system' | 'more'

const TABS: { id: Tab; label: string; icon: IconName }[] = [
  { id: 'trackpad', label: 'Trackpad', icon: 'pointer' },
  { id: 'keyboard', label: 'Tastiera', icon: 'keyboard' },
  { id: 'screen', label: 'Schermo', icon: 'monitor' },
  { id: 'system', label: 'Sistema', icon: 'power' },
  { id: 'more', label: 'Altro', icon: 'menu' },
]

type Boot = 'checking' | 'paired' | 'unpaired' | 'offline' | 'untrusted'

export default function App() {
  const [boot, setBoot] = useState<Boot>('checking')
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

  if (boot === 'checking') {
    return <div className="flex h-full items-center justify-center text-gray-400">Connessione…</div>
  }
  if (boot === 'offline') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
        <Icon name="wifi-off" className="h-12 w-12 text-gray-500" />
        <p className="text-gray-300">PC non raggiungibile. Verifica che Kursor sia avviato e che tu sia sulla stessa rete.</p>
        <button className="key px-6" onClick={() => location.reload()}>
          Riprova
        </button>
        {isNative && (
          <button className="text-sm text-accent-2" onClick={() => setBoot('unpaired')}>
            Cambia PC / associa di nuovo
          </button>
        )}
      </div>
    )
  }
  if (boot === 'untrusted') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
        <Icon name="lock" className="h-12 w-12 text-red-400" />
        <h1 className="text-lg font-semibold">Certificato del PC cambiato</h1>
        <p className="max-w-xs text-sm text-gray-300">
          Il PC ha presentato un certificato diverso da quello associato. La connessione è stata bloccata per proteggerti
          da intercettazioni. Se hai reinstallato Kursor o rigenerato i certificati sul PC, associa di nuovo.
        </p>
        <button className="key px-6" onClick={() => setBoot('unpaired')}>
          Associa di nuovo
        </button>
      </div>
    )
  }
  if (boot === 'unpaired') {
    return <PairScreen initialCode={pairCode} onPaired={() => setBoot('paired')} />
  }

  return (
    <div className="flex h-full flex-col">
      <header className="safe-top flex items-center justify-between border-b border-ink-800 bg-ink-950 px-4">
        <div className="flex h-12 items-center gap-2 font-semibold tracking-tight">
          <img src="/icons/icon.svg" alt="" className="h-6 w-6" />
          Kursor
        </div>
        <StatusPill status={status} />
      </header>

      <main className="relative min-h-0 flex-1">
        {tab === 'trackpad' && <Trackpad socket={control} full />}
        {tab === 'keyboard' && <KeyboardPanel socket={control} />}
        {tab === 'screen' && <ScreenPanel control={control} />}
        {tab === 'system' && <SystemPanel />}
        {tab === 'more' && <MorePanel onLoggedOut={() => setBoot('unpaired')} />}
      </main>

      <nav className="safe-bottom grid grid-cols-5 border-t border-ink-800 bg-ink-950">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] ${
              tab === t.id ? 'text-accent-2' : 'text-gray-400'
            }`}
          >
            <Icon name={t.icon} className="h-5 w-5" />
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  )
}

function StatusPill({ status }: { status: SocketStatus }) {
  const map: Record<SocketStatus, [string, string]> = {
    idle: ['bg-gray-500', 'Inattivo'],
    connecting: ['bg-amber-400 animate-pulse', 'Connessione'],
    open: ['bg-emerald-400', 'Connesso'],
    offline: ['bg-red-500 animate-pulse', 'Offline'],
    revoked: ['bg-red-500', 'Revocato'],
    untrusted: ['bg-red-500', 'Non fidato'],
  }
  const [dot, label] = map[status]
  return (
    <span className="flex items-center gap-2 rounded-full bg-ink-800 px-3 py-1 text-xs text-gray-300">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {label}
    </span>
  )
}
