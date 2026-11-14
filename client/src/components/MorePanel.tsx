import { useCallback, useEffect, useState } from 'react'
import { api, ApiError, logout, type Device } from '../lib/api'
import { usePrefs } from '../lib/settings'
import ConfirmDialog from './ConfirmDialog'
import { Icon } from './Icon'
import { APP_VERSION, LegalLinks } from './Legal'

function ago(ts: number) {
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return 'adesso'
  if (s < 3600) return `${Math.floor(s / 60)} min fa`
  if (s < 86400) return `${Math.floor(s / 3600)} h fa`
  return new Date(ts * 1000).toLocaleDateString()
}

export default function MorePanel({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [prefs, setPrefs] = usePrefs()
  const [devices, setDevices] = useState<Device[]>([])
  const [error, setError] = useState<string | null>(null)
  const [toRevoke, setToRevoke] = useState<Device | null>(null)
  const [confirmLogout, setConfirmLogout] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await api.devices()
      setDevices(res.devices)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Errore')
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
      setError(err instanceof ApiError ? err.message : 'Errore')
    }
  }

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-4 pb-8">
      <section className="flex flex-col gap-3">
        <h2 className="text-xs uppercase tracking-wide text-gray-500">Trackpad</h2>
        <div className="grid gap-4 rounded-2xl bg-ink-900 p-4 text-sm">
          <Range label={`Sensibilità: ${prefs.sensitivity.toFixed(1)}`} min={0.3} max={4} step={0.1}
            value={prefs.sensitivity} onChange={(v) => setPrefs({ sensitivity: v })} />
          <Range label={`Accelerazione: ${prefs.acceleration.toFixed(1)}`} min={0} max={3} step={0.1}
            value={prefs.acceleration} onChange={(v) => setPrefs({ acceleration: v })} />
          <Range label={`Velocità scroll: ${prefs.scrollSpeed.toFixed(1)}`} min={0.2} max={4} step={0.1}
            value={prefs.scrollSpeed} onChange={(v) => setPrefs({ scrollSpeed: v })} />
          <label className="flex items-center justify-between">
            Scroll naturale
            <input type="checkbox" checked={prefs.naturalScroll} onChange={(e) => setPrefs({ naturalScroll: e.target.checked })} />
          </label>
          <label className="flex items-center justify-between">
            Vibrazione (Android)
            <input type="checkbox" checked={prefs.haptics} onChange={(e) => setPrefs({ haptics: e.target.checked })} />
          </label>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xs uppercase tracking-wide text-gray-500">Dispositivi associati</h2>
          <button className="text-xs text-accent-2" onClick={() => void load()}>
            Aggiorna
          </button>
        </div>
        {error && <p className="rounded-xl bg-red-500/15 p-3 text-sm text-red-300">{error}</p>}
        <ul className="flex flex-col gap-2">
          {devices.map((d) => (
            <li key={d.id} className="flex items-center gap-3 rounded-2xl bg-ink-900 p-4">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">
                  {d.name} {d.current && <span className="ml-1 rounded bg-accent/20 px-1.5 py-0.5 text-[10px] text-accent-2">questo</span>}
                </p>
                <p className="truncate text-xs text-gray-500">
                  {d.last_ip} · {ago(d.last_seen)} · id {d.id.slice(0, 8)}
                </p>
              </div>
              <button className="key h-10 w-10 text-red-400" onClick={() => setToRevoke(d)} aria-label="Revoca">
                <Icon name="trash" className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      </section>

      <button className="rounded-2xl bg-red-500/15 py-4 font-medium text-red-300" onClick={() => setConfirmLogout(true)}>
        Disconnetti questo dispositivo
      </button>

      <section className="flex flex-col items-center gap-2 pt-2">
        <LegalLinks />
        <p className="text-[11px] text-gray-600">Kursor {APP_VERSION}</p>
      </section>

      {toRevoke && (
        <ConfirmDialog
          title="Revocare l'accesso?"
          message={`"${toRevoke.name}" non potrà più controllare il PC finché non verrà associato di nuovo.`}
          confirmLabel="Revoca"
          danger
          onCancel={() => setToRevoke(null)}
          onConfirm={() => void revoke(toRevoke)}
        />
      )}
      {confirmLogout && (
        <ConfirmDialog
          title="Disconnettere?"
          message="Servirà un nuovo PIN per associare di nuovo questo telefono."
          confirmLabel="Disconnetti"
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
