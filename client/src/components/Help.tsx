import { Capacitor } from '@capacitor/core'
import { t, useLang } from '../lib/i18n'
import { APP_VERSION, Sheet } from './Legal'

/** Public issue tracker used by the in-app "Segnala un problema" button (no email needed). */
export const SUPPORT_URL = 'https://github.com/makaDv/Kursor/issues/new'

const FAQ: [string, string][] = [
  [
    'L’app non trova il PC',
    'Controlla che PadLink sia aperto sul PC (icona vicino all’orologio) e che telefono e PC siano sulla stessa rete Wi-Fi. Se il PC ha cambiato indirizzo, l’app lo ritrova da sola: tocca «Cerca il PC in rete».',
  ],
  [
    'Windows blocca il programma o chiede il firewall',
    'Al primo avvio Windows chiede di consentire l’accesso alla rete: scegli solo «Reti private». Se la tua rete è impostata come «Pubblica», cambiala in «Privata» dalle impostazioni di rete di Windows.',
  ],
  [
    'Il PC dice «Certificato cambiato»',
    'Succede se reinstalli PadLink sul PC o rigeneri i certificati. Per sicurezza l’app blocca la connessione: associa di nuovo il telefono.',
  ],
  [
    'Non riesco a controllare alcune finestre',
    'I programmi avviati come amministratore sono protetti da Windows e PadLink non può controllarli. È una protezione voluta.',
  ],
  [
    'Come accendo il PC dal telefono?',
    'Su Android, se il PC supporta il Wake-on-LAN (da attivare nel BIOS e nella scheda di rete), quando è spento compare «Accendi PC».',
  ],
  [
    'Chi può vedere cosa faccio?',
    'Nessuno oltre a te: telefono e PC parlano direttamente in modo cifrato, senza server esterni. Sul PC un’icona verde indica sempre quando un telefono è connesso.',
  ],
]

function feedbackHref(kind: 'bug' | 'idea'): string {
  const subject = kind === 'bug' ? 'PadLink: segnalazione problema' : 'PadLink: suggerimento'
  const body =
    `\n\n---\nPadLink ${APP_VERSION} · ${Capacitor.getPlatform()} · ${navigator.userAgent}\n` +
    '(Queste informazioni tecniche aiutano a capire il problema. Nessun altro dato viene inviato.)'
  return `${SUPPORT_URL}?title=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}

export default function Help({ onClose }: { onClose: () => void }) {
  useLang()
  return (
    <Sheet title={t('Aiuto')} onClose={onClose}>
      {FAQ.map(([q, a]) => (
        <details key={q} className="card mt-3 p-4 [&_p]:mt-2">
          <summary className="cursor-pointer font-medium text-gray-100">{t(q)}</summary>
          <p>{t(a)}</p>
        </details>
      ))}
      <h3>{t('Non hai trovato la risposta?')}</h3>
      <p>{t('Apri una segnalazione su GitHub: la pagina si apre già compilata con la versione dell’app.')}</p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <a className="btn-secondary" href={feedbackHref('bug')} target="_blank" rel="noopener noreferrer">
          {t('Segnala un problema')}
        </a>
        <a className="btn-secondary" href={feedbackHref('idea')} target="_blank" rel="noopener noreferrer">
          {t('Suggerisci un’idea')}
        </a>
      </div>
    </Sheet>
  )
}
