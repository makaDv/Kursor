import { useEffect, useRef, useState } from 'react'
import { t } from '../lib/i18n'
import { haptic } from '../lib/settings'

const HOLD_MS = 1200

/** Modal that requires press-and-hold to confirm, preventing accidental taps. */
export default function ConfirmDialog(props: {
  title: string
  message: string
  confirmLabel: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const [progress, setProgress] = useState(0)
  const raf = useRef(0)
  const startedAt = useRef(0)
  const done = useRef(false)

  useEffect(() => () => cancelAnimationFrame(raf.current), [])

  const tick = () => {
    const p = Math.min(1, (performance.now() - startedAt.current) / HOLD_MS)
    setProgress(p)
    if (p >= 1 && !done.current) {
      done.current = true
      haptic(40)
      props.onConfirm()
      return
    }
    raf.current = requestAnimationFrame(tick)
  }

  const begin = (e: React.PointerEvent) => {
    e.preventDefault()
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
    done.current = false
    startedAt.current = performance.now()
    raf.current = requestAnimationFrame(tick)
  }

  const end = () => {
    cancelAnimationFrame(raf.current)
    if (!done.current) setProgress(0)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-4 backdrop-blur-sm sm:items-center" onClick={props.onCancel}>
      <div
        role="dialog"
        aria-modal="true"
        className="safe-bottom w-full max-w-sm rounded-3xl border border-white/10 bg-ink-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">{props.title}</h2>
        <p className="mt-2 text-sm text-muted">{props.message}</p>
        <button
          className={`relative mt-6 h-14 w-full overflow-hidden rounded-2xl font-semibold text-white ${
            props.danger ? 'bg-red-900/60' : 'bg-indigo-900/60'
          }`}
          style={{ touchAction: 'none' }}
          onPointerDown={begin}
          onPointerUp={end}
          onPointerCancel={end}
          onPointerLeave={end}
          onContextMenu={(e) => e.preventDefault()}
        >
          <span
            className={`absolute inset-y-0 left-0 ${props.danger ? 'bg-red-500' : 'bg-accent'}`}
            style={{ width: `${progress * 100}%` }}
          />
          <span className="relative">{t('Tieni premuto: {a}', { a: props.confirmLabel })}</span>
        </button>
        <button className="btn-secondary mt-3 w-full" onClick={props.onCancel}>
          {t('Annulla')}
        </button>
      </div>
    </div>
  )
}
