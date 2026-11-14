import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, logout, type Device } from '../lib/api'
import { t, useLang } from '../lib/i18n'
import { biometricAvailable, canCaptureVolumeKeys } from '../lib/pc'
import { isNative } from '../lib/platform'
import { usePrefs } from '../lib/settings'
import ConfirmDialog from './ConfirmDialog'
import { Icon } from './Icon'
import { APP_VERSION, LegalLinks } from './Legal'
import SystemPanel from './SystemPanel'

function ago(ts: number) {
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return t('adesso')
  if (s < 3600) return t('{n} min fa', { n: Math.floor(s / 60) })
  if (s < 86400) return t('{n} h fa', { n: Math.floor(s / 3600) })
  return new Date(ts * 1000).toLocaleDateString()
}

export default function MorePanel({
  onLoggedOut,
  canPower = true,
  onHelp,
}: {
  onLoggedOut: () => void
  canPower?: boolean
  onHelp?: () => void
}) {
  useLang()
  const [prefs, setPrefs] = usePrefs()
  const [devices, setDevices] = useState<Device[]>([])
  const [error, setError] = useState<string | null>(null)
  const [toRevoke, setToRevoke] = useState<Device | null>(null)
  const [confirmLogout, setConfirmLogout] = useState(false)
  const [bio, setBio] = useState(false)

  useEffect(() => {
    void biometricAvailable().then(setBio)
  }, [])

  const load = useCallback(async () => {
    try {
      const res = await api.devices()
      setDevices(res.devices)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Errore'))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const revoke = async (d: Device) => {
    setToRevoke(null)
    try {
      await api.revokeDevice(d.id)
      if (d.current) onLoggedOut()
      else void load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Errore'))
    }
  }

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-4 pb-8">
      <section className="flex flex-col gap-3">
        <h2 className="section-title">{t('Computer')}</h2>
        <SystemPanel canPower={canPower} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="section-title">{t('Trackpad')}</h2>
        <div className="grid gap-4 card p-4 text-sm">
          <Range label={t('Sensibilità: {v}', { v: prefs.sensitivity.toFixed(1) })} min={0.3} max={4} step={0.1}
            value={prefs.sensitivity} onChange={(v) => setPrefs({ sensitivity: v })} />
          <Range label={t('Accelerazione: {v}', { v: prefs.acceleration.toFixed(1) })} min={0} max={3} step={0.1}
            value={prefs.acceleration} onChange={(v) => setPrefs({ acceleration: v })} />
          <Range label={t('Velocità scroll: {v}', { v: prefs.scrollSpeed.toFixed(1) })} min={0.2} max={4} step={0.1}
            value={prefs.scrollSpeed} onChange={(v) => setPrefs({ scrollSpeed: v })} />
          <Toggle label={t('Scroll naturale')} checked={prefs.naturalScroll} onChange={(v) => setPrefs({ naturalScroll: v })} />
          <Toggle label={t('Pulsanti per mancini')} checked={prefs.leftHanded} onChange={(v) => setPrefs({ leftHanded: v })} />
          <Toggle label={t('Vibrazione (Android)')} checked={prefs.haptics} onChange={(v) => setPrefs({ haptics: v })} />
          {canCaptureVolumeKeys && (
            <Toggle label={t('Tasti volume del telefono = volume del PC')} checked={prefs.volumeKeys} onChange={(v) => setPrefs({ volumeKeys: v })} />
          )}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="section-title">{t('Aspetto e lingua')}</h2>
        <div className="grid gap-4 card p-4 text-sm">
          <Choice
            label={t('Tema')}
            value={prefs.theme}
            options={[['auto', t('Automatico')], ['dark', t('Scuro')], ['light', t('Chiaro')]]}
            onChange={(v) => setPrefs({ theme: v as typeof prefs.theme })}
          />
          <Range label={t('Dimensione testo: {v}%', { v: Math.round(prefs.textScale * 100) })} min={0.85} max={1.4} step={0.05}
            value={prefs.textScale} onChange={(v) => setPrefs({ textScale: v })} />
          <Choice
            label={t('Lingua')}
            value={prefs.lang}
            options={[['auto', t('Automatica')], ['it', 'Italiano'], ['en', 'English']]}
            onChange={(v) => setPrefs({ lang: v as typeof prefs.lang })}
          />
        </div>
      </section>

      {isNative && bio && (
        <section className="flex flex-col gap-3">
          <h2 className="section-title">{t('Sicurezza')}</h2>
          <div className="grid gap-4 card p-4 text-sm">
            <Toggle label={t('Sblocca PadLink con impronta o volto')} checked={prefs.biometricLock} onChange={(v) => setPrefs({ biometricLock: v })} />
            <Toggle label={t('Chiedi impronta o volto per spegnere e terminare')} checked={prefs.biometricPower} onChange={(v) => setPrefs({ biometricPower: v })} />
          </div>
        </section>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="section-title">{t('Dispositivi associati')}</h2>
          <button className="text-xs text-accent-2" onClick={() => void load()}>
            {t('Aggiorna')}
          </button>
        </div>
        {error && <p className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}
        <ul className="flex flex-col gap-2">
          {devices.map((d) => (
            <li key={d.id} className="flex items-center gap-3 card p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">
                  {d.name} {d.current && <span className="ml-1 rounded bg-accent/20 px-1.5 py-0.5 text-[10px] text-accent-2">{t('questo')}</span>}
                </p>
                <p className="truncate text-xs text-gray-500">
                  {d.last_ip} · {ago(d.last_seen)} · id {d.id.slice(0, 8)}
                </p>
              </div>
              <button className="key h-10 w-10 text-red-400" onClick={() => setToRevoke(d)} aria-label={t('Revoca {name}', { name: d.name })}>
                <Icon name="trash" className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      </section>

      {onHelp && (
        <button className="btn-secondary" onClick={onHelp}>
          {t('Aiuto e segnalazioni')}
        </button>
      )}
      <button className="btn-danger" onClick={() => setConfirmLogout(true)}>
        {t('Disconnetti questo dispositivo')}
      </button>

      <section className="flex flex-col items-center gap-2 pt-2">
        <LegalLinks />
        <p className="text-[11px] text-gray-600">PadLink {APP_VERSION}</p>
      </section>

      {toRevoke && (
        <ConfirmDialog
          title={t('Revocare l’accesso?')}
          message={t('«{name}» non potrà più controllare il PC finché non verrà associato di nuovo.', { name: toRevoke.name })}
          confirmLabel={t('Revoca')}
          danger
          onCancel={() => setToRevoke(null)}
          onConfirm={() => void revoke(toRevoke)}
        />
      )}
      {confirmLogout && (
        <ConfirmDialog
          title={t('Disconnettere?')}
          message={t('Servirà un nuovo PIN per associare di nuovo questo telefono.')}
          confirmLabel={t('Disconnetti')}
          danger
          onCancel={() => setConfirmLogout(false)}
          onConfirm={() => {
            setConfirmLogout(false)
            void logout().finally(onLoggedOut)
          }}
        />
      )}
    </div>
  )
}

function Range(props: { label: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void }) {
  return (
    <label className="flex flex-col gap-1 text-gray-300">
      {props.label}
      <input type="range" min={props.min} max={props.max} step={props.step} value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))} />
    </label>
  )
}

function Toggle(props: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-4">
      <span>{props.label}</span>
      <input type="checkbox" className="h-5 w-5 shrink-0" checked={props.checked} onChange={(e) => props.onChange(e.target.checked)} />
    </label>
  )
}

function Choice(props: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-gray-300">{props.label}</span>
      <div className="grid gap-1 rounded-xl bg-ink-800 p-1" style={{ gridTemplateColumns: `repeat(${props.options.length}, 1fr)` }} role="radiogroup" aria-label={props.label}>
        {props.options.map(([v, l]) => (
          <button
            key={v}
            role="radio"
            aria-checked={props.value === v}
            onClick={() => props.onChange(v)}
            className={`rounded-lg px-2 py-2 text-xs font-medium ${props.value === v ? 'bg-accent text-white' : 'text-gray-400'}`}
          >
            {l}
          </button>
        ))}
      </div>
    </div>
  )
}
