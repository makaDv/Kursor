import { useEffect, useRef, useState } from 'react'
import { ApiError, pair } from '../lib/api'
import { KursorNative } from '../lib/native'
import {
  apiUrl,
  getServer,
  isNative,
  LAN_ONLY,
  normalizeServer,
  parsePairingLink,
  setServer,
  verificationCode,
  type ServerConfig,
} from '../lib/platform'
import { PrivacyNote } from './Legal'

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

/** Pending manual pairing waiting for the user to compare the verification code. */
interface Verify {
  cfg: ServerConfig
  secret: string
}

export default function PairScreen({ initialCode, onPaired }: { initialCode: string | null; onPaired: () => void }) {
  const [pin, setPin] = useState('')
  const [name, setName] = useState(defaultDeviceName)
  const [server, setServerInput] = useState(() => getServer()?.origin.replace(/^https:\/\//, '') ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [verify, setVerify] = useState<Verify | null>(null)
  const autoTried = useRef(false)

  const doPair = async (secret: string, cfg?: ServerConfig) => {
    setBusy(true)
    setError(null)
    try {
      if (cfg) await setServer(cfg)
      await pair(secret, name.trim() || defaultDeviceName())
      onPaired()
    } catch (err) {
      setError(describe(err))
    } finally {
      setBusy(false)
    }
  }

  /**
   * Native: work out how to trust the PC before sending anything secret.
   * - pin from the QR code: trusted directly (the QR is the out-of-band channel);
   * - publicly trusted certificate (tunnel): system trust, no pin;
   * - otherwise: show the CA fingerprint as a verification code to compare on the PC.
   */
  const nativePair = async (origin: string, secret: string, qrPin: string | null) => {
    if (qrPin) return doPair(secret, { origin, pin: qrPin })
    const saved = getServer()
    setBusy(true)
    setError(null)
    try {
      const probe = await KursorNative.probe({ url: origin })
      if (probe.publiclyTrusted) {
        setBusy(false)
        return doPair(secret, { origin, pin: null })
      }
      // Same PC as before (unchanged certificate): no need to compare the code again.
      if (probe.fingerprint && saved?.origin === origin && saved.pin === probe.fingerprint) {
        setBusy(false)
        return doPair(secret, saved)
      }
      if (!probe.fingerprint) {
        setError('Il PC non presenta un certificato PadLink valido.')
      } else {
        setVerify({ cfg: { origin, pin: probe.fingerprint }, secret })
      }
    } catch {
      setError('PC non raggiungibile. Controlla indirizzo e rete Wi-Fi.')
    } finally {
      setBusy(false)
    }
  }

  const submitManual = (secret: string) => {
    if (!isNative) return void doPair(secret)
    const origin = normalizeServer(server)
    if (!origin) {
      setError(
        LAN_ONLY
          ? 'Indirizzo non valido. Su iPhone PadLink si collega solo a PC sulla stessa rete Wi-Fi (es. 192.168.1.10).'
          : 'Indirizzo del PC non valido (es. 192.168.1.10:8443)',
      )
      return
    }
    void nativePair(origin, secret, null)
  }

  const handleLink = (text: string): boolean => {
    const link = parsePairingLink(text)
    if (!link) return false
    setServerInput(link.origin.replace(/^https:\/\//, ''))
    void nativePair(link.origin, link.code, link.pin)
    return true
  }

  const scan = async () => {
    setError(null)
    try {
      const { value } = await KursorNative.scanQr()
      if (value && !handleLink(value)) setError('Questo QR non è un codice di associazione PadLink.')
    } catch {
      setError('Fotocamera non disponibile. Inserisci indirizzo e PIN a mano.')
    }
  }

  // PWA QR flow: the high-entropy code arrives in the URL fragment, which browsers
  // never send to the server. Remove it from the address bar right away.
  useEffect(() => {
    if (!initialCode || autoTried.current) return
    autoTried.current = true
    history.replaceState(null, '', location.pathname)
    void doPair(initialCode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCode])

  const digits = pin.replace(/\D/g, '').slice(0, 6)

  if (verify) {
    return (
      <div className="safe-top safe-bottom flex h-full flex-col items-center justify-center gap-6 overflow-y-auto px-6 text-center">
        <h1 className="text-xl font-semibold">Verifica il PC</h1>
        <p className="max-w-xs text-sm text-gray-400">
          Controlla che nella finestra di PadLink sul PC compaia <b>esattamente</b> questo codice di verifica:
        </p>
        <p className="card px-5 py-4 font-mono text-2xl tracking-wider text-accent-2">
          {verificationCode(verify.cfg.pin!)}
        </p>
        <p className="max-w-xs text-xs text-gray-500">
          Se il codice è diverso, qualcuno sulla rete potrebbe intercettare la connessione: non proseguire.
        </p>
        <div className="flex w-full max-w-xs flex-col gap-3">
          <button
            className="btn-primary"
            disabled={busy}
            onClick={() => {
              const v = verify
              setVerify(null)
              void doPair(v.secret, v.cfg)
            }}
          >
            Il codice corrisponde
          </button>
          <button className="btn-secondary" onClick={() => setVerify(null)}>
            Annulla
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="safe-top safe-bottom flex h-full flex-col items-center justify-center gap-8 overflow-y-auto px-6 py-6">
      <div className="flex flex-col items-center gap-3">
        <img src="/icons/icon.svg" alt="" className="brand-glow h-16 w-16" />
        <h1 className="text-2xl font-semibold">Associa questo dispositivo</h1>
        <p className="max-w-xs text-center text-sm text-gray-400">
          {isNative
            ? 'Apri PadLink sul PC e inquadra il QR code, oppure inserisci indirizzo e PIN.'
            : 'Inserisci il PIN a 6 cifre mostrato sul PC, oppure inquadra il QR code.'}
        </p>
      </div>

      {isNative && (
        <button
          onClick={() => void scan()}
          disabled={busy}
          className="btn-primary w-full max-w-xs"
        >
          Scansiona il QR code
        </button>
      )}
      {isNative && (
        <div className="flex w-full max-w-xs items-center gap-3 text-[11px] font-semibold tracking-wider text-muted uppercase">
          <span className="h-px flex-1 bg-white/10" />
          oppure con PIN
          <span className="h-px flex-1 bg-white/10" />
        </div>
      )}

      <form
        className="flex w-full max-w-xs flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (digits.length === 6) submitManual(digits)
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
              onChange={(e) => {
                // Only a paste (several characters at once) is treated as a pairing link,
                // never a half-typed one.
                const pasted = e.target.value.length - server.length > 1
                if (!(pasted && handleLink(e.target.value))) setServerInput(e.target.value)
              }}
              className="field font-mono"
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
          className="rounded-2xl border border-white/5 bg-ink-800 py-4 text-center font-mono text-3xl tracking-[0.5em] outline-none focus:border-accent focus:ring-2 focus:ring-accent/40"
          aria-label="PIN"
        />
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          Nome dispositivo
          <input
            value={name}
            maxLength={64}
            onChange={(e) => setName(e.target.value)}
            className="field"
          />
        </label>
        <button
          type="submit"
          disabled={busy || digits.length !== 6}
          className={isNative ? 'btn-secondary' : 'btn-primary'}
        >
          {busy ? 'Verifica…' : 'Associa con PIN'}
        </button>
        {error && <p className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-center text-sm text-red-300">{error}</p>}
      </form>

      {!isNative && (
        <p className="max-w-xs text-center text-xs text-gray-500">
          Prima volta? Scarica e installa il{' '}
          <a href={apiUrl('/ca.crt')} target="_blank" rel="noreferrer" className="text-accent-2 underline">
            certificato del PC
          </a>{' '}
          per una connessione cifrata e fidata (istruzioni nel README).
        </p>
      )}
      <PrivacyNote />
    </div>
  )
}
