import { useEffect, useRef, useState } from 'react'
import type { KursorSocket } from '../lib/socket'
import { t, useLang } from '../lib/i18n'
import { getPrefs, haptic, usePrefs } from '../lib/settings'

/**
 * Gestures:
 *  - 1 finger move     relative cursor movement (with pointer acceleration)
 *  - 1 finger tap      left click (two quick taps = OS double click)
 *  - long press + move drag (left button held until the finger lifts)
 *  - 2 finger move     scroll (vertical and horizontal)
 *  - 2 finger tap      right click
 *  - 3 finger tap      middle click
 */

const TAP_MAX_MS = 220
const TAP_MAX_MOVE = 8
const LONG_PRESS_MS = 450
const SCROLL_DIVISOR = 28

interface Pt {
  x: number
  y: number
}

function centroid(list: TouchList): Pt {
  let x = 0
  let y = 0
  for (let i = 0; i < list.length; i++) {
    x += list[i].clientX
    y += list[i].clientY
  }
  return { x: x / list.length, y: y / list.length }
}

export default function Trackpad({ socket, full = false }: { socket: KursorSocket; full?: boolean }) {
  useLang()
  const [prefs] = usePrefs()
  const padRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  const [dragLock, setDragLock] = useState(false)

  useEffect(() => {
    const el = padRef.current
    if (!el) return

    let startTime = 0
    let maxTouches = 0
    let moved = 0
    let last: Pt = { x: 0, y: 0 }
    let lastT = 0
    let mode: 'idle' | 'move' | 'scroll' | 'drag' = 'idle'
    let longTimer: number | undefined
    let pendX = 0
    let pendY = 0
    let pendSX = 0
    let pendSY = 0
    let raf = 0

    const flush = () => {
      raf = 0
      if (pendX || pendY) {
        socket.send({ t: 'move', dx: +pendX.toFixed(2), dy: +pendY.toFixed(2) })
        pendX = pendY = 0
      }
      if (pendSX || pendSY) {
        socket.send({ t: 'scroll', dx: +pendSX.toFixed(3), dy: +pendSY.toFixed(3) })
        pendSX = pendSY = 0
      }
    }
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(flush)
    }

    const onStart = (e: TouchEvent) => {
      e.preventDefault()
      const n = e.touches.length
      if (n === 1 && mode === 'idle') {
        startTime = performance.now()
        maxTouches = 1
        moved = 0
        mode = 'move'
        longTimer = window.setTimeout(() => {
          if (moved < TAP_MAX_MOVE && mode === 'move') {
            mode = 'drag'
            socket.send({ t: 'down', b: 'left' })
            setDragging(true)
            haptic(25)
          }
        }, LONG_PRESS_MS)
      } else if (n >= 2) {
        window.clearTimeout(longTimer)
        maxTouches = Math.max(maxTouches, n)
        if (mode !== 'drag') mode = 'scroll'
      }
      last = centroid(e.touches)
      lastT = performance.now()
    }

    const onMove = (e: TouchEvent) => {
      e.preventDefault()
      const c = centroid(e.touches)
      const dx = c.x - last.x
      const dy = c.y - last.y
      const now = performance.now()
      const dt = Math.max(1, now - lastT)
      last = c
      lastT = now
      moved += Math.abs(dx) + Math.abs(dy)
      if (moved > TAP_MAX_MOVE) window.clearTimeout(longTimer)

      const prefs = getPrefs()
      if (mode === 'move' || mode === 'drag') {
        const speed = Math.hypot(dx, dy) / dt // px per ms
        const gain = prefs.sensitivity * (1 + prefs.acceleration * Math.min(speed, 2.5))
        pendX += dx * gain * devicePixelRatio
        pendY += dy * gain * devicePixelRatio
        schedule()
      } else if (mode === 'scroll') {
        const dir = prefs.naturalScroll ? 1 : -1
        pendSX += (-dx / SCROLL_DIVISOR) * prefs.scrollSpeed * dir
        pendSY += (dy / SCROLL_DIVISOR) * prefs.scrollSpeed * dir
        schedule()
      }
    }

    const onEnd = (e: TouchEvent) => {
      e.preventDefault()
      if (e.touches.length > 0) {
        last = centroid(e.touches)
        return
      }
      window.clearTimeout(longTimer)
      const duration = performance.now() - startTime
      flush()
      if (mode === 'drag') {
        socket.send({ t: 'up', b: 'left' })
        setDragging(false)
      } else if (duration < TAP_MAX_MS + (maxTouches > 1 ? 80 : 0) && moved < TAP_MAX_MOVE * maxTouches) {
        const b = maxTouches >= 3 ? 'middle' : maxTouches === 2 ? 'right' : 'left'
        socket.send({ t: 'click', b, n: 1 })
        haptic(8)
      }
      mode = 'idle'
      maxTouches = 0
    }

    el.addEventListener('touchstart', onStart, { passive: false })
    el.addEventListener('touchmove', onMove, { passive: false })
    el.addEventListener('touchend', onEnd, { passive: false })
    el.addEventListener('touchcancel', onEnd, { passive: false })
    return () => {
      el.removeEventListener('touchstart', onStart)
      el.removeEventListener('touchmove', onMove)
      el.removeEventListener('touchend', onEnd)
      el.removeEventListener('touchcancel', onEnd)
      window.clearTimeout(longTimer)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [socket])

  const button = (b: 'left' | 'middle' | 'right') => ({
    onTouchStart: (e: React.TouchEvent) => {
      e.preventDefault()
      socket.send({ t: 'down', b })
      haptic(8)
    },
    onTouchEnd: (e: React.TouchEvent) => {
      e.preventDefault()
      socket.send({ t: 'up', b })
    },
    onMouseDown: () => socket.send({ t: 'down', b }),
    onMouseUp: () => socket.send({ t: 'up', b }),
  })

  const toggleDragLock = () => {
    const next = !dragLock
    setDragLock(next)
    socket.send({ t: next ? 'down' : 'up', b: 'left' })
    haptic(15)
  }

  return (
    <div className={`flex flex-col gap-2 p-3 ${full ? 'h-full' : ''}`}>
      <div
        ref={padRef}
        className={`relative flex flex-1 items-center justify-center rounded-3xl border border-ink-700 bg-gradient-to-b from-ink-900 to-ink-800 ${
          full ? 'min-h-0' : 'min-h-44'
        } ${dragging || dragLock ? 'ring-2 ring-accent' : ''}`}
        style={{ touchAction: 'none' }}
      >
        <span className="pointer-events-none px-6 text-center text-xs leading-relaxed text-gray-500">
          {dragging ? t('Trascinamento…') : full ? t('Tocca = click · 2 dita = scroll / click destro · tieni premuto = trascina') : ''}
        </span>
      </div>
      {/* Left-handed: mirrored order, the main (left-click) button sits under the left thumb's natural reach. */}
      <div className={`grid gap-2 ${prefs.leftHanded ? 'grid-cols-[auto_2fr_1fr_2fr]' : 'grid-cols-[2fr_1fr_2fr_auto]'}`}>
        {(prefs.leftHanded ? (['lock', 'right', 'middle', 'left'] as const) : (['left', 'middle', 'right', 'lock'] as const)).map((b) =>
          b === 'lock' ? (
            <button
              key={b}
              className={`key h-12 px-3 ${dragLock ? 'key-on' : ''}`}
              onClick={toggleDragLock}
              title={t('Blocca trascinamento')}
              aria-label={t('Blocca trascinamento')}
              aria-pressed={dragLock}
            >
              ⇲
            </button>
          ) : (
            <button key={b} className="key h-12" {...button(b)}>
              {t(b === 'left' ? 'Sinistro' : b === 'middle' ? 'Centro' : 'Destro')}
            </button>
          ),
        )}
      </div>
    </div>
  )
}
