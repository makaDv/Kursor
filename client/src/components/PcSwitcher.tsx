import { useState } from 'react'
import { t, useLang } from '../lib/i18n'
import { getServer, listServers, removeServer, switchServer, type ServerConfig } from '../lib/platform'
import ConfirmDialog from './ConfirmDialog'
import { Icon } from './Icon'
import { Sheet } from './Legal'

function label(c: ServerConfig) {
  return c.name || c.origin.replace(/^https:\/\//, '').replace(/:\d+$/, '')
}

/** List of paired PCs (home, office...): switch, add another, forget one. */
export default function PcSwitcher(props: { onClose: () => void; onSwitched: () => void; onAdd: () => void }) {
  useLang()
  const [items, setItems] = useState(listServers)
  const [forget, setForget] = useState<ServerConfig | null>(null)
  const current = getServer()?.id

  return (
    <Sheet title={t('I tuoi PC')} onClose={props.onClose}>
      <ul className="flex flex-col gap-2">
        {items.map((c) => (
          <li key={c.id} className={`card flex items-center gap-3 p-4 ${c.id === current ? 'ring-1 ring-accent/60' : ''}`}>
            <button
              className="flex min-w-0 flex-1 items-center gap-3 text-left"
              onClick={async () => {
                if (c.id && c.id !== current && (await switchServer(c.id))) props.onSwitched()
                else props.onClose()
              }}
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/15 text-accent-2">
                <Icon name="monitor" className="h-5 w-5" />
              </span>
              <span className="min-w-0">
                <span className="block truncate font-medium text-gray-100">{label(c)}</span>
                <span className="block truncate text-xs text-muted">{c.origin.replace(/^https:\/\//, '')}</span>
              </span>
              {c.id === current && <span className="chip bg-accent/20 text-accent-2">{t('in uso')}</span>}
            </button>
            <button className="key h-10 w-10 text-red-400" aria-label={t('Dimentica questo PC')} onClick={() => setForget(c)}>
              <Icon name="trash" className="h-4 w-4" />
            </button>
          </li>
        ))}
      </ul>
      <button className="btn-primary mt-4 w-full" onClick={props.onAdd}>
        {t('Aggiungi un altro PC')}
      </button>
      {forget && (
        <ConfirmDialog
          title={t('Dimenticare {pc}?', { pc: label(forget) })}
          message={t('Il telefono non si collegherà più a questo PC finché non lo associ di nuovo.')}
          confirmLabel={t('Dimentica')}
          danger
          onCancel={() => setForget(null)}
          onConfirm={async () => {
            const wasCurrent = forget.id === current
            await removeServer(forget.id!)
            setForget(null)
            setItems(listServers())
            if (wasCurrent) props.onSwitched()
          }}
        />
      )}
    </Sheet>
  )
}
