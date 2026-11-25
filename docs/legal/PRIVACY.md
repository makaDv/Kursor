# Informativa sulla privacy di PadLink

_Ultimo aggiornamento: 25 novembre 2026_

## In breve

**PadLink non raccoglie, non vende e non condivide alcun dato personale.** Non ci sono account, server dello sviluppatore, pubblicità, analytics, crash reporting né SDK di terze parti. Tutto resta fra il tuo telefono e il tuo PC.

## Titolare

makaDv (sviluppatore indipendente), contatto: [GitHub Issues](https://github.com/makaDv/PadLink/issues).

## Come funziona PadLink

PadLink ha due parti, entrambe sotto il tuo controllo:

1. il **programma per PC** (Windows), che installi sul computer da controllare;
2. l'**app** (Android/iOS) o la web app, che usi sul telefono.

Il telefono comunica **direttamente** con il tuo PC sulla rete locale, con una connessione cifrata (TLS 1.2+). L'app verifica l'identità del PC con il suo certificato (certificate pinning): l'impronta arriva dal QR code che scansioni, oppure la confermi con il codice di verifica. Nessun dato passa da server dello sviluppatore, perché questi server non esistono.

Se scegli di usare un tunnel (per esempio Cloudflare Tunnel o WireGuard) per raggiungere il PC da fuori casa, quel servizio è configurato e gestito da te ed è soggetto alle sue condizioni.

## Dati trattati, solo sui tuoi dispositivi

| Dove | Cosa | Perché | Per quanto |
|---|---|---|---|
| Telefono | Indirizzi, nomi e indirizzo MAC dei PC associati (il MAC serve solo per l'accensione a distanza), impronta dei loro certificati, token di sessione (cifrati nel Keystore Android o nel Keychain iOS), preferenze, ultime frasi digitate nella Tastiera | Riconnettersi ai PC in modo sicuro, comodità | Finché non disconnetti, dimentichi il PC o disinstalli l'app |
| PC | Nome del dispositivo associato, permessi, data di associazione, ultimo accesso e ultimo IP locale, hash del token di sessione | Gestire, limitare e revocare i dispositivi | Finché non revochi il dispositivo (o fino alla revoca automatica dei telefoni inattivi, se attiva) |
| PC | Hash scrypt della password del PC (mai la password in chiaro). Sul telefono la password resta solo in memoria | Chiedere la password a ogni apertura dell'app | Finché non la cambi |
| PC | Blocchi temporanei anti-tentativi (IP locale e scadenza) | Sicurezza: impedire di indovinare il PIN | Fino alla scadenza del blocco |
| PC | Registro degli accessi (associazioni, tentativi falliti, revoche, azioni di sistema, chiusura di app: solo il nome del programma, mai il titolo della finestra) | Sicurezza: rilevare abusi | File a rotazione, al massimo circa 12 MB |
| In transito | Movimenti del mouse, tasti, testo digitato, immagini dello schermo, elenco delle app e delle finestre aperte sul PC (nome del programma e titolo della finestra), testo degli appunti solo quando premi «Copia dal PC» o «Incolla sul PC» | Il controllo remoto vero e proprio | Non vengono salvati: esistono solo in tempo reale |
| Rete locale | Il programma PC si annuncia sulla rete locale (mDNS) con il nome del PC e l'impronta pubblica del suo certificato | Permettere all'app di ritrovare il PC se cambia indirizzo | Finché il programma è aperto; disattivabile dalla finestra di PadLink |

Lo sviluppatore non riceve e non possiede copie di nessuno di questi dati.

## Servizi di terzi, solo se li usi

- **Valutazione nello store**: dopo alcuni utilizzi l'app può chiedere a Google Play o all'App Store di mostrare la loro finestra di valutazione. La gestisce interamente lo store, secondo la sua privacy policy; PadLink non riceve nulla.
- **Assistenza**: «Segnala un problema» apre il tuo programma di posta con un messaggio precompilato (versione dell'app e modello del telefono). Lo invii tu, e solo se vuoi.
- **Aggiornamenti del programma PC** (quando attivi): una volta al giorno il programma scarica un piccolo file pubblico che indica l'ultima versione, senza inviare identificativi. Il server che lo ospita vede solo l'indirizzo IP pubblico, come per qualsiasi download.

## Permessi dell'app

- **Fotocamera**: solo per leggere il QR code di associazione. L'elaborazione avviene sul telefono e nessuna immagine viene salvata o trasmessa.
- **Rete / rete locale**: per raggiungere e ritrovare il PC sulla tua rete.
- **Impronta / volto** (facoltativo): la verifica la fa il sistema del telefono; PadLink riceve solo «riuscito» o «non riuscito», mai dati biometrici.

## I tuoi diritti e la cancellazione

Hai il pieno controllo dei dati, perché si trovano solo sui tuoi dispositivi:

- **revoca un dispositivo** dall'app (Altro › Dispositivi) o dalla finestra di PadLink sul PC;
- **cancella i dati del telefono** disinstallando l'app, oppure con "Disconnetti";
- **cancella i dati del PC** disinstallando PadLink ed eliminando la cartella `%USERPROFILE%\.padlink`.

Visto che non trattiamo i tuoi dati, non abbiamo nulla da esportare o cancellare per conto tuo. Per qualsiasi domanda puoi comunque aprire una segnalazione su [GitHub Issues](https://github.com/makaDv/PadLink/issues). Puoi anche presentare reclamo all'autorità di controllo (in Italia, il Garante per la protezione dei dati personali).

## Sicurezza

- Associazione con PIN o QR monouso, valido 5 minuti, con blocco dopo 5 tentativi falliti.
- Token di sessione a breve durata, ruotati a ogni uso, con rilevamento del riuso.
- Connessione sempre cifrata, con certificate pinning.
- Sul PC un indicatore segnala sempre quando un dispositivo è connesso, e il controllo si può mettere in pausa in ogni momento.

## Minori

PadLink non è rivolto a minori di 13 anni e non raccoglie consapevolmente dati di minori.

## Modifiche

Eventuali modifiche a questa informativa saranno pubblicate a questo indirizzo e indicate nelle note di versione dell'app.

---

# PadLink Privacy Policy (English)

_Last updated: 25 November 2026_

**PadLink does not collect, sell or share any personal data.** There are no accounts, no developer servers, no ads, no analytics, no crash reporting and no third-party SDKs.

**How it works.** The phone app talks **directly** to the PadLink program on *your* PC over your local network, through an encrypted TLS connection authenticated by certificate pinning (the PC's fingerprint comes from the pairing QR code, or you confirm it with a verification code). Nothing passes through developer servers, because there are none. If you choose to set up a tunnel (for example Cloudflare or WireGuard), that service is yours and subject to its own terms.

**Data stored on your devices only.**
- *Phone:* the PC address, its certificate fingerprint, a session token (encrypted in the Android Keystore or iOS Keychain) and your preferences.
- *PC:* the paired device name, pairing date, last access time and local IP, a hash of the session token, a scrypt hash of the PC password (never the password itself; on the phone it is kept only in memory), and a rotating security access log (about 12 MB at most).
- *Never stored:* mouse movements, keystrokes, typed text, screen images and the list of open apps/windows (program name and window title). They exist only in real time between your devices.

**Third-party services, only if you use them.** The store may show its own rating dialog; “Report a problem” opens your mail app with a pre-filled message you choose to send; the PC program, when update checks are enabled, downloads a small public version file once a day without identifiers.

**Permissions.**
- *Camera:* used only to read the pairing QR code, on the device. No images are stored or sent.
- *Local network:* used to reach and find your PC (the PC announces its name and public certificate fingerprint via mDNS; can be turned off).
- *Fingerprint / face (optional):* checked by the phone’s system; PadLink only gets “success” or “failure”.

**Control and deletion.**
- Revoke a device from the app or from the PC window.
- Uninstall the app to erase the phone data.
- Uninstall PadLink and delete `%USERPROFILE%\.padlink` to erase the PC data.

The developer holds no copy of any of this data.

**Children.** PadLink is not directed at children under 13.

**Contact.** makaDv, [GitHub Issues](https://github.com/makaDv/PadLink/issues).
