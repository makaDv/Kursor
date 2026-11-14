import { useState } from 'react'
import { api, ApiError } from '../lib/api'
import { t, useLang } from '../lib/i18n'
import { confirmWithBiometrics } from '../lib/pc'
import ConfirmDialog from './ConfirmDialog'
import { Icon, type IconName } from './Icon'

type Action = 'lock' | 'sleep' | 'shutdown'

const ACTIONS: { id: Action; label: string; desc: string; icon: IconName; danger: boolean }[] = [
  { id: 'lock', label: 'Blocca', desc: 'Blocca la sessione del PC (serve la password per rientrare).', icon: 'lock', danger: false },
  { id: 'sleep', label: 'Sospendi', desc: 'Mette il PC in sospensione. PadLink non sarà raggiungibile finché non si risveglia.', icon: 'moon', danger: true },
  { id: 'shutdown', label: 'Spegni', desc: 'Spegne il PC tra 10 secondi. Il lavoro non salvato andrà perso.', icon: 'power', danger: true },
]

export default function SystemPanel({ canPower = true }: { canPower?: boolean }) {
  useLang()
  const [pending, setPending] = useState<Action | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  const run = async (action: Action) => {
    setPending(null)
    const label = t(ACTIONS.find((a) => a.id === action)!.label)
    // Power actions also ask for fingerprint / face (if enabled in Altro > Sicurezza).
    if (!(await confirmWithBiometrics(t('Conferma: {a} il PC', { a: label.toLowerCase() }), 'power'))) return
    try {
      await api.system(action)
      setMessage({ ok: true, text: t('Comando «{a}» inviato.', { a: label }) })
    } catch (err) {
      setMessage({ ok: false, text: err instanceof ApiError ? err.message : t('Errore') })
    }
  }

  const current = ACTIONS.find((a) => a.id === pending)

  if (!canPower) {
    return <p className="card p-4 text-sm text-muted">{t('Blocco, sospensione e spegnimento non sono consentiti a questo dispositivo (impostazione sul PC).')}</p>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-2">
        {ACTIONS.map((a) => (
          <button key={a.id} onClick={() => setPending(a.id)} className="card flex flex-col items-center gap-2 px-2 py-4 text-sm font-medium active:bg-ink-800">
            <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${a.danger ? 'bg-red-500/15 text-red-400' : 'bg-accent/15 text-accent-2'}`}>
              <Icon name={a.icon} className="h-5 w-5" />
            </span>
            {t(a.label)}
          </button>
        ))}
      </div>
      {message && (
        <p className={`rounded-xl p-3 text-center text-sm ${message.ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'}`} role="status">
          {message.text}
        </p>
      )}
      {current && (
        <ConfirmDialog
          title={t('{a} il PC?', { a: t(current.label) })}
          message={t(current.desc)}
          confirmLabel={t(current.label)}
          danger={current.danger}
          onCancel={() => setPending(null)}
          onConfirm={() => void run(current.id)}
        />
      )}
    </div>
  )
}
