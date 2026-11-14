/**
 * In-app privacy policy, terms and open-source notices. The full texts also live
 * in docs/legal/ (the privacy URL required by the stores must host the same text).
 */
import { useState } from 'react'

export const APP_VERSION = '1.0.0'

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink-950" role="dialog" aria-modal="true" aria-label={title}>
      <header className="safe-top flex items-center justify-between border-b border-ink-800 px-4">
        <h2 className="flex h-12 items-center font-semibold">{title}</h2>
        <button className="px-2 py-2 text-accent-2" onClick={onClose}>
          Chiudi
        </button>
      </header>
      <div className="safe-bottom flex-1 overflow-y-auto p-5 text-sm leading-relaxed text-gray-300 [&_h3]:mt-5 [&_h3]:font-semibold [&_h3]:text-gray-100 [&_li]:ml-4 [&_li]:list-disc [&_p]:mt-2">
        {children}
      </div>
    </div>
  )
}

export function PrivacyText() {
  return (
    <>
      <p>
        <b>In breve: Kursor non raccoglie, non vende e non condivide alcun dato personale.</b> Non esistono account, server
        dello sviluppatore, pubblicità, analytics o SDK di terze parti.
      </p>
      <h3>Come funziona</h3>
      <p>
        L’app comunica esclusivamente con il <b>tuo</b> PC, sul quale hai installato Kursor, attraverso una connessione
        cifrata (TLS) verificata con il certificato del PC (certificate pinning). Nessun dato transita da server dello
        sviluppatore o di terzi, salvo che tu configuri volontariamente un tunnel (es. Cloudflare, WireGuard), che è un
        servizio tuo e soggetto alle sue condizioni.
      </p>
      <h3>Dati trattati, solo sui tuoi dispositivi</h3>
      <ul>
        <li>Telefono: indirizzo del PC, impronta del suo certificato, token di sessione cifrato nel Keystore/Keychain, preferenze.</li>
        <li>PC: nome del dispositivo associato, ultimo IP e orario di accesso, registro degli accessi (sicurezza), conservati sul PC.</li>
        <li>Comandi (mouse, tastiera) e immagini dello schermo viaggiano in tempo reale fra i tuoi dispositivi e non vengono salvati.</li>
      </ul>
      <h3>Permessi</h3>
      <ul>
        <li>Fotocamera: solo per leggere il QR code di associazione, elaborato sul telefono. Nessuna foto viene salvata o inviata.</li>
        <li>Rete locale: per raggiungere il PC sulla tua rete Wi-Fi.</li>
      </ul>
      <h3>Controllo e cancellazione</h3>
      <p>
        Puoi revocare un dispositivo in qualsiasi momento (app › Altro, o finestra di Kursor sul PC). Disinstallando l’app
        si cancellano tutti i dati sul telefono; disinstallando Kursor dal PC e cancellando la cartella dati si cancellano
        quelli sul PC. Lo sviluppatore non possiede copie di nessuno di questi dati.
      </p>
      <h3>Minori</h3>
      <p>L’app non è rivolta a minori di 13 anni e non raccoglie consapevolmente dati di minori.</p>
      <h3>Contatti</h3>
      <p>Per domande sulla privacy usa il contatto indicato nella scheda dello store.</p>
    </>
  )
}

function TermsText() {
  return (
    <>
      <p>
        Kursor permette di controllare <b>solo computer di tua proprietà o che sei autorizzato a gestire</b>. È vietato
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
  ['AndroidX', 'Apache-2.0'],
]

function LicensesText() {
  return (
    <>
      <p>Kursor include i seguenti componenti open source, ciascuno soggetto alla propria licenza:</p>
      <ul>
        {LICENSES.map(([name, lic]) => (
          <li key={name}>
            {name} — {lic}
          </li>
        ))}
      </ul>
      <p>I testi completi delle licenze sono disponibili nei rispettivi progetti e nel file THIRD_PARTY_NOTICES del progetto.</p>
    </>
  )
}

type Doc = 'privacy' | 'terms' | 'licenses'
const TITLES: Record<Doc, string> = { privacy: 'Privacy', terms: 'Termini d’uso', licenses: 'Licenze open source' }

export function LegalLinks({ className = '' }: { className?: string }) {
  const [open, setOpen] = useState<Doc | null>(null)
  return (
    <>
      <div className={`flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-gray-500 ${className}`}>
        {(Object.keys(TITLES) as Doc[]).map((d) => (
          <button key={d} className="underline" onClick={() => setOpen(d)}>
            {TITLES[d]}
          </button>
        ))}
      </div>
      {open && (
        <Sheet title={TITLES[open]} onClose={() => setOpen(null)}>
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
      <p>Usa Kursor solo su computer tuoi o che sei autorizzato a gestire. Nessun dato lascia i tuoi dispositivi.</p>
      <LegalLinks />
    </div>
  )
}
