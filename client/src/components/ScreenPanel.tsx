import { useEffect, useMemo, useRef, useState } from 'react'
import { t, useLang } from '../lib/i18n'
import { KursorSocket, type Monitor, type SocketStatus } from '../lib/socket'
import { getPrefs, haptic, usePrefs } from '../lib/settings'
import Trackpad from './Trackpad'
import { Icon } from './Icon'
import { useSecureScreen } from '../lib/pc'

// Must match server/kursor/control/screen.py HEADER ("<IffHHB3x", 20 bytes).
const HEADER_SIZE = 20
const MIME = ['image/jpeg', 'image/webp']

type Mode = 'touch' | 'trackpad'

export default function ScreenPanel({ control }: { control: KursorSocket }) {
  useLang()
  useSecureScreen() // the PC screen must not end up in screenshots or the recents preview
  const [prefs, setPrefs] = usePrefs()
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState<SocketStatus>('idle')
  const [mode, setMode] = useState<Mode>('touch')
  const [showSettings, setShowSettings] = useState(false)
  const [stats, setStats] = useState({ fps: 0, kbps: 0, w: 0, h: 0 })
  const [monitors, setMonitors] = useState<Monitor[]>([])
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const cursorRef = useRef<HTMLDivElement>(null)
  const counters = useRef({ frames: 0, bytes: 0 })

  const streamParams = () => {
    const p = getPrefs()
    return {
      fps: p.streamFps,
      quality: p.streamQuality,
      max_width: p.streamWidth,
      format: p.streamFormat,
      auto: p.streamAuto,
      monitor: p.monitor,
    }
  }

  const screen = useMemo(() => {
    let decoding = false
    const sock: KursorSocket = new KursorSocket({
      path: '/ws/screen',
      onStatus: (s) => {
        setStatus(s)
        if (s === 'open') {
          setMonitors(sock.monitors.filter((m) => m.index > 0))
          sock.send({ t: 'start', params: streamParams() })
        }
      },
      onBinary: async (buf) => {
        if (buf.byteLength <= HEADER_SIZE || decoding) return
        const view = new DataView(buf)
        const seq = view.getUint32(0, true)
        const cx = view.getFloat32(4, true)
        const cy = view.getFloat32(8, true)
        const fmt = view.getUint8(16)
        decoding = true
        try {
          const blob = new Blob([buf.slice(HEADER_SIZE)], { type: MIME[fmt] ?? 'image/jpeg' })
          const bmp = await createImageBitmap(blob)
          const canvas = canvasRef.current
          if (canvas) {
            if (canvas.width !== bmp.width || canvas.height !== bmp.height) {
              canvas.width = bmp.width
              canvas.height = bmp.height
            }
            canvas.getContext('2d')?.drawImage(bmp, 0, 0)
          }
          bmp.close()
          const cur = cursorRef.current
          if (cur) {
            const visible = cx >= 0 && cy >= 0
            cur.style.display = visible ? 'block' : 'none'
            cur.style.left = `${cx * 100}%`
            cur.style.top = `${cy * 100}%`
          }
          counters.current.frames++
          counters.current.bytes += buf.byteLength
        } catch {
          /* corrupt frame: skip */
        } finally {
          decoding = false
          sock.send({ t: 'ack', seq })
        }
      },
    })
    return sock
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (running) screen.start()
    else screen.stop()
    return () => screen.stop()
  }, [running, screen])

  useEffect(() => {
    const id = window.setInterval(() => {
      const c = counters.current
      const canvas = canvasRef.current
      setStats({ fps: c.frames, kbps: Math.round((c.bytes * 8) / 1000), w: canvas?.width ?? 0, h: canvas?.height ?? 0 })
      c.frames = 0
      c.bytes = 0
    }, 1000)
    return () => window.clearInterval(id)
  }, [])

  const pushConfig = () => screen.send({ t: 'config', params: streamParams() })

  // ---- direct touch on the screen image -------------------------------------
  useEffect(() => {
    const el = canvasRef.current
    if (!el || mode !== 'touch') return
    let start = 0
    let moved = 0
    let maxTouches = 0
    let longTimer: number | undefined
    let longFired = false
    let lastY = 0
    let lastX = 0

    const norm = (t: Touch) => {
      const r = el.getBoundingClientRect()
      return {
        x: Math.min(1, Math.max(0, (t.clientX - r.left) / r.width)),
        y: Math.min(1, Math.max(0, (t.clientY - r.top) / r.height)),
      }
    }
    const abs = (t: Touch) => {
      const p = norm(t)
      control.send({ t: 'abs', x: +p.x.toFixed(5), y: +p.y.toFixed(5), m: getPrefs().monitor })
    }

    const onStart = (e: TouchEvent) => {
      e.preventDefault()
      maxTouches = Math.max(maxTouches, e.touches.length)
      if (e.touches.length === 1) {
        start = performance.now()
        moved = 0
        longFired = false
        lastX = e.touches[0].clientX
        lastY = e.touches[0].clientY
        abs(e.touches[0])
        longTimer = window.setTimeout(() => {
          if (moved < 10) {
            longFired = true
            control.send({ t: 'click', b: 'right', n: 1 })
            haptic(25)
          }
        }, 550)
      } else {
        window.clearTimeout(longTimer)
        const c = e.touches
        lastX = (c[0].clientX + c[1].clientX) / 2
        lastY = (c[0].clientY + c[1].clientY) / 2
      }
    }
    const onMove = (e: TouchEvent) => {
      e.preventDefault()
      if (e.touches.length === 1 && maxTouches === 1) {
        const t = e.touches[0]
        moved += Math.abs(t.clientX - lastX) + Math.abs(t.clientY - lastY)
        lastX = t.clientX
        lastY = t.clientY
        if (moved > 10) window.clearTimeout(longTimer)
        abs(t)
      } else if (e.touches.length >= 2) {
        const c = e.touches
        const x = (c[0].clientX + c[1].clientX) / 2
        const y = (c[0].clientY + c[1].clientY) / 2
        const p = getPrefs()
        const dir = p.naturalScroll ? 1 : -1
        control.send({ t: 'scroll', dx: (-(x - lastX) / 28) * p.scrollSpeed * dir, dy: ((y - lastY) / 28) * p.scrollSpeed * dir })
        lastX = x
        lastY = y
        moved += 100
      }
    }
    const onEnd = (e: TouchEvent) => {
      e.preventDefault()
      if (e.touches.length > 0) return
      window.clearTimeout(longTimer)
      if (maxTouches === 1 && !longFired && moved < 10 && performance.now() - start < 300) {
        control.send({ t: 'click', b: 'left', n: 1 })
        haptic(8)
      }
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
    }
  }, [mode, control, running])

  const fullscreen = () => {
    const el = wrapRef.current as (HTMLDivElement & { webkitRequestFullscreen?: () => void }) | null
    if (!el) return
    if (document.fullscreenElement) void document.exitFullscreen()
    else if (el.requestFullscreen) void el.requestFullscreen().catch(() => {})
    else el.webkitRequestFullscreen?.()
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex items-center gap-2 p-3">
        <button className={`key gap-2 px-4 ${running ? 'key-on' : ''}`} onClick={() => setRunning(!running)}>
          <Icon name={running ? 'stop' : 'play'} className="h-4 w-4" />
          {running ? t('Ferma') : t('Avvia streaming')}
        </button>
        <div className="flex rounded-xl bg-ink-800 p-1 text-xs">
          {(['touch', 'trackpad'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded-lg px-3 py-2 ${mode === m ? 'bg-ink-700 text-gray-50' : 'text-gray-400'}`}
            >
              {m === 'touch' ? t('Tocco') : t('Trackpad')}
            </button>
          ))}
        </div>
        <button className="key ml-auto px-3" onClick={fullscreen} aria-label={t('Schermo intero')}>
          <Icon name="expand" className="h-4 w-4" />
        </button>
        <button className={`key px-3 ${showSettings ? 'key-on' : ''}`} onClick={() => setShowSettings(!showSettings)} aria-label={t('Impostazioni streaming')} aria-expanded={showSettings}>
          ⚙
        </button>
      </div>

      {showSettings && (
        <div className="mx-3 mb-3 grid gap-3 card p-4 text-sm">
          <Slider label={t('Fotogrammi al secondo: {v}', { v: prefs.streamFps })} min={1} max={30} value={prefs.streamFps}
            onChange={(v) => setPrefs({ streamFps: v })} onCommit={pushConfig} />
          <Slider label={t('Qualità: {v}', { v: prefs.streamQuality })} min={10} max={95} value={prefs.streamQuality}
            onChange={(v) => setPrefs({ streamQuality: v })} onCommit={pushConfig} />
          <Slider label={t('Larghezza max: {v}px', { v: prefs.streamWidth })} min={480} max={2560} step={160} value={prefs.streamWidth}
            onChange={(v) => setPrefs({ streamWidth: v })} onCommit={pushConfig} />
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={prefs.streamAuto}
                onChange={(e) => { setPrefs({ streamAuto: e.target.checked }); pushConfig() }} />
              {t('Qualità adattiva')}
            </label>
            <select value={prefs.streamFormat} className="rounded-lg bg-ink-800 px-2 py-1"
              onChange={(e) => { setPrefs({ streamFormat: e.target.value as 'jpeg' | 'webp' }); pushConfig() }}>
              <option value="jpeg">JPEG</option>
              <option value="webp">WebP</option>
            </select>
            {monitors.length > 1 && (
              <select value={prefs.monitor} className="rounded-lg bg-ink-800 px-2 py-1"
                onChange={(e) => { setPrefs({ monitor: Number(e.target.value) }); pushConfig() }}>
                {monitors.map((m) => (
                  <option key={m.index} value={m.index}>Monitor {m.index} ({m.width}×{m.height})</option>
                ))}
              </select>
            )}
          </div>
        </div>
      )}

      <div ref={wrapRef} className="relative mx-3 flex items-center justify-center overflow-hidden rounded-2xl bg-black">
        <div className="relative w-full">
          <canvas
            ref={canvasRef}
            className="block h-auto w-full"
            style={{ touchAction: mode === 'touch' ? 'none' : 'auto', aspectRatio: stats.w ? undefined : '16 / 9' }}
          />
          <div
            ref={cursorRef}
            className="pointer-events-none absolute hidden h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-accent shadow"
          />
          {!running && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-gray-500">
              {status === 'forbidden' ? t('Questo dispositivo non ha il permesso di vedere lo schermo (impostazione sul PC).') : t('Streaming disattivato')}
            </div>
          )}
        </div>
      </div>
      {running && (
        <p className="px-3 pt-1 text-right font-mono text-[10px] text-gray-500">
          {status === 'forbidden' ? t('Non consentito') : status !== 'open' ? t('Connessione…') : `${stats.fps} fps · ${stats.kbps} kbit/s · ${stats.w}×${stats.h}`}
        </p>
      )}
      {mode === 'trackpad' && <Trackpad socket={control} />}
    </div>
  )
}

function Slider(props: {
  label: string
  min: number
  max: number
  step?: number
  value: number
  onChange: (v: number) => void
  onCommit: () => void
}) {
  return (
    <label className="flex flex-col gap-1 text-gray-300">
      {props.label}
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step ?? 1}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
        onPointerUp={props.onCommit}
        onTouchEnd={props.onCommit}
        onKeyUp={props.onCommit}
      />
    </label>
  )
}
