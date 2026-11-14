import { useEffect, useRef, useState } from 'react'
import { ApiError, pair } from '../lib/api'
import { apiUrl, getServer, isNative, normalizeServer, setServer } from '../lib/platform'

function defaultDeviceName() {
  const ua = navigator.userAgent
  if (/iPhone/.test(ua)) return 'iPhone'
  if (/iPad/.test(ua)) return 'iPad'
  if (/Android/.test(ua)) return 'Android'
  return 'Browser'
}

function describe(err: unknown): string {
  if (!(err instanceof ApiError)) return 'Errore imprevisto'
  if (err.code === 'locked_out' && err.retryAfter) {
    const min = Math.ceil(err.retryAfter / 60)
    return `Troppi tentativi falliti. Bloccato per ${min} minut${min === 1 ? 'o' : 'i'}.`
  }
  if (err.code === 'invalid_code' && err.remainingAttempts !== undefined) {
    return `Codice non valido. Tentativi rimasti: ${err.remainingAttempts}.`
  }
  return err.message
}

export default function PairScreen({ initialCode, onPaired }: { initialCode: string | null; onPaired: () => void }) {
  const [pin, setPin] = useState('')
  const [name, setName] = useState(defaultDeviceName)
  const [server, setServerInput] = useState(() => getServer()?.replace(/^https:\/\//, '') ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const autoTried = useRef(false)

  const submit = async (secret: string, serverOverride?: string) => {
    if (isNative) {
      const origin = normalizeServer(serverOverride ?? server)
      if (!origin) {
        setError('Indirizzo del PC non valido (es. 192.168.1.10:8443)')
        return
      }
      setServer(origin)
    }
    setBusy(true)
    setError(null)
    try {
      await pair(secret, name.trim() || defaultDeviceName())
      onPaired()
    } catch (err) {
      setError(describe(err))
    } finally {
      setBusy(false)
    }
  }

  // QR flow: the high-entropy code arrives in the URL fragment, which browsers
  // never send to the server. Remove it from the address bar right away.
  useEffect(() => {
    if (!initialCode || autoTried.current) return
    autoTried.current = true
    history.replaceState(null, '', location.pathname)
    void submit(initialCode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCode])

  const digits = pin.replace(/\D/g, '').slice(0, 6)

  // App: pasting the QR link (https://IP:8443/#pair=CODE) fills everything in.
  const onServerChange = (value: string) => {
    const m = value.match(/^(https:\/\/[^/#\s]+)\/?#pair=([A-Za-z0-9_-]{6,64})/)
    if (m) {
      setServerInput(m[1].replace(/^https:\/\//, ''))
      void submit(m[2], m[1])
      return
    }
    setServerInput(value)
  }

  return (
    <div className="safe-top safe-bottom flex h-full flex-col items-center justify-center gap-8 overflow-y-auto px-6">
      <div className="flex flex-col items-center gap-3">
        <img src="/icons/icon.svg" alt="" className="h-16 w-16" />
        <h1 className="text-2xl font-semibold">Associa questo dispositivo</h1>
        <p className="max-w-xs text-center text-sm text-gray-400">
          {isNative
            ? 'Inserisci l’indirizzo e il PIN mostrati nel terminale del PC (oppure incolla il link del QR).'
            : 'Inserisci il PIN a 6 cifre mostrato nel terminale del PC, oppure inquadra il QR code.'}
        </p>
      </div>

      <form
        className="flex w-full max-w-xs flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (digits.length === 6) void submit(digits)
        }}
      >
        {isNative && (
          <label className="flex flex-col gap-1 text-xs text-gray-400">
            Indirizzo del PC
            <input
              value={server}
              inputMode="url"
              autoCapitalize="off"
              autoCorrect="off"
              placeholder="192.168.1.10:8443"
              onChange={(e) => onServerChange(e.target.value)}
              className="rounded-xl bg-ink-800 px-3 py-3 font-mono text-base text-gray-100 outline-none focus:ring-2 focus:ring-accent"
            />
          </label>
        )}
        <input
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]*"
          maxLength={7}
          placeholder="000000"
          value={digits}
          onChange={(e) => setPin(e.target.value)}
          className="rounded-2xl bg-ink-800 py-4 text-center font-mono text-3xl tracking-[0.5em] outline-none focus:ring-2 focus:ring-accent"
          aria-label="PIN"
        />
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          Nome dispositivo
          <input
            value={name}
            maxLength={64}
            onChange={(e) => setName(e.target.value)}
            className="rounded-xl bg-ink-800 px-3 py-3 text-base text-gray-100 outline-none focus:ring-2 focus:ring-accent"
          />
        </label>
        <button
          type="submit"
          disabled={busy || digits.length !== 6}
          className="rounded-2xl bg-accent py-4 font-semibold text-white disabled:opacity-40"
        >
          {busy ? 'Verifica…' : 'Associa'}
        </button>
        {error && <p className="rounded-xl bg-red-500/15 p-3 text-center text-sm text-red-300">{error}</p>}
      </form>

      <p className="max-w-xs text-center text-xs text-gray-500">
        Prima volta? Scarica e installa il{' '}
        <a href={apiUrl('/ca.crt')} target="_blank" rel="noreferrer" className="text-accent-2 underline">
          certificato del PC
        </a>{' '}
        per una connessione cifrata e fidata (istruzioni nel README).
      </p>
    </div>
  )
}
