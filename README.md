# PadLink

Controlla il tuo PC dallo smartphone: trackpad, tastiera, scorciatoie, streaming dello schermo e azioni di sistema.

| Parte | Cosa | Dove |
|---|---|---|
| **PC (Windows)** | Programma con icona nell'area di notifica, finestra di associazione (QR/PIN), indicatore "telefono connesso", pausa, revoca. Installer `.exe`. | `server/` · `packaging/windows/` |
| **App Android** | Google Play · Capacitor 8.6 + plugin nativo (pinning, Keystore, scanner QR) | `client/android/` |
| **App iOS** | App Store · stesso codice + plugin Swift (pinning, Keychain, scanner QR) | `client/ios/` |
| **PWA** | Dal browser, senza store (richiede di installare la CA sul telefono) | `client/` |

- **Server (PC):** Python 3.11+ · FastAPI · WebSocket · `mss` (cattura schermo) · `pynput` (mouse/tastiera) · tkinter + `pystray` (app desktop)
- **Client:** React 18 · TypeScript · Tailwind CSS 4 · Vite · Capacitor 8.6

**Pubblicazione sugli store** (Data safety, App Privacy, note per la revisione, firma): vedi [`docs/store/PUBLISHING.md`](docs/store/PUBLISHING.md).
Privacy, termini e licenze: [`docs/legal/`](docs/legal/).

---

## Struttura

```
PadLink/
├── server/
│   ├── requirements.txt
│   └── kursor/
│       ├── __main__.py        # CLI: run, desktop, pair, devices, revoke, revoke-all, cert
│       ├── desktop.py         # app Windows: tray, finestra QR/PIN, indicatore connessione, pausa, consenso
│       ├── runtime.py         # bootstrap del server condiviso fra CLI e app desktop
│       ├── pairinfo.py        # link di pairing (codice + impronta della CA per il pinning)
│       ├── app.py             # FastAPI: auth, dispositivi, azioni di sistema, hosting PWA, header di sicurezza
│       ├── ws.py              # WebSocket /ws/control (input) e /ws/screen (streaming adattivo)
│       ├── services.py        # wiring dei componenti + registro delle connessioni live
│       ├── certs.py           # CA locale con name constraints + certificato server per la LAN
│       ├── config.py, netutil.py, fsutil.py, logging_setup.py
│       ├── security/
│       │   ├── pairing.py     # PIN a 6 cifre + codice QR, monouso, scadenza 5 min
│       │   ├── tokens.py      # JWT di accesso HS256 (10 min)
│       │   ├── store.py       # dispositivi + refresh token ruotati (solo hash su disco)
│       │   ├── ratelimit.py   # blocco dopo 5 tentativi falliti, token bucket
│       │   └── origin.py      # allow-list di Host e Origin
│       └── control/
│           ├── input.py       # mouse/tastiera con validazione rigorosa
│           ├── screen.py      # cattura e codifica JPEG/WebP
│           └── system.py      # blocco, sospensione, spegnimento
├── client/
│   ├── android/               # progetto Android Studio (Capacitor)
│   ├── ios/                   # progetto Xcode (Capacitor, Swift Package Manager)
│   ├── native/kursor-native/  # plugin nativo: HTTPS/WSS con pinning, Keystore/Keychain, scanner QR
│   ├── public/                # manifest, service worker, icone
│   └── src/
│       ├── lib/api.ts         # client HTTP con gestione dei token
│       ├── lib/transport.ts   # fetch/WebSocket (PWA) oppure plugin nativo (app)
│       ├── lib/socket.ts      # WebSocket autenticato con riconnessione automatica
│       └── components/        # Pairing, Trackpad, Tastiera, Schermo, Sistema, Dispositivi, Legal
├── packaging/windows/         # PyInstaller (.spec) + Inno Setup (.iss) + build.ps1
├── .github/workflows/         # build.yml: Android / iOS / Windows (avvio manuale)
├── docs/
│   ├── legal/                 # PRIVACY, TERMS, THIRD_PARTY_NOTICES
│   ├── store/PUBLISHING.md    # checklist e risposte per Google Play / App Store / Microsoft Store
│   └── *.example.*            # Cloudflare Tunnel e WireGuard
└── scripts/make_icons.py      # icone PWA, Android, iOS, Windows
```

## Architettura di sicurezza

| Minaccia | Contromisura |
|---|---|
| Accesso non autorizzato | **Pairing** con PIN a 6 cifre o QR (codice casuale a 144 bit). È **monouso** e scade dopo **5 minuti**. Su disco finiscono solo gli HMAC. |
| Password del PC | Oltre al pairing serve una **password scelta sul PC**, chiesta dall'app **a ogni apertura** (e dopo 5 minuti in background). Sul PC resta solo un hash **scrypt** (`password.json`); sul telefono la password vive solo in memoria. Si verifica durante il refresh, prima di ruotare il token: una password sbagliata non consuma la sessione, ma conta nel blocco per IP e, dopo **10 errori**, revoca il telefono. Cambiarla chiude le sessioni attive e invalida gli access token (claim `pwv`). |
| Brute force del PIN | **Blocco per IP dopo 5 errori**, salvato su disco (`lockouts.json`), quindi resta anche se il programma viene riavviato. Il blocco dura 15 min e raddoppia a ogni recidiva. In più il PIN viene **distrutto dopo 5 errori totali**, da qualunque IP. Ogni risposta di errore ha un ritardo casuale. |
| Furto del token | **Access token JWT di 10 min**, tenuto solo in memoria (mai in `localStorage`). Il **refresh token** sta in un cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/auth`, invisibile a JavaScript, e **ruota** a ogni uso. Se un token già usato ricompare, il server lo tratta come furto e **revoca il dispositivo**. |
| CSRF / WebSocket hijacking | Allow-list rigorosa di **Origin** sulle richieste che modificano lo stato e su ogni handshake WebSocket. Il cookie è `SameSite=Strict`. |
| DNS rebinding | Allow-list dell'header **Host** (IP LAN, `localhost`, hostname, origine del tunnel). |
| Token nei log | Sul WebSocket il token viaggia nel **primo messaggio**, mai nell'URL. Il codice QR sta nel fragment `#`, che il browser non invia al server. |
| Intercettazione | **TLS ovunque** (HTTPS/WSS) con cipher ECDHE + AEAD. In LAN si usa una **CA locale con X.509 name constraints**: anche se la sua chiave venisse rubata, potrebbe firmare solo IP privati, `localhost` e `*.local`, mai siti pubblici. |
| MITM sull'app | **Certificate pinning**: il QR contiene l'impronta SHA-256 della CA del PC (`#pair=…&fp=…`) e l'app accetta *solo* quella come radice. Le CA di sistema e quelle installate dall'utente vengono ignorate. Senza QR, l'app mostra un **codice di verifica** (`XXXX-XXXX-XXXX`, 48 bit) da confrontare con quello sul PC. Se il certificato cambia, l'app blocca la connessione prima di inviare qualsiasi token. Sul telefono non si installa nulla. |
| Esposizione accidentale | Il server accetta **solo** client della rete locale (IP privati), di VPN (range CGNAT di Tailscale) o di un tunnel locale (`127.0.0.1`). Se il PC finisce esposto su Internet per errore (port forwarding, UPnP, DMZ), le richieste da IP pubblici vengono rifiutate (HTTP 403 `lan_only`, WS 4403) e registrate. |
| Visione dello schermo | Quando un telefono guarda lo schermo, la finestra del PC lo dice esplicitamente ("Sta guardando lo schermo: …") e compare una notifica. |
| XSS nelle app | CSP anche nelle app native (meta inserito in build da `vite.config.ts`). Nessun `eval` o script inline. Dipendenze verificate con `npm audit` e `pip-audit`. |
| Permessi per dispositivo | Dalla finestra del PC ogni telefono può essere limitato: schermo, app, appunti, spegnimento. Il server li applica a ogni richiesta (HTTP 403 `no_permission`, WS 4403). Mouse e tastiera restano sempre consentiti. |
| Conferma sul PC | Opzione «Chiedi conferma qui sul PC»: alla prima connessione di ogni sessione compare *Consenti / Rifiuta*. La richiesta scade in 30 s, e un rifiuto chiude con WS 4403 `denied`. |
| Notifiche delle azioni | Blocco, sospensione, spegnimento, chiusura o terminazione di programmi e lettura degli appunti mostrano sul PC una notifica con il nome del telefono. |
| Telefoni dimenticati | Revoca automatica dei dispositivi non usati da 30, 90 o 180 giorni (impostazione sul PC, default 90). |
| Telefono rubato | Sblocco facoltativo dell'app con impronta o volto, che è richiesta di default anche per spegnere e terminare. |
| Aggiornamenti | Controllo giornaliero facoltativo di una nuova versione, con manifest firmato **Ed25519** (`server/kursor/updates.py`): un sito compromesso non può annunciare aggiornamenti falsi. |
| Rete pubblica | Se Windows classifica la rete come «Pubblica», la finestra di PadLink mostra un avviso. |
| Uso occulto | **Nessuna modalità nascosta.** L'icona nel tray è sempre visibile, diventa verde e mostra una notifica quando un telefono si connette. La finestra indica chi sta controllando il PC. **Pausa** (codice 4423) e revoca sono a un clic. Al primo avvio c'è una schermata di consenso, e l'avvio automatico è facoltativo. |
| Esposizione su internet | Nessun port forwarding. Si passa da **Cloudflare Tunnel** (+ Cloudflare Access) oppure da **WireGuard/Tailscale**. In modalità tunnel il server ascolta solo su `127.0.0.1`. |
| Revoca | `python -m kursor revoke <id>` oppure il pulsante nell'app. Le sessioni live si chiudono entro circa 2 secondi (codice 4409). Anche gli access token ancora validi smettono subito di funzionare. |
| Azioni distruttive | Il pulsante va **tenuto premuto** per confermare. Il server richiede `confirm` uguale al nome dell'azione e accetta al massimo 1 azione ogni 5 s per dispositivo. |
| Input malevolo | Validazione di ogni comando (tipi, limiti, whitelist dei tasti) e rate limit per connessione. I pulsanti premuti vengono rilasciati alla disconnessione. |
| Audit | Log JSON-lines con rotazione in `~/.padlink/logs/access.log`: pairing, fallimenti, blocchi, refresh, riuso di token, revoche, connessioni WS e azioni di sistema. Il testo digitato non viene registrato. |
| Header | CSP restrittiva, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, HSTS, COOP. Niente docs/OpenAPI esposti. |

I dati sensibili (chiave di firma, dispositivi, CA, log) stanno in `~/.padlink` (oppure in `$KURSOR_DATA_DIR`), fuori dal repository.

---

## 0. Programma per PC (utenti finali)

Scarica `PadLink-Setup-x.y.z.exe` e installalo: non servono diritti di amministratore. Al primo avvio:
1. accetta i termini (schermata di benvenuto);
2. Windows chiede l'accesso alla rete: **consenti solo le reti private**;
3. premi **Associa un nuovo telefono** e inquadra il QR con l'app PadLink.

Chiudendo la finestra PadLink resta nell'area di notifica (icona vicino all'orologio). Dal menu dell'icona: Apri, Associa, **Pausa controllo**, Esci.
Da sorgente: `cd server; .venv\Scripts\python -m kursor desktop`. Build dell'installer: `packaging\windows\build.ps1` (vedi `docs/store/PUBLISHING.md` per la firma).

## 1. Installazione

Prerequisiti: **Python 3.11+** e **Node.js 20+**.

```powershell
# Windows (PowerShell)
cd PadLink\server
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

cd ..\client
npm install
npm run build          # genera client/dist, servita dal server
```

```bash
# Linux / macOS
cd PadLink/server
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd ../client && npm install && npm run build
```

> **Linux:** `pynput` richiede una sessione X11. Su Wayland la cattura e l'input sono limitati.
> **macOS:** concedi a Terminale/Python i permessi *Accessibilità* e *Registrazione schermo* (Impostazioni → Privacy e sicurezza).

## 2. Avvio del server

```powershell
cd server
.venv\Scripts\python -m kursor run
```

Al primo avvio PadLink:
1. crea la **CA locale** e il **certificato del server** per gli IP LAN del PC (`~/.padlink/certs`);
2. stampa l'**URL** (es. `https://192.168.1.10:8443`), l'impronta SHA-256 della CA, un **PIN** e un **QR code**.

Consenti l'accesso quando Windows Firewall lo chiede, **solo per le reti private**.

Opzioni utili: `--port 8443`, `--no-pair` (non genera il PIN all'avvio), `--log-level DEBUG`.

## 3. Certificati locali (HTTPS in LAN)

I certificati si generano da soli a `run`. Puoi anche gestirli a mano:

```powershell
.venv\Scripts\python -m kursor cert           # crea o rinnova (il certificato server si rinnova se cambia l'IP)
.venv\Scripts\python -m kursor cert --force   # rigenera anche la CA (poi va reinstallata sul telefono)
```

**Installa la CA sul telefono una sola volta.** Serve per una connessione fidata, senza avvisi, e per installare la PWA.

1. Dal telefono, sulla stessa Wi-Fi, apri `https://<IP-del-PC>:8443/ca.crt`. Accetta l'avviso del browser solo per questo download.
2. Prima di fidarti, confronta l'impronta SHA-256 mostrata dal telefono con quella stampata nel terminale.
3. **iOS:** Impostazioni → *Profilo scaricato* → Installa. Poi Impostazioni → Generali → Info → **Impostazioni certificati attendibili** → attiva "PadLink Local CA".
   **Android:** Impostazioni → Sicurezza → Crittografia e credenziali → Installa un certificato → **Certificato CA** → scegli `kursor-ca.crt`.
   (Chrome per Android usa i certificati utente. Alcune versioni potrebbero comunque mostrare un avviso: in quel caso usa Tailscale o il tunnel.)

## 4. Collegare il telefono

1. Telefono e PC sulla **stessa rete** (oppure in VPN, vedi sotto).
2. **Inquadra il QR** con la fotocamera, oppure apri l'URL e digita il **PIN a 6 cifre**.
3. Installa la PWA: **iOS** Safari → Condividi → *Aggiungi alla schermata Home*. **Android** Chrome → ⋮ → *Installa app*.

Il PIN scade dopo 5 minuti ed è monouso. Per associare un altro dispositivo, con il server avviato:

```powershell
.venv\Scripts\python -m kursor pair
```

## 5. Gestione dei dispositivi

```powershell
.venv\Scripts\python -m kursor devices          # elenco
.venv\Scripts\python -m kursor revoke 3fa2      # revoca per ID o prefisso univoco
.venv\Scripts\python -m kursor revoke-all       # revoca tutto e ruota la chiave di firma
.venv\Scripts\python -m kursor password         # imposta o cambia la password del PC (anche dalla finestra di PadLink)
```

Puoi vedere e revocare i dispositivi anche dall'app (scheda **Altro**).

## 6. Uso

| Scheda | Funzioni |
|---|---|
| **Trackpad** | 1 dito muove · tap = click · 2 dita = scroll · tap a 2 dita = click destro · tap a 3 dita = click centrale · tieni premuto = trascina · pulsanti S/C/D · blocco trascinamento |
| **Tastiera** | Digitazione live (gestisce l'autocorrezione) oppure invio di un blocco di testo · Ctrl/Alt/Shift/Win "sticky" · Esc, Tab, frecce, F1–F12 · scorciatoie (Alt+Tab, copia/incolla, Win+D, Task Manager…) · tasti multimediali |
| **Schermo** | Streaming JPEG/WebP · FPS, qualità e risoluzione regolabili · **qualità adattiva** (backpressure basata sugli ACK) · modalità *Tocco* (tap = click nel punto, pressione lunga = click destro) o *Trackpad* · selezione del monitor · schermo intero |
| **Sistema** | Blocca · Sospendi · Spegni (conferma tenendo premuto) |
| **Altro** | Sensibilità, accelerazione, scroll naturale · dispositivi associati · disconnessione |

## 7. Accesso da internet (senza port forwarding)

**Non** aprire la porta 8443 sul router. Scegli una di queste opzioni.

### Opzione A: Tailscale / WireGuard (consigliata, la più semplice)
- **Tailscale:** installalo su PC e telefono con lo stesso account e avvialo **prima** di PadLink: l'IP 100.x finisce nel certificato e nel QR (`&ts=100.x.y.z`). Fuori casa l'app passa da sola all'indirizzo Tailscale, con lo stesso certificato fissato (pinning). Se Tailscale parte dopo PadLink, riavvia PadLink: l'app impara l'indirizzo Tailscale alla prima connessione successiva.
- **Firewall:** da PowerShell come amministratore, `powershell -ExecutionPolicy Bypass -File scripts\firewall.ps1`. Apre la porta 8443 solo alla rete locale (profilo Privato) e a 100.64.0.0/10 (Tailscale), mai a Internet.
- La password del PC resta obbligatoria anche via Tailscale.
- **WireGuard:** server sul router o su un dispositivo sempre acceso. Per il telefono vedi l'esempio [`docs/wireguard-peer.example.conf`](docs/wireguard-peer.example.conf).

### Opzione B: Cloudflare Tunnel (+ Cloudflare Access)
```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create kursor
cloudflared tunnel route dns kursor kursor.tuodominio.it
# configura docs/cloudflared-config.example.yml in %USERPROFILE%\.cloudflared\config.yml
```
Avvia PadLink **solo su loopback**: TLS lo termina Cloudflare e il traffico locale non lascia il PC.
```powershell
.venv\Scripts\python -m kursor run --host 127.0.0.1 --port 8080 --no-tls `
    --public-origin https://kursor.tuodominio.it --trust-proxy
cloudflared tunnel run kursor
```
**Fortemente consigliato:** nella dashboard Zero Trust crea un'applicazione **Cloudflare Access** per `kursor.tuodominio.it`, con policy *email = la tua* e OTP. Così, prima ancora di PadLink, c'è un secondo fattore.

`--no-tls` viene rifiutato se `--host` non è loopback, così non si espone per errore HTTP in chiaro sulla LAN.

## 8. App Android e iOS (store)

Le app native nascono dallo stesso codice React con [Capacitor](https://capacitorjs.com) 8.6. **Tutto il traffico verso il PC passa dal plugin nativo `client/native/kursor-native`**, non dalla WebView: così il certificato del PC viene verificato con il pinning e sul telefono non serve installare nulla.

| | PWA | App Android | App iOS |
|---|---|---|---|
| Rete | fetch/WebSocket del browser | OkHttp, pinning della CA del PC | URLSession, pinning della CA del PC |
| Fiducia TLS | CA installata sul telefono | impronta dal QR o codice di verifica; CA utente **non** accettate | uguale ad Android |
| Refresh token | cookie `HttpOnly` | Android Keystore (AES-256-GCM), backup disattivato | Keychain `ThisDeviceOnly` |
| Scanner QR | fotocamera di sistema | ZXing (offline, niente Google ML Kit) | AVFoundation |
| Reti | LAN o tunnel | LAN o tunnel | **solo LAN** (App Store Guideline 4.2.7) |

Per rifiutare le app e accettare solo la PWA, avvia il server con `--no-app`.

### Sviluppo
```powershell
cd client
npm run build; npx cap sync      # copia il web e collega il plugin nativo in android/ e ios/
npx cap open android             # Android Studio, poi ▶
```
- APK di debug da riga di comando: `cd client\android; .\gradlew assembleDebug`.
- APK release firmato (consigliato anche per uso personale: il debug è `debuggable`): crea `client\android\keystore.properties` (`storeFile`, `storePassword`, `keyAlias`, `keyPassword`; è in `.gitignore`), poi `.\gradlew assembleRelease` e `adb install -r app\build\outputs\apk\release\app-release.apk`.
- Se sposti la cartella del progetto, riesegui `npm install` in `client`: il plugin `kursor-native` è un link locale e `npx cap sync` non lo trova più.
- iOS richiede macOS + Xcode (`npx cap open ios`) oppure la CI: `gh workflow run build.yml -f targets=ios` compila il progetto senza firma.
- Icone e splash (PWA, Android, iOS, Windows): `server\.venv\Scripts\python scripts\make_icons.py`.

### Pubblicazione
Tutti i passaggi sono in **[`docs/store/PUBLISHING.md`](docs/store/PUBLISHING.md)**: appId definitivo, firma, Data safety ("nessun dato raccolto"), App Privacy ("Data Not Collected"), note per i revisori, scheda dello store, firma del programma Windows.

## 9. Sviluppo web

```powershell
# terminale 1: backend che accetta l'origine del dev server
cd server; .venv\Scripts\python -m kursor run --dev
# terminale 2: Vite con proxy verso https://localhost:8443
cd client; npm run dev
```
Dal telefono apri `http://<IP-PC>:5173`. Solo per sviluppo: niente TLS verso il telefono.

Rigenerare le icone: `server\.venv\Scripts\python scripts\make_icons.py`

## App aperte sul PC (scheda "App")

`GET /api/windows` elenca le finestre visibili nella barra delle applicazioni (programma, titolo, stato).
`POST /api/windows/{id}/{azione}` con azione `focus` · `minimize` · `maximize` · `restore` · `close` · `kill`.
- `close` equivale a premere la X: il programma può chiedere di salvare. `kill` è la chiusura forzata. Entrambe richiedono `{"confirm":"<azione>"}`, e nell'app vanno confermate tenendo premuto.
- Ogni azione verifica di nuovo che l'handle sia una finestra dell'elenco, quindi non si possono colpire finestre nascoste o di sistema. I processi di sistema (`explorer.exe`, `dwm.exe`, `csrss.exe`, …) non possono essere terminati.
- I programmi avviati come amministratore non sono controllabili da PadLink, che gira senza privilegi: è una protezione di Windows (UIPI).
- Il registro degli accessi annota azione e nome del programma, mai il titolo della finestra.

## Protocollo WebSocket (riferimento)

1. Il client si connette a `/ws/control` o a `/ws/screen` e invia `{"t":"auth","token":"<JWT>"}` entro 5 s. Il server risponde con `{"t":"ready","exp":…,"monitors":[…]}`.
2. **Comandi di controllo:** `move{dx,dy}` · `abs{x,y,m}` · `click{b,n}` · `down{b}` · `up{b}` · `scroll{dx,dy}` · `text{s}` · `keys{k:[…]}` · `ping`.
3. **Comandi dello schermo:** `start{params}` · `config{params}` · `stop` · `ack{seq}`. Ogni frame binario è un header di 20 byte (`<IffHHB3x`: seq, cursore x/y normalizzati, larghezza, altezza, formato) seguito dall'immagine.
4. **Codici di chiusura:** `4401` token scaduto/non valido · `4403` origine vietata, `denied` (rifiutato sul PC) o `no_permission` · `4408` timeout auth · `4409` dispositivo revocato · `4423` controllo in pausa sul PC · `4429` bloccato.
5. **Messaggi aggiuntivi:** `{"t":"approval_pending"}` mentre il PC chiede conferma; `ready` include `perms` (permessi) e `pc` (nome e MAC per il Wake-on-LAN).

## Funzioni per l'utente

- **App:** più PC con selettore nell'intestazione; ritrova il PC via mDNS (`_padlink._tcp`) se cambia IP; Wake-on-LAN (Android); scheda App con icone vere; appunti telefono ↔ PC su richiesta; frasi recenti; controlli per presentazioni; tasti del volume del telefono come volume del PC (Android); pulsanti per mancini; tema chiaro/scuro/automatico; dimensione del testo; italiano e inglese; guida iniziale; Aiuto e FAQ con «Segnala un problema»; scorciatoie dal launcher (Android) e azioni rapide (iOS); richiesta di valutazione dopo 3 sessioni riuscite.
- **Programma PC:** italiano o inglese in base alla lingua di Windows (`PADLINK_LANG=it|en` per forzarla); permessi per telefono; conferma delle connessioni; revoca automatica degli inattivi; annuncio mDNS disattivabile; avviso di rete pubblica; notifiche delle azioni.

## Test

```powershell
cd server
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q tests
```
Le suite in `server/tests/suites` provano tutto end-to-end su server reali: autenticazione, pinning, pausa, finestre, permessi, conferma, appunti, blocchi e mDNS. La CI (`gh workflow run build.yml -f targets=test`) le esegue insieme a `pip-audit` e `npm audit`. Dependabot propone ogni settimana gli aggiornamenti di sicurezza.

## Limiti noti
- Windows 11 con Smart App Control blocca `PadLink.exe` se non è firmato: per distribuirlo serve la firma del codice oppure il Microsoft Store (vedi `docs/store/PUBLISHING.md`).
- Il programma per PC esiste solo per Windows. Il server gira anche su macOS e Linux, ma senza la scheda App, gli appunti e il pacchetto di installazione.
- Wake-on-LAN e tasti del volume del telefono funzionano solo su Android: su iPhone servirebbero un entitlement Apple o API non pubbliche.
- Con l'ibernazione attiva, Windows può ibernare invece di sospendere.
- La schermata di blocco/UAC di Windows (desktop sicuro) non è controllabile da un processo utente: è una scelta di sicurezza del sistema operativo.
