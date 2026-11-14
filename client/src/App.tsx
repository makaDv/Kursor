import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, onAuthChange, refresh } from './lib/api'
import { t, useLang } from './lib/i18n'
import { KursorNative } from './lib/native'
import {
  canCaptureVolumeKeys,
  canWakeOnLan,
  confirmWithBiometrics,
  launchTab,
  noteGoodSession,
  noteSessionError,
  rediscover,
  wakePc,
} from './lib/pc'
import { getServer, isNative, listServers, loadServer, updateCurrentServer } from './lib/platform'
import { usePrefs } from './lib/settings'
import { KursorSocket, type SocketStatus } from './lib/socket'
import PairScreen from './components/PairScreen'
import Trackpad from './components/Trackpad'
import KeyboardPanel from './components/KeyboardPanel'
import ScreenPanel from './components/ScreenPanel'
import MorePanel from './components/MorePanel'
import AppsPanel from './components/AppsPanel'
import Onboarding, { onboardingDone } from './components/Onboarding'
import Help from './components/Help'
import PcSwitcher from './components/PcSwitcher'
import { Icon, type IconName } from './components/Icon'
import { TermsGate, termsAccepted } from './components/Legal'

type Tab = 'trackpad' | 'keyboard' | 'screen' | 'apps' | 'more'

/** What this phone may do on the PC (set in the PC window; mouse/keyboard always allowed). */
export interface Perms {
  screen: boolean
  apps: boolean
  clipboard: boolean
  power: boolean
}
const ALL_PERMS: Perms = { screen: true, apps: true, clipboard: true, power: true }

const TABS: { id: Tab; label: string; icon: IconName; perm?: keyof Perms }[] = [
  { id: 'trackpad', label: 'Mouse', icon: 'pointer' },
  { id: 'keyboard', label: 'Tastiera', icon: 'keyboard' },
  { id: 'screen', label: 'Schermo', icon: 'monitor', perm: 'screen' },
  { id: 'apps', label: 'App', icon: 'apps', perm: 'apps' },
  { id: 'more', label: 'Altro', icon: 'menu' },
]

type Boot = 'checking' | 'paired' | 'unpaired' | 'offline' | 'untrusted'

const RELOCK_AFTER_MS = 60_000

export default function App() {
  useLang()
  const [prefs] = usePrefs()
  const [boot, setBoot] = useState<Boot>('checking')
  const [accepted, setAccepted] = useState(termsAccepted)
  const [onboarded, setOnboarded] = useState(onboardingDone)
  const [locked, setLocked] = useState(() => isNative && prefs.biometricLock)
  const [tab, setTab] = useState<Tab>('trackpad')
  const [status, setStatus] = useState<SocketStatus>('idle')
  const [perms, setPerms] = useState<Perms>(ALL_PERMS)
  const [sheet, setSheet] = useState<'help' | 'pcs' | null>(null)
  const [adding, setAdding] = useState(false)
  const [, bump] = useState(0) // re-render after the current PC's details change

  const onMessage = useCallback((msg: Record<string, unknown>) => {
    if (msg.t !== 'ready') return
    if (msg.perms && typeof msg.perms === 'object') setPerms({ ...ALL_PERMS, ...(msg.perms as Partial<Perms>) })
    const pc = msg.pc as { name?: string; mac?: string | null } | undefined
    if (pc && isNative) void updateCurrentServer({ name: pc.name || undefined, mac: pc.mac ?? null }).then(() => bump((n) => n + 1))
  }, [])

  const control = useMemo(() => new KursorSocket({ path: '/ws/control', onStatus: setStatus, onMessage }), [onMessage])

  // A QR pairing link (#pair=...) always wins over an existing session.
  const pairCode = useMemo(() => {
    const m = location.hash.match(/pair=([A-Za-z0-9_-]{6,64})/)
    return m ? m[1] : null
  }, [])

  const connect = useCallback(async () => {
    setBoot('checking')
    if (isNative && !(await loadServer())) return setBoot('unpaired')
    const attempt = async () => {
      try {
        setBoot((await refresh()) ? 'paired' : 'unpaired')
        return true
      } catch (err) {
        const code = err instanceof ApiError ? err.code : ''
        if (code === 'pin_mismatch') {
          setBoot('untrusted')
          return true
        }
        return code !== 'network' ? (setBoot('unpaired'), true) : false
      }
    }
    if (await attempt()) return
    // Unreachable: the PC may have a new IP address. Look for it on the LAN once.
    if ((await rediscover()) && (await attempt())) return
    setBoot('offline')
  }, [])

  useEffect(() => {
    const off = onAuthChange((authed) => setBoot(authed ? 'paired' : 'unpaired'))
    if (pairCode) setBoot('unpaired')
    else void connect()
    return () => {
      off()
    }
  }, [pairCode, connect])

  useEffect(() => {
    if (boot !== 'paired' || locked) return
    control.start()
    const onVisible = () => {
      if (document.visibilityState === 'visible' && !control.isOpen) control.start()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      control.stop()
    }
  }, [boot, control, locked])

  useEffect(() => {
    if (status === 'revoked') setBoot('unpaired')
    if (status === 'untrusted') setBoot('untrusted')
    if (status === 'open') noteGoodSession()
    if (status === 'offline' || status === 'denied') noteSessionError()
  }, [status])

  // Biometric lock: on start and when coming back after a minute in the background.
  const hiddenAt = useRef(0)
  useEffect(() => {
    if (!isNative) return
    const onVis = () => {
      if (document.visibilityState === 'hidden') hiddenAt.current = Date.now()
      else if (prefs.biometricLock && hiddenAt.current && Date.now() - hiddenAt.current > RELOCK_AFTER_MS) setLocked(true)
    }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [prefs.biometricLock])

  // Launcher shortcuts / iOS quick actions open a specific tab.
  useEffect(() => {
    if (!isNative) return
    const go = (name: string | null) => {
      if (name && TABS.some((x) => x.id === name)) setTab(name as Tab)
    }
    void launchTab().then(go)
    const h = KursorNative.addListener('launchTab', (ev) => go(ev.tab))
    return () => void h.then((x) => x.remove())
  }, [])

  // Android: phone volume keys control the PC volume while the app is in front.
  useEffect(() => {
    if (!canCaptureVolumeKeys) return
    const on = prefs.volumeKeys && boot === 'paired' && !locked
    void KursorNative.setVolumeKeyCapture({ enabled: on }).catch(() => undefined)
    if (!on) return
    const h = KursorNative.addListener('volumeKey', (ev) => control.send({ t: 'keys', k: [ev.key === 'up' ? 'volume_up' : 'volume_down'] }))
    return () => {
      void h.then((x) => x.remove())
      void KursorNative.setVolumeKeyCapture({ enabled: false }).catch(() => undefined)
    }
  }, [prefs.volumeKeys, boot, locked, control])

  // A tab the device is no longer allowed to use falls back to the trackpad.
  useEffect(() => {
    const def = TABS.find((x) => x.id === tab)
    if (def?.perm && !perms[def.perm]) setTab('trackpad')
  }, [perms, tab])

  if (!accepted) return <TermsGate onAccept={() => setAccepted(true)} />
  if (!onboarded && !getServer() && !pairCode) return <Onboarding onDone={() => setOnboarded(true)} />
  if (locked) return <LockScreen onUnlock={() => setLocked(false)} />

  if (adding) {
    return (
      <PairScreen
        initialCode={null}
        onCancel={() => setAdding(false)}
        onPaired={() => {
          setAdding(false)
          control.stop()
          void connect()
        }}
      />
    )
  }

  if (boot === 'checking') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-muted">
        <img src="/icons/icon.svg" alt="" className="brand-glow h-14 w-14 animate-pulse" />
        {t('Connessione al PC…')}
      </div>
    )
  }
  if (boot === 'offline') return <OfflineScreen onRetry={() => void connect()} onPair={() => setBoot('unpaired')} onHelp={() => setSheet('help')} sheet={sheet} closeSheet={() => setSheet(null)} />
  if (boot === 'untrusted') {
    return (
      <StateScreen
        icon="lock"
        tone="bad"
        title={t('Certificato del PC cambiato')}
        text={t('Il PC ha presentato un certificato diverso da quello associato: la connessione è stata bloccata per proteggerti da intercettazioni. Se hai reinstallato PadLink sul PC, associa di nuovo.')}
      >
        <button className="btn-primary w-full" onClick={() => setBoot('unpaired')}>
          {t('Associa di nuovo')}
        </button>
      </StateScreen>
    )
  }
  if (boot === 'unpaired') {
    return <PairScreen initialCode={pairCode} onPaired={() => setBoot('paired')} onCancel={listServers().length > 0 && isNative ? () => void connect() : undefined} />
  }

  const cfg = getServer()
  const pcHost = cfg?.name || cfg?.origin.replace(/^https:\/\//, '').replace(/:\d+$/, '') || location.hostname
  const tabs = TABS.filter((x) => !x.perm || perms[x.perm])

  return (
    <div className="flex h-full flex-col">
      <header className="safe-top border-b border-white/5 bg-ink-950/95 px-4 backdrop-blur">
        <div className="flex h-14 items-center justify-between gap-3">
          <button
            className="flex min-w-0 items-center gap-2.5 text-left"
            onClick={() => isNative && setSheet('pcs')}
            aria-label={isNative ? t('Cambia PC') : undefined}
          >
            <img src="/icons/icon.svg" alt="" className="brand-glow h-7 w-7" />
            <span className="min-w-0 leading-tight">
              <span className="block font-semibold tracking-tight">PadLink</span>
              <span className="flex items-center gap-1 truncate text-[11px] text-muted">
                {pcHost}
                {isNative && <span aria-hidden="true">▾</span>}
              </span>
            </span>
          </button>
          <div className="flex items-center gap-2">
            <button className="key h-9 w-9 rounded-full px-0" onClick={() => setSheet('help')} aria-label={t('Aiuto')}>
              ?
            </button>
            <StatusPill status={status} />
          </div>
        </div>
      </header>

      <StatusBanner status={status} />

      <main className="relative min-h-0 flex-1">
        {tab === 'trackpad' && <Trackpad socket={control} full />}
        {tab === 'keyboard' && <KeyboardPanel socket={control} canClipboard={perms.clipboard} />}
        {tab === 'screen' && <ScreenPanel control={control} />}
        {tab === 'apps' && <AppsPanel onShowScreen={() => setTab('screen')} canPower={perms.power} canScreen={perms.screen} />}
        {tab === 'more' && (
          <MorePanel onLoggedOut={() => setBoot('unpaired')} canPower={perms.power} onHelp={() => setSheet('help')} />
        )}
      </main>

      <nav className={`safe-bottom grid border-t border-white/5 bg-ink-950 px-1`} style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)` }}>
        {tabs.map((x) => {
          const active = tab === x.id
          return (
            <button
              key={x.id}
              onClick={() => setTab(x.id)}
              aria-current={active ? 'page' : undefined}
              className={`flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors ${
                active ? 'text-gray-50' : 'text-muted'
              }`}
            >
              <span className={`flex h-7 w-12 items-center justify-center rounded-full transition-colors ${active ? 'bg-accent/20 text-accent-2' : ''}`}>
                <Icon name={x.icon} className="h-5 w-5" />
              </span>
              {t(x.label)}
            </button>
          )
        })}
      </nav>

      {sheet === 'help' && <Help onClose={() => setSheet(null)} />}
      {sheet === 'pcs' && (
        <PcSwitcher
          onClose={() => setSheet(null)}
          onAdd={() => {
            setSheet(null)
            setAdding(true)
          }}
          onSwitched={() => {
            setSheet(null)
            control.stop()
            setPerms(ALL_PERMS)
            void connect()
          }}
        />
      )}
    </div>
  )
}

function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const [failed, setFailed] = useState(false)
  const unlock = useCallback(async () => {
    setFailed(false)
    if (await confirmWithBiometrics(t('Sblocca PadLink'), 'unlock')) onUnlock()
    else setFailed(true)
  }, [onUnlock])
  useEffect(() => {
    void unlock()
  }, [unlock])
  return (
    <StateScreen icon="lock" tone="muted" title={t('PadLink è bloccato')} text={failed ? t('Sblocco non riuscito. Riprova.') : t('Usa impronta, volto o PIN del telefono per continuare.')}>
      <button className="btn-primary w-full" onClick={() => void unlock()}>
        {t('Sblocca')}
      </button>
    </StateScreen>
  )
}

function OfflineScreen(props: {
  onRetry: () => void
  onPair: () => void
  onHelp: () => void
  sheet: 'help' | 'pcs' | null
  closeSheet: () => void
}) {
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const cfg = getServer()
  const canWake = canWakeOnLan && !!cfg?.mac
  return (
    <StateScreen
      icon="wifi-off"
      tone="muted"
      title={t('PC non raggiungibile')}
      text={t('Il PC potrebbe essere spento, in sospensione o su un’altra rete Wi-Fi. Controlla che PadLink sia aperto sul PC.')}
    >
      <button className="btn-primary w-full" disabled={busy} onClick={props.onRetry}>
        {t('Riprova')}
      </button>
      {isNative && (
        <button
          className="btn-secondary w-full"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            setNote(t('Cerco il PC sulla rete…'))
            const moved = await rediscover()
            setBusy(false)
            if (moved) props.onRetry()
            else setNote(t('PC non trovato su questa rete. È acceso e con PadLink aperto?'))
          }}
        >
          {t('Cerca il PC in rete')}
        </button>
      )}
      {canWake && (
        <button
          className="btn-secondary w-full"
          disabled={busy}
          onClick={async () => {
            const ok = await wakePc()
            setNote(ok ? t('Segnale di accensione inviato. Attendi qualche secondo e riprova.') : t('Impossibile inviare il segnale di accensione.'))
            if (ok) window.setTimeout(props.onRetry, 15_000)
          }}
        >
          {t('Accendi PC')}
        </button>
      )}
      {note && <p className="text-center text-xs text-muted">{note}</p>}
      {isNative && (
        <button className="btn-ghost w-full" onClick={props.onPair}>
          {t('Cambia PC o associa di nuovo')}
        </button>
      )}
      <button className="btn-ghost w-full" onClick={props.onHelp}>
        {t('Aiuto')}
      </button>
      {props.sheet === 'help' && <Help onClose={props.closeSheet} />}
    </StateScreen>
  )
}

/** Full-screen message with icon, used for offline / untrusted / locked states. */
function StateScreen(props: { icon: IconName; tone: 'muted' | 'bad'; title: string; text: string; children: React.ReactNode }) {
  return (
    <div className="safe-top safe-bottom flex h-full flex-col items-center justify-center gap-6 overflow-y-auto p-8 text-center">
      <span className={`flex h-20 w-20 items-center justify-center rounded-3xl ${props.tone === 'bad' ? 'bg-red-500/15 text-red-400' : 'bg-ink-800 text-muted'}`}>
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
  approval: { dot: 'bg-warn animate-pulse', label: 'In attesa' },
  denied: { dot: 'bg-bad', label: 'Rifiutato' },
  forbidden: { dot: 'bg-bad', label: 'Non consentito' },
  revoked: { dot: 'bg-bad', label: 'Revocato' },
  untrusted: { dot: 'bg-bad', label: 'Non fidato' },
}

function StatusPill({ status }: { status: SocketStatus }) {
  const s = STATUS[status]
  return (
    <span className="chip shrink-0 border border-white/5 bg-ink-900 px-3 py-1 text-xs text-gray-300" role="status">
      <span className={`h-2 w-2 rounded-full ${s.dot}`} />
      {t(s.label)}
    </span>
  )
}

/** Explains non-connected states right under the header, instead of a cryptic dot. */
function StatusBanner({ status }: { status: SocketStatus }) {
  const msg: Partial<Record<SocketStatus, [string, string]>> = {
    offline: ['bg-red-500/10 text-red-300', 'PC non raggiungibile: riprovo e lo cerco in rete in automatico…'],
    paused: ['bg-amber-500/10 text-amber-300', 'Controllo messo in pausa dal PC. Riprende da solo quando lo riattivi.'],
    approval: ['bg-amber-500/10 text-amber-300', 'Conferma la connessione sul PC: è comparsa una richiesta nella finestra di PadLink.'],
    denied: ['bg-red-500/10 text-red-300', 'La connessione è stata rifiutata sul PC.'],
  }
  const m = msg[status]
  if (!m) return null
  return (
    <div className={`px-4 py-2 text-center text-xs ${m[0]}`} role="status">
      {t(m[1])}
    </div>
  )
}
