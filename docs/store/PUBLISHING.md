# Pubblicare Kursor sugli store

Checklist per Google Play, Apple App Store e la distribuzione del programma Windows, con le risposte pronte per i questionari sulla privacy.

> Questi documenti sono una base tecnica accurata, **non una consulenza legale**. Prima di una pubblicazione commerciale, fai rivedere Termini e Privacy da un professionista.

---

## 0. Prima di tutto (una volta sola)

| Cosa | Dove | Note |
|---|---|---|
| Identificativo definitivo dell'app | `client/capacitor.config.ts` (`appId`), `client/android/app/build.gradle`, progetto Xcode | Oggi è `io.github.makadv.kursor`. **Non si può più cambiare dopo la prima pubblicazione.** Se hai un dominio, usa `tuodominio.kursor`. |
| Nome e contatto | `docs/legal/PRIVACY.md`, `docs/legal/TERMS.md` | Sostituisci `[NOME / RAGIONE SOCIALE]` e `[EMAIL DI CONTATTO]`. Usa un'email dedicata. |
| URL pubblico della privacy | Obbligatorio per entrambi gli store | Il repository è privato, quindi pubblica **solo** `PRIVACY.md`, per esempio con Google Sites, Notion pubblico o un repository pubblico separato che contenga solo quel file. |
| Verifica del marchio "Kursor" | EUIPO / UIBM / USPTO | Controlla che il nome non sia già registrato nella classe 9 (software). |
| Account sviluppatore | Google Play Console (25 $ una tantum), Apple Developer Program (99 $/anno) | Per Google Play da privato servono verifica dell'identità e 12 tester per 14 giorni prima della produzione. |

---

## 1. Google Play (Android)

### Build firmata
1. Crea la chiave di upload. **Conservala fuori dal repository** e fanne un backup:
   `keytool -genkeypair -v -keystore kursor-upload.jks -keyalg RSA -keysize 4096 -validity 10000 -alias upload`
2. Android Studio › Build › Generate Signed App Bundle › `.aab`. Attiva **Play App Signing**: Google custodisce la chiave di firma, tu tieni solo quella di upload.
3. Aumenta `versionCode` e `versionName` in `client/android/app/build.gradle` a ogni rilascio.

### Sicurezza dei dati (Data safety): risposte
- **La tua app raccoglie o condivide uno dei tipi di dati utente richiesti?** → **No.**
  Motivazione: i dati (indirizzo del PC, token cifrato, comandi, immagini dello schermo) restano sul dispositivo o viaggiano solo fra il telefono e il PC dell'utente. Per la definizione di Google, i dati che lasciano il dispositivo verso un server **controllato dall'utente stesso** non sono "raccolti" dallo sviluppatore.
- **I dati sono criptati in transito?** → Sì (TLS 1.2+, certificate pinning).
- **È possibile richiedere la cancellazione dei dati?** → Non si applica: non esistono dati sui server dello sviluppatore. Basta disinstallare l'app.
- **SDK di terze parti che raccolgono dati:** nessuno. Lo scanner QR usa ZXing (offline), **non** Google ML Kit.

### Altre dichiarazioni
- **Permessi:** `CAMERA` serve solo allo scanner QR. Non ci sono permessi sensibili soggetti a dichiarazione (niente Accessibility, niente SMS, niente posizione).
- **Classificazione dei contenuti (IARC):** utility, nessun contenuto sensibile, quindi PEGI 3 / Everyone.
- **Pubblico di destinazione:** 18+ (oppure 13+). Non selezionare fasce per bambini.
- **Accesso all'app per la revisione:** "Sono necessarie istruzioni speciali". Incolla le istruzioni della sezione 4.
- **Annunci:** No.
- **App governativa / finanziaria / sanitaria:** No.

---

## 2. Apple App Store (iOS)

### Requisiti
- Un Mac con Xcode 16+, **oppure** la CI: il workflow `.github/workflows/build.yml` (job `ios`) compila senza firma; per l'upload servono i certificati (vedi sotto).
- In Xcode: Signing & Capabilities › Team, Bundle Identifier = `appId`.
- Product › Archive › Distribute App › App Store Connect.

### Guideline da rispettare (già gestite nel codice)
| Guideline | Come la rispettiamo |
|---|---|
| **4.2.7 Remote Desktop Clients**: solo PC dell'utente, host e client sulla stessa rete locale | L'app iOS accetta **solo indirizzi LAN** (`LAN_ONLY` in `client/src/lib/platform.ts`). Niente tunnel su iOS. Nessun account, tutto si gestisce dal PC. |
| 2.1 Completezza | La revisione richiede un PC: fornisci un **video dimostrativo** e istruzioni (sezione 4). |
| 5.1.1 Privacy / permessi | Testi chiari per fotocamera e rete locale in `Info.plist`. Privacy policy nell'app (Altro › Privacy). |
| 5.1.2 Uso dei dati | Nessun tracciamento: `PrivacyInfo.xcprivacy` dichiara che non viene raccolto nessun dato. |
| Export compliance | `ITSAppUsesNonExemptEncryption = false`: si usa solo il TLS standard del sistema (esente). |

### Privacy dell'app (App Store Connect › App Privacy)
- **Do you or your third-party partners collect data from this app?** → **No, we do not collect data from this app.**
  L'etichetta risultante è **"Data Not Collected"**.

### Firma in CI (quando vorrai)
Aggiungi ai *secrets* del repository: `IOS_DIST_CERT_P12` (base64), `IOS_DIST_CERT_PASSWORD`, `IOS_PROFILE` (base64), `APPSTORE_API_KEY_ID`, `APPSTORE_API_ISSUER_ID`, `APPSTORE_API_KEY_P8`. Poi estendi il job `ios` con `xcodebuild archive` + `-exportArchive` + `xcrun altool --upload-app`.

---

## 3. Programma Windows (il "lato PC")

Gli utenti dello store devono poter scaricare il programma per il PC. Senza di lui l'app non fa nulla, e va scritto nella descrizione.

### Firma del codice: obbligatoria nella pratica
Windows 11 con **Smart App Control** attivo **blocca** gli eseguibili non firmati (verificato su questo PC: `Kursor.exe` non firmato viene bloccato). Hai due strade:

1. **Microsoft Store (consigliato).** Lo store firma l'app: niente certificato da comprare e nessun avviso SmartScreen. Account sviluppatore individuale gratuito (2025+). Si pubblica come `.exe` o MSI (Win32) indicando l'URL dell'installer, oppure come MSIX.
2. **Firma Authenticode tua.** Azure Trusted Signing (circa 10 $/mese, richiede verifica dell'identità) oppure un certificato OV/EV da una CA. Firma sia `Kursor.exe` sia `Kursor-Setup-*.exe` (comando in `packaging/windows/build.ps1`).

### Build
`powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1` produce `dist\Kursor\` e, se Inno Setup 6 è installato, `dist\Kursor-Setup-1.0.0.exe`.

### Cosa fa l'installer (trasparenza)
- Installa per l'utente corrente, **senza diritti di amministratore**.
- Mostra i Termini d'uso da accettare. Al primo avvio compare anche una schermata di consenso.
- L'avvio automatico è facoltativo e disattivato di default.
- La disinstallazione rimuove tutto e chiede se cancellare anche i dati.
- Firewall: Windows chiede l'autorizzazione al primo avvio. **Consenti solo le reti private.**

---

## 4. Istruzioni per i revisori (copia nei campi "Review notes" / "App access")

```
Kursor is a remote control for the user's OWN Windows PC (mouse, keyboard,
screen view), similar to a wireless trackpad. It needs the free companion
program installed on the PC: <URL DOWNLOAD PROGRAMMA PC>.

No account, no sign-in, no data collected. Phone and PC talk directly over
the local network through TLS with certificate pinning.

How to test:
1. On a Windows 10/11 PC on the same Wi-Fi, install and open Kursor.
2. Press "Associa un nuovo telefono" (Pair a new phone): a QR code appears.
3. In the app tap "Scansiona il QR code" and scan it.
4. Use Trackpad / Tastiera (Keyboard) / Schermo (Screen) tabs.

Demo video: <URL VIDEO 1-2 MINUTI>

The PC always shows a visible tray indicator and a notification when a
phone is connected; the user can pause or revoke access at any time.
iOS build: connects only to PCs on the same local network (Guideline 4.2.7).
```

Registra un video di 1-2 minuti: installazione sul PC, scansione del QR, trackpad, tastiera, schermo, revoca dal PC.

---

## 5. Scheda dello store (testo di partenza)

**Nome:** Kursor: controlla il tuo PC
**Breve (80 caratteri):** Trackpad, tastiera e schermo del tuo PC sul telefono. Sicuro e senza account.

**Descrizione:**
Trasforma il telefono in trackpad, tastiera e telecomando per il **tuo** PC Windows.

- Trackpad con gesti, click, scroll e trascinamento
- Tastiera, scorciatoie e tasti multimediali
- Visione dello schermo in tempo reale con controllo a tocco
- Blocco, sospensione e spegnimento del PC, con conferma

**Sicurezza e privacy**
- Nessun account, nessun server esterno, nessun dato raccolto
- Associazione con QR code o PIN monouso
- Connessione cifrata con verifica del certificato del PC
- Sul PC un indicatore mostra sempre quando il telefono è connesso; puoi mettere in pausa o revocare l'accesso in qualsiasi momento

**Richiede** il programma gratuito Kursor sul PC (Windows 10/11): <URL>.
Usa Kursor solo su computer tuoi o che sei autorizzato a gestire.

**Screenshot:** pairing, trackpad, tastiera, schermo, finestra del PC con indicatore verde.

---

## 6. Cose da NON fare (per non avere problemi)

- Non aggiungere modalità "nascoste" o senza icona sul PC: verresti classificato come stalkerware/RAT dagli antivirus e dagli store.
- Non integrare analytics, crash reporting o pubblicità senza aggiornare privacy, Data safety e App Privacy.
- Non promettere nella scheda funzioni che non ci sono (per esempio "funziona ovunque" su iOS).
- Non pubblicare il repository o le chiavi di firma (`*.jks`, `.p12`, `.p8`): sono già in `.gitignore`.
