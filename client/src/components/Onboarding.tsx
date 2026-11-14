import { useState } from 'react'
import { t, useLang } from '../lib/i18n'
import { Icon, type IconName } from './Icon'

const KEY = 'padlink.onboarding.v1'

export function onboardingDone(): boolean {
  try {
    return localStorage.getItem(KEY) !== null
  } catch {
    return true
  }
}

function markDone() {
  try {
    localStorage.setItem(KEY, '1')
  } catch {
    /* ignore */
  }
}

const SLIDES: { icon: IconName; title: string; text: string; points?: string[] }[] = [
  {
    icon: 'monitor',
    title: 'Installa PadLink sul PC',
    text: 'Scarica il programma gratuito PadLink per Windows e aprilo: comparirà un’icona vicino all’orologio.',
  },
  {
    icon: 'apps',
    title: 'Scansiona il QR code',
    text: 'Nella finestra di PadLink sul PC premi «Associa un telefono», poi inquadra il QR con questa app.',
  },
  {
    icon: 'pointer',
    title: 'Ecco i gesti',
    text: 'Usa lo schermo del telefono come il touchpad di un portatile:',
    points: [
      'Un tocco: click sinistro',
      'Due dita: scorri, oppure tocca per il click destro',
      'Tieni premuto e muovi: trascina',
    ],
  },
]

/** Three-step introduction shown once, after accepting the terms. */
export default function Onboarding({ onDone }: { onDone: () => void }) {
  useLang()
  const [i, setI] = useState(0)
  const slide = SLIDES[i]
  const last = i === SLIDES.length - 1
  const finish = () => {
    markDone()
    onDone()
  }
  return (
    <div className="safe-top safe-bottom flex h-full flex-col px-6 py-6">
      <div className="flex justify-end">
        <button className="btn-ghost min-h-10 px-3 text-sm" onClick={finish}>
          {t('Salta')}
        </button>
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
        <span className="flex h-24 w-24 items-center justify-center rounded-3xl bg-accent/15 text-accent-2">
          <Icon name={slide.icon} className="h-12 w-12" />
        </span>
        <p className="text-xs font-semibold tracking-wider text-muted uppercase">
          {t('Passo {n} di {tot}', { n: i + 1, tot: SLIDES.length })}
        </p>
        <h1 className="text-2xl font-semibold">{t(slide.title)}</h1>
        <p className="max-w-xs text-sm text-muted">{t(slide.text)}</p>
        {slide.points && (
          <ul className="card flex w-full max-w-xs flex-col gap-2 p-4 text-left text-sm">
            {slide.points.map((pt) => (
              <li key={pt} className="flex gap-2">
                <span className="text-accent-2">•</span>
                {t(pt)}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-col items-center gap-4">
        <div className="flex gap-2" aria-hidden="true">
          {SLIDES.map((_, k) => (
            <span key={k} className={`h-2 rounded-full transition-all ${k === i ? 'w-6 bg-accent' : 'w-2 bg-ink-700'}`} />
          ))}
        </div>
        <button className="btn-primary w-full max-w-sm" onClick={() => (last ? finish() : setI(i + 1))}>
          {last ? t('Inizia') : t('Avanti')}
        </button>
      </div>
    </div>
  )
}
