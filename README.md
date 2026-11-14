# Kursor

Controlla il tuo PC dallo smartphone: trackpad, tastiera, scorciatoie, streaming dello schermo e azioni di sistema.
Il PC deve essere acceso e raggiungibile in rete. L'app per il telefono è una **PWA**: si apre dal browser e si installa
sulla schermata Home, senza passare dagli store, su iOS e Android.

- **Server (PC):** Python 3.11+ · FastAPI · WebSocket · `mss` (cattura schermo) · `pynput` (mouse/tastiera)
- **Client (telefono):** React 18 · TypeScript · Tailwind CSS 4 · Vite. Il server stesso la serve, quindi c'è una sola origine HTTPS.

---

## Struttura

```
Kursor/
├── server/
│   ├── requirements.txt
│   └── kursor/
│       ├── __main__.py        # CLI: run, pair, devices, revoke, revoke-all, cert
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
│   ├── public/                # manifest, service worker, icone
│   └── src/
│       ├── lib/api.ts         # client HTTP con gestione dei token
│       ├── lib/socket.ts      # WebSocket autenticato con riconnessione automatica
│       └── components/        # Trackpad, Tastiera, Schermo, Sistema, Dispositivi
├── docs/                      # esempi di configurazione per Cloudflare Tunnel e WireGuard
└── scripts/make_icons.py
```

## Architettura di sicurezza

| Minaccia | Contromisura |
|---|---|
| Accesso non autorizzato | **Pairing** con PIN a 6 cifre o QR (codice casuale a 144 bit). È **monouso** e scade dopo **5 minuti**. Su disco finiscono solo gli HMAC. |
| Brute force del PIN | **Blocco per IP dopo 5 errori.** Il blocco dura 15 min e raddoppia a ogni recidiva. In più il PIN viene **distrutto dopo 5 errori totali**, da qualunque IP. Ogni risposta di errore ha un ritardo casuale. |
| Furto del token | **Access token JWT di 10 min**, tenuto solo in memoria (mai in `localStorage`). Il **refresh token** sta in un cookie `HttpOnly; Secure; SameSite=Strict; Path=/api/auth`, invisibile a JavaScript, e **ruota** a ogni uso. Se un token già usato ricompare, il server lo tratta come furto e **revoca il dispositivo**. |
| CSRF / WebSocket hijacking | Allow-list rigorosa di **Origin** sulle richieste che modificano lo stato e su ogni handshake WebSocket. Il cookie è `SameSite=Strict`. |
| DNS rebinding | Allow-list dell'header **Host** (IP LAN, `localhost`, hostname, origine del tunnel). |
| Token nei log | Sul WebSocket il token viaggia nel **primo messaggio**, mai nell'URL. Il codice QR sta nel fragment `#`, che il browser non invia al server. |
| Intercettazione | **TLS ovunque** (HTTPS/WSS) con cipher ECDHE + AEAD. In LAN si usa una **CA locale con X.509 name constraints**: anche se la sua chiave venisse rubata, potrebbe firmare solo IP privati, `localhost` e `*.local`, mai siti pubblici. |
| Esposizione su internet | Nessun port forwarding. Si passa da **Cloudflare Tunnel** (+ Cloudflare Access) oppure da **WireGuard/Tailscale**. In modalità tunnel il server ascolta solo su `127.0.0.1`. |
| Revoca | `python -m kursor revoke <id>` oppure il pulsante nell'app. Le sessioni live si chiudono entro circa 2 secondi (codice 4409). Anche gli access token ancora validi smettono subito di funzionare. |
| Azioni distruttive | Il pulsante va **tenuto premuto** per confermare. Il server richiede `confirm` uguale al nome dell'azione e accetta al massimo 1 azione ogni 5 s per dispositivo. |
| Input malevolo | Validazione di ogni comando (tipi, limiti, whitelist dei tasti) e rate limit per connessione. I pulsanti premuti vengono rilasciati alla disconnessione. |
| Audit | Log JSON-lines con rotazione in `~/.kursor/logs/access.log`: pairing, fallimenti, blocchi, refresh, riuso di token, revoche, connessioni WS e azioni di sistema. Il testo digitato non viene registrato. |
| Header | CSP restrittiva, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, HSTS, COOP. Niente docs/OpenAPI esposti. |

I dati sensibili (chiave di firma, dispositivi, CA, log) stanno in `~/.kursor` (oppure in `$KURSOR_DATA_DIR`), fuori dal repository.

---

## 1. Installazione

Prerequisiti: **Python 3.11+** e **Node.js 20+**.

```powershell
# Windows (PowerShell)
cd Kursor\server
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

cd ..\client
npm install
npm run build          # genera client/dist, servita dal server
```

```bash
# Linux / macOS
cd Kursor/server
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

Al primo avvio Kursor:
1. crea la **CA locale** e il **certificato del server** per gli IP LAN del PC (`~/.kursor/certs`);
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
3. **iOS:** Impostazioni → *Profilo scaricato* → Installa. Poi Impostazioni → Generali → Info → **Impostazioni certificati attendibili** → attiva "Kursor Local CA".
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
- **Tailscale:** installalo su PC e telefono con lo stesso account. Apri `https://<IP-100.x-del-PC>:8443`. Kursor include gli IP 100.64.0.0/10 nel certificato se il PC li espone all'avvio. Se cambia rete, riavvia Kursor.
- **WireGuard:** server sul router o su un dispositivo sempre acceso. Per il telefono vedi l'esempio [`docs/wireguard-peer.example.conf`](docs/wireguard-peer.example.conf).

### Opzione B: Cloudflare Tunnel (+ Cloudflare Access)
```powershell
winget install --id Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create kursor
cloudflared tunnel route dns kursor kursor.tuodominio.it
# configura docs/cloudflared-config.example.yml in %USERPROFILE%\.cloudflared\config.yml
```
Avvia Kursor **solo su loopback**: TLS lo termina Cloudflare e il traffico locale non lascia il PC.
```powershell
.venv\Scripts\python -m kursor run --host 127.0.0.1 --port 8080 --no-tls `
    --public-origin https://kursor.tuodominio.it --trust-proxy
cloudflared tunnel run kursor
```
**Fortemente consigliato:** nella dashboard Zero Trust crea un'applicazione **Cloudflare Access** per `kursor.tuodominio.it`, con policy *email = la tua* e OTP. Così, prima ancora di Kursor, c'è un secondo fattore.

`--no-tls` viene rifiutato se `--host` non è loopback, così non si espone per errore HTTP in chiaro sulla LAN.

## 8. Sviluppo

```powershell
# terminale 1: backend che accetta l'origine del dev server
cd server; .venv\Scripts\python -m kursor run --dev
# terminale 2: Vite con proxy verso https://localhost:8443
cd client; npm run dev
```
Dal telefono apri `http://<IP-PC>:5173`. Solo per sviluppo: niente TLS verso il telefono.

Rigenerare le icone: `server\.venv\Scripts\python scripts\make_icons.py`

## Protocollo WebSocket (riferimento)

1. Il client si connette a `/ws/control` o a `/ws/screen` e invia `{"t":"auth","token":"<JWT>"}` entro 5 s. Il server risponde con `{"t":"ready","exp":…,"monitors":[…]}`.
2. **Comandi di controllo:** `move{dx,dy}` · `abs{x,y,m}` · `click{b,n}` · `down{b}` · `up{b}` · `scroll{dx,dy}` · `text{s}` · `keys{k:[…]}` · `ping`.
3. **Comandi dello schermo:** `start{params}` · `config{params}` · `stop` · `ack{seq}`. Ogni frame binario è un header di 20 byte (`<IffHHB3x`: seq, cursore x/y normalizzati, larghezza, altezza, formato) seguito dall'immagine.
4. **Codici di chiusura:** `4401` token scaduto/non valido · `4403` origine vietata · `4408` timeout auth · `4409` dispositivo revocato · `4429` bloccato.

## Limiti noti
- Il blocco anti brute force sta in memoria: si azzera al riavvio del server. Il PIN però scade e viene distrutto dopo 5 errori, a prescindere.
- Con l'ibernazione attiva, Windows può ibernare invece di sospendere.
- La schermata di blocco/UAC di Windows (desktop sicuro) non è controllabile da un processo utente: è una scelta di sicurezza del sistema operativo.
