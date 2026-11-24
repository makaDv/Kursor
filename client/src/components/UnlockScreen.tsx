import { useState } from 'react'
import { ApiError, refresh, setSessionPassword } from '../lib/api'
import { t, useLang } from '../lib/i18n'
import { getServer } from '../lib/platform'

function describe(err: unknown): string {
  if (!(err instanceof ApiError)) return t('Errore imprevisto')
  if (err.code === 'locked_out' && err.retryAfter) {
    const min = Math.ceil(err.retryAfter / 60)
    return min === 1 ? t('Troppi tentativi falliti. Bloccato per 1 minuto.') : t('Troppi tentativi falliti. Bloccato per {n} minuti.', { n: min })
  }
  if (err.code === 'invalid_password' && err.remainingAttempts !== undefined) {
    return t('Password errata. Tentativi rimasti: {n}.', { n: err.remainingAttempts })
  }
  return err.message
}

/**
 * Asks the PC password on every app start (and after a while in the background).
 * The password is checked by the PC while exchanging the refresh token and is kept
 * only in memory.
 */
export default function UnlockScreen({ onUnlocked, onRepair }: { onUnlocked: () => void; onRepair: () => void }) {
  useLang()
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cfg = getServer()
  const pcName = cfg?.name || cfg?.origin.replace(/^https:\/\//, '').replace(/:\d+$/, '') || location.hostname

  const submit = async () => {
    if (!password) return
    setBusy(true)
    setError(null)
    setSessionPassword(password)
    try {
      if (await refresh()) {
        setPassword('')
        onUnlocked()
      } else {
        // The session itself is gone (revoked or expired): pair again.
        onRepair()
      }
    } catch (err) {
      setError(describe(err))
      if (err instanceof ApiError && err.code === 'device_revoked') onRepair()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="safe-top safe-bottom flex h-full flex-col items-center justify-center gap-8 overflow-y-auto px-6 py-6">
      <div className="flex flex-col items-center gap-3">
        <img src="/icons/icon.svg" alt="" className="brand-glow h-16 w-16" />
        <h1 className="text-2xl font-semibold">{t('Password del PC')}</h1>
        <p className="max-w-xs text-center text-sm text-gray-400">
          {t('Inserisci la password impostata nella finestra di PadLink su «{pc}».', { pc: pcName })}
        </p>
      </div>
      <form
        className="flex w-full max-w-xs flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <input
          type="password"
          autoComplete="current-password"
          autoFocus
          maxLength={128}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="field"
          aria-label={t('Password del PC')}
          placeholder={t('Password del PC')}
        />
        <button type="submit" disabled={busy || !password} className="btn-primary">
          {busy ? t('Verifica…') : t('Sblocca')}
        </button>
        {error && <p className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-center text-sm text-red-300">{error}</p>}
      </form>
      <button className="btn-ghost w-full max-w-xs" onClick={onRepair}>
        {t('Associa di nuovo')}
      </button>
    </div>
  )
}
