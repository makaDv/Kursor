import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError, type PcWindow, type WindowAction } from '../lib/api'
import ConfirmDialog from './ConfirmDialog'
import { Icon } from './Icon'

const POLL_MS = 3000

/** Open applications on the PC: see what is running and switch, minimize, maximize, close. */
export default function AppsPanel({ onShowScreen }: { onShowScreen: () => void }) {
  const [list, setList] = useState<PcWindow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [confirm, setConfirm] = useState<{ win: PcWindow; action: 'close' | 'kill' } | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await api.windows()
      setList(res.windows)
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Errore')
    }
  }, [])

  useEffect(() => {
    void load()
    const t = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load()
    }, POLL_MS)
    return () => window.clearInterval(t)
  }, [load])

  const run = async (win: PcWindow, action: WindowAction) => {
    setConfirm(null)
    setBusy(true)
    try {
      await api.windowAction(win.id, action)
      if (action === 'close' || action === 'kill') setSelected(null)
      window.setTimeout(() => void load(), 400)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Errore')
    } finally {
      setBusy(false)
    }
  }

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase()
    const items = (list ?? []).filter((w) => !q || w.app.toLowerCase().includes(q) || w.title.toLowerCase().includes(q))
    return items.sort((a, b) => Number(b.focused) - Number(a.focused) || a.app.localeCompare(b.app))
  }, [list, filter])

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-4 pb-8">
      <div className="flex gap-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Cerca un'app o una finestra"
          className="min-w-0 flex-1 field"
        />
        <button className="key px-4" onClick={() => void load()} aria-label="Aggiorna">
          <Icon name="refresh" />
        </button>
      </div>

      {error && <p className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-center text-sm text-red-300">{error}</p>}
      {list === null && !error && <p className="text-center text-sm text-gray-500">Caricamento…</p>}
      {list !== null && shown.length === 0 && (
        <p className="text-center text-sm text-gray-500">{filter ? 'Nessun risultato.' : 'Nessuna finestra aperta.'}</p>
      )}

      {shown.map((w) => {
        const open = selected === w.id
        return (
          <div key={w.id} className={`card ${w.focused ? 'border-accent/50' : ''}`}>
            <button className="flex w-full items-center gap-3 p-4 text-left" onClick={() => setSelected(open ? null : w.id)}>
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/15 font-semibold text-accent">
                {(w.app || '?').slice(0, 1).toUpperCase()}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate font-medium">{w.app}</span>
                <span className="truncate text-xs text-gray-400">{w.title}</span>
              </span>
              {w.focused && <span className="rounded-full bg-accent/20 px-2 py-0.5 text-[10px] text-accent-2">attiva</span>}
              {w.minimized && <span className="rounded-full bg-ink-800 px-2 py-0.5 text-[10px] text-gray-400">ridotta</span>}
            </button>
            {open && (
              <div className="grid grid-cols-3 gap-2 px-4 pb-4">
                <button className="key py-3 text-sm" disabled={busy} onClick={() => void run(w, 'focus')}>
                  Porta avanti
                </button>
                <button
                  className="key py-3 text-sm"
                  disabled={busy}
                  onClick={() => {
                    void run(w, 'focus')
                    onShowScreen()
                  }}
                >
                  Vedi schermo
                </button>
                <button className="key py-3 text-sm" disabled={busy} onClick={() => void run(w, 'minimize')}>
                  Riduci
                </button>
                <button
                  className="key py-3 text-sm"
                  disabled={busy}
                  onClick={() => void run(w, w.maximized ? 'restore' : 'maximize')}
                >
                  {w.maximized ? 'Ripristina' : 'Ingrandisci'}
                </button>
                <button
                  className="key py-3 text-sm text-red-300"
                  disabled={busy}
                  onClick={() => setConfirm({ win: w, action: 'close' })}
                >
                  Chiudi
                </button>
                <button
                  className="key py-3 text-sm text-red-400 disabled:opacity-30"
                  disabled={busy || w.protected}
                  onClick={() => setConfirm({ win: w, action: 'kill' })}
                  title={w.protected ? 'Processo di sistema' : undefined}
                >
                  Termina
                </button>
              </div>
            )}
          </div>
        )
      })}

      {confirm && (
        <ConfirmDialog
          title={confirm.action === 'close' ? `Chiudere ${confirm.win.app}?` : `Terminare ${confirm.win.app}?`}
          message={
            confirm.action === 'close'
              ? 'Come premere la X: il programma potrebbe chiederti sul PC di salvare il lavoro.'
              : 'Chiusura forzata immediata: il lavoro non salvato andrà perso. Usala solo se il programma non risponde.'
          }
          confirmLabel={confirm.action === 'close' ? 'Chiudi' : 'Termina'}
          danger
          onCancel={() => setConfirm(null)}
          onConfirm={() => void run(confirm.win, confirm.action)}
        />
      )}
    </div>
  )
}
