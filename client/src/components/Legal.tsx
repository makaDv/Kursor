/**
 * In-app privacy policy, terms and open-source notices. The full texts also live
 * in docs/legal/ (the privacy URL required by the stores must host the same text).
 */
import { useEffect, useState } from 'react'
import { currentLang, t, useLang } from '../lib/i18n'

export const APP_VERSION = '1.0.0'

export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink-950" role="dialog" aria-modal="true" aria-label={title}>
      <header className="safe-top flex items-center justify-between border-b border-ink-800 px-4">
        <h2 className="flex h-12 items-center font-semibold">{title}</h2>
        <button className="px-2 py-2 text-accent-2" onClick={onClose}>
          {t('Chiudi')}
        </button>
      </header>
      <div className="safe-bottom flex-1 overflow-y-auto p-5 text-sm leading-relaxed text-gray-300 [&_h3]:mt-5 [&_h3]:font-semibold [&_h3]:text-gray-100 [&_li]:ml-4 [&_li]:list-disc [&_p]:mt-2">
        {children}
      </div>
    </div>
  )
}

export function PrivacyText() {
  return currentLang() === 'en' ? <PrivacyEn /> : <PrivacyIt />
}

function PrivacyIt() {
  return (
    <>
      <p>
        <b>In breve: PadLink non raccoglie, non vende e non condivide alcun dato personale.</b> Non esistono account, server
        dello sviluppatore, pubblicità, analytics o SDK di tracciamento.
      </p>
      <h3>Come funziona</h3>
      <p>
        L’app comunica esclusivamente con il <b>tuo</b> PC, sul quale hai installato PadLink, attraverso una connessione
        cifrata (TLS) verificata con il certificato del PC (certificate pinning). Nessun dato transita da server dello
        sviluppatore o di terzi, salvo che tu configuri volontariamente un tunnel (es. Cloudflare, WireGuard), che è un
        servizio tuo e soggetto alle sue condizioni.
      </p>
      <h3>Dati trattati, solo sui tuoi dispositivi</h3>
      <ul>
        <li>Telefono: indirizzi, nomi e indirizzo MAC (per l’accensione a distanza) dei PC associati, impronta dei loro certificati, token di sessione cifrati nel Keystore/Keychain, preferenze e ultime frasi digitate.</li>
        <li>PC: nome del dispositivo associato, permessi, ultimo IP e orario di accesso, registro degli accessi (sicurezza), conservati sul PC.</li>
        <li>Comandi (mouse, tastiera), immagini dello schermo, elenco delle app aperte sul PC e appunti (solo quando premi «Copia dal PC» / «Incolla sul PC») viaggiano in tempo reale fra i tuoi dispositivi e non vengono salvati.</li>
        <li>Sulla rete locale il programma PC si annuncia (mDNS) con il nome del PC e l’impronta del suo certificato, così l’app lo ritrova se cambia indirizzo. Si può disattivare dalla finestra di PadLink.</li>
      </ul>
      <h3>Permessi</h3>
      <ul>
        <li>Fotocamera: solo per leggere il QR code di associazione, elaborato sul telefono. Nessuna foto viene salvata o inviata.</li>
        <li>Rete locale: per raggiungere e ritrovare il PC sulla tua rete Wi-Fi.</li>
        <li>Impronta / volto (facoltativo): verificati dal sistema del telefono; PadLink riceve solo «riuscito» o «non riuscito».</li>
      </ul>
      <h3>Servizi dello store</h3>
      <p>
        L’app può mostrare la finestra di valutazione di Google Play o dell’App Store, gestita interamente dallo store. Se
        scrivi all’assistenza dall’app, la mail parte dal tuo programma di posta e contiene solo ciò che vedi (più versione
        dell’app e modello del telefono).
      </p>
      <h3>Controllo e cancellazione</h3>
      <p>
        Puoi revocare un dispositivo in qualsiasi momento (app › Altro, o finestra di PadLink sul PC), e il PC può revocare
        da solo i telefoni inattivi. Disinstallando l’app si cancellano tutti i dati sul telefono; disinstallando PadLink
        dal PC e cancellando la cartella dati si cancellano quelli sul PC. Lo sviluppatore non possiede copie di nessuno di
        questi dati.
      </p>
      <h3>Minori</h3>
      <p>L’app non è rivolta a minori di 13 anni e non raccoglie consapevolmente dati di minori.</p>
      <h3>Contatti</h3>
      <p>Per domande sulla privacy usa il contatto indicato nella scheda dello store.</p>
    </>
  )
}

function PrivacyEn() {
  return (
    <>
      <p>
        <b>In short: PadLink does not collect, sell or share any personal data.</b> There are no accounts, no developer
        servers, no ads, no analytics and no tracking SDKs.
      </p>
      <h3>How it works</h3>
      <p>
        The app talks only to <b>your</b> PC running PadLink, over an encrypted TLS connection verified with the PC’s
        certificate (certificate pinning). No data goes through developer or third-party servers, unless you deliberately
        set up a tunnel (e.g. Cloudflare, WireGuard), which is your own service under its own terms.
      </p>
      <h3>Data handled, only on your devices</h3>
      <ul>
        <li>Phone: addresses, names and MAC address (for remote wake-up) of the paired PCs, their certificate fingerprints, session tokens encrypted in the Keystore/Keychain, preferences and recently typed phrases.</li>
        <li>PC: paired device name, permissions, last IP and access time, security access log, stored on the PC.</li>
        <li>Commands (mouse, keyboard), screen images, the list of open apps and the clipboard (only when you tap “Copy from PC” / “Paste to PC”) travel in real time between your devices and are never stored.</li>
        <li>On the local network the PC program announces itself (mDNS) with the PC name and its certificate fingerprint, so the app finds it again after an address change. It can be turned off in the PadLink window.</li>
      </ul>
      <h3>Permissions</h3>
      <ul>
        <li>Camera: only to read the pairing QR code, processed on the phone. No photos are stored or sent.</li>
        <li>Local network: to reach and find your PC on your Wi-Fi.</li>
        <li>Fingerprint / face (optional): checked by the phone’s system; PadLink only receives “success” or “failure”.</li>
      </ul>
      <h3>Store services</h3>
      <p>
        The app may show the Google Play or App Store rating dialog, handled entirely by the store. If you contact support
        from the app, the email is sent by your mail app and contains only what you see (plus app version and phone model).
      </p>
      <h3>Control and deletion</h3>
      <p>
        You can revoke a device at any time (app › More, or the PadLink window on the PC), and the PC can automatically
        revoke inactive phones. Uninstalling the app erases all data on the phone; uninstalling PadLink from the PC and
        deleting its data folder erases the PC data. The developer holds no copy of any of this data.
      </p>
      <h3>Children</h3>
      <p>The app is not directed at children under 13 and does not knowingly collect children’s data.</p>
      <h3>Contact</h3>
      <p>For privacy questions use the contact shown on the store listing.</p>
    </>
  )
}

function TermsText() {
  if (currentLang() === 'en') {
    return (
      <>
        <p>
          PadLink lets you control <b>only computers you own or are authorised to manage</b>. Using it to access someone
          else’s computer without their explicit consent is forbidden: besides breaching these terms, it may be a crime.
        </p>
        <h3>Responsibility</h3>
        <p>
          Whoever holds a paired device can control the PC (mouse, keyboard, screen, shutdown). Keep your phone safe, do
          not share PINs or QR codes and revoke lost devices immediately. The PC always shows an indicator while a device is
          connected.
        </p>
        <p>
          The software is provided “as is”, without warranties, to the extent permitted by law. The developer is not liable
          for damage caused by misuse or by exposing the PC to the Internet without the recommended protections.
        </p>
      </>
    )
  }
  return (
    <>
      <p>
        PadLink permette di controllare <b>solo computer di tua proprietà o che sei autorizzato a gestire</b>. È vietato
        usarlo per accedere al computer di altre persone senza il loro consenso esplicito: oltre a violare questi termini,
        può costituire reato.
      </p>
      <h3>Responsabilità</h3>
      <p>
        Chi possiede un dispositivo associato può controllare il PC (mouse, tastiera, schermo, spegnimento). Custodisci il
        telefono, non condividere PIN o QR e revoca subito i dispositivi persi. Sul PC un indicatore mostra sempre quando
        un dispositivo è connesso.
      </p>
      <p>
        Il software è fornito “così com’è”, senza garanzie, nei limiti consentiti dalla legge. Lo sviluppatore non risponde
        di danni derivanti da uso improprio o dall’esposizione del PC su Internet senza le protezioni consigliate.
      </p>
    </>
  )
}

const LICENSES: [string, string][] = [
  ['React, React DOM', 'MIT'],
  ['Capacitor', 'MIT'],
  ['Tailwind CSS', 'MIT'],
  ['OkHttp, Okio (Android)', 'Apache-2.0'],
  ['ZXing, zxing-android-embedded (Android)', 'Apache-2.0'],
  ['AndroidX, Kotlin stdlib, Play In-App Review (Android)', 'Apache-2.0'],
]

function LicensesText() {
  // Full license texts (Apache-2.0 / MIT / BSD require shipping them), generated by
  // scripts/collect_licenses.py into public/licenses.txt and bundled with the app.
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    fetch('/licenses.txt')
      .then((r) => (r.ok ? r.text() : Promise.reject()))
      .then(setText)
      .catch(() => setText(null))
  }, [])
  return (
    <>
      <p>{t('PadLink include i seguenti componenti open source, ciascuno soggetto alla propria licenza:')}</p>
      <ul>
        {LICENSES.map(([name, lic]) => (
          <li key={name}>
            {name} — {lic}
          </li>
        ))}
      </ul>
      <h3>{t('Testi completi')}</h3>
      {text ? (
        <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-[11px] leading-snug text-gray-400">{text}</pre>
      ) : (
        <p>{t('Caricamento…')}</p>
      )}
    </>
  )
}

type Doc = 'privacy' | 'terms' | 'licenses'
const TITLES: Record<Doc, string> = { privacy: 'Privacy', terms: 'Termini d’uso', licenses: 'Licenze open source' }

export function LegalLinks({ className = '' }: { className?: string }) {
  useLang()
  const [open, setOpen] = useState<Doc | null>(null)
  return (
    <>
      <div className={`flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-gray-500 ${className}`}>
        {(Object.keys(TITLES) as Doc[]).map((d) => (
          <button key={d} className="underline" onClick={() => setOpen(d)}>
            {t(TITLES[d])}
          </button>
        ))}
      </div>
      {open && (
        <Sheet title={t(TITLES[open])} onClose={() => setOpen(null)}>
          {open === 'privacy' && <PrivacyText />}
          {open === 'terms' && <TermsText />}
          {open === 'licenses' && <LicensesText />}
        </Sheet>
      )}
    </>
  )
}

export function PrivacyNote() {
  return (
    <div className="flex max-w-xs flex-col items-center gap-2 text-center text-xs text-gray-500">
      <p>{t('Usa PadLink solo su computer tuoi o che sei autorizzato a gestire. Nessun dato lascia i tuoi dispositivi.')}</p>
      <LegalLinks />
    </div>
  )
}

// ---- first-run acceptance -------------------------------------------------------------
const TERMS_KEY = 'padlink.terms.v1'

export function termsAccepted(): boolean {
  try {
    return localStorage.getItem(TERMS_KEY) !== null
  } catch {
    return false
  }
}

export function TermsGate({ onAccept }: { onAccept: () => void }) {
  useLang()
  const [checked, setChecked] = useState(false)
  const accept = () => {
    try {
      localStorage.setItem(TERMS_KEY, String(Date.now()))
    } catch {
      /* storage unavailable: asked again next launch */
    }
    onAccept()
  }
  return (
    <div className="safe-top safe-bottom flex h-full flex-col items-center justify-center gap-6 overflow-y-auto px-6 py-8">
      <img src="/icons/icon.svg" alt="" className="brand-glow h-14 w-14" />
      <h1 className="text-2xl font-semibold">{t('Benvenuto in PadLink')}</h1>
      <div className="card w-full max-w-sm divide-y divide-white/5">
        {(
          [
            ['bg-accent-2', 'Cosa fa', 'Mouse, tastiera, schermo, app aperte, blocco e spegnimento del PC su cui hai installato PadLink.'],
            ['bg-warn', 'Solo PC tuoi', 'Usalo solo su computer tuoi o che sei autorizzato a gestire. Controllare il PC di altri senza consenso è vietato e può costituire reato.'],
            ['bg-ok', 'Sempre visibile', 'Sul PC un indicatore mostra sempre quando il telefono è connesso.'],
            ['bg-accent', 'Privato', 'Nessun account e nessun dato raccolto: tutto resta fra i tuoi dispositivi, cifrato.'],
          ] as const
        ).map(([dot, title, text]) => (
          <div key={title} className="flex gap-3 p-4">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot}`} />
            <div>
              <p className="text-sm font-semibold">{t(title)}</p>
              <p className="text-xs text-muted">{t(text)}</p>
            </div>
          </div>
        ))}
      </div>
      <LegalLinks />
      <label className="flex max-w-sm items-start gap-3 text-sm text-gray-300">
        <input type="checkbox" className="mt-1 h-4 w-4" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
        {t('Ho letto e accetto i Termini d’uso e l’Informativa privacy.')}
      </label>
      <button
        disabled={!checked}
        onClick={accept}
        className="btn-primary w-full max-w-sm"
      >
        {t('Continua')}
      </button>
    </div>
  )
}
