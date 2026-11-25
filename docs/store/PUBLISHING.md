# Pubblicare PadLink sugli store

Checklist per Google Play, Apple App Store e la distribuzione del programma Windows, con le risposte pronte per i questionari sulla privacy.

> Questi documenti sono una base tecnica accurata, **non una consulenza legale**. Prima di una pubblicazione commerciale, fai rivedere Termini e Privacy da un professionista.

---

## 0. Prima di tutto (una volta sola)

| Cosa | Dove | Note |
|---|---|---|
| Identificativo definitivo dell'app | `client/capacitor.config.ts` (`appId`), `client/android/app/build.gradle`, progetto Xcode | Oggi è `io.github.makadv.padlink`. **Non si può più cambiare dopo la prima pubblicazione.** Se hai un dominio, usa `tuodominio.padlink`. |
| **Dati pubblici (un solo file)** | `release.json` | Nome dello sviluppatore, email di contatto/sicurezza/assistenza, URL di sito, download, Play, Microsoft Store, video demo, identità di Partner Center. Poi `server\.venv\Scripts\python scripts\apply_release_info.py`: li scrive in privacy, termini, `SECURITY.md`, app (`SUPPORT_EMAIL`) e sito. Usa un'email dedicata. |
| **Controllo finale** | `scripts/release_check.py` | Prima di ogni upload: fallisce se resta un segnaposto, se le versioni non coincidono, se l'app Android è insicura (debug WebView, backup, HTTP in chiaro), se una chiave è tracciata da git o se `npm audit`/`pip-audit` trovano vulnerabilità. `build.ps1 -Release` lo esegue da solo. |
| Sito pubblico e URL della privacy | Obbligatorio per entrambi gli store | `scripts/build_site.py` genera `site/dist/` (home, FAQ, privacy, termini) dai documenti in `docs/legal`. Pubblica **solo** quella cartella (GitHub Pages di un repository pubblico separato, Netlify, Cloudflare Pages). L'URL della privacy è `<sito>/privacy.html`. Il repository resta privato. |
| Verifica del marchio "PadLink" | [TMview](https://www.tmdn.org/tmview/) (UE + nazionali), [USPTO](https://tmsearch.uspto.gov) | Il progetto si chiamava "Kursor", ma è stato rinominato perché suona identico a **Cursor**, marchio software registrato da Anysphere. Negli USA non risultano marchi PADLINK attivi (novembre 2026); **verifica in UE nelle classi 9 e 42 prima del lancio**. Valuta di registrarlo tu (EUIPO, circa 850 € per una classe). |
| Account sviluppatore | Google Play Console (25 $ una tantum), Apple Developer Program (99 $/anno) | Per Google Play da privato servono verifica dell'identità e 12 tester per 14 giorni prima della produzione. |
| Licenze open source | `scripts/collect_licenses.py` | Va eseguito prima di ogni build di rilascio (lo fa già `build.ps1`): genera i testi completi mostrati nell'app e nel programma PC. |

### Obblighi che il codice non può risolvere

| Obbligo | Quando | Cosa fare |
|---|---|---|
| **Stato di "trader" (Digital Services Act, UE)** | Sempre, entrambi gli store lo chiedono | Se l'app è **gratuita e senza alcun guadagno**, puoi dichiararti *non-trader* e i tuoi dati non vengono mostrati. Se guadagni (prezzo, acquisti in-app, donazioni, pubblicità) sei *trader*: nome, indirizzo, email e telefono diventano **pubblici** nella scheda. In quel caso conviene un indirizzo professionale. |
| **Partita IVA / fisco** | Solo se guadagni | Con l'app gratuita non serve. Se la vendi, Apple e Google ti pagano come sviluppatore e i ricavi vanno dichiarati: chiedi a un commercialista (in Italia di solito serve la P.IVA, regime forfettario). |
| **Revisione legale di Termini e Privacy** | Prima del lancio | Sono modelli accurati per *come funziona davvero* l'app, ma solo un avvocato può adattarli alla tua situazione. È una spesa una tantum, consigliata. |
| **Età** | Prima di registrare gli account | Per gli account sviluppatore Google e Apple devi essere maggiorenne. |
| **Cyber Resilience Act (UE 2024/2847)** | Obbligo di segnalare all'ENISA le vulnerabilità sfruttate attivamente dall'**11 settembre 2026**; requisiti completi dall'11 dicembre 2027 | Si applica ai prodotti software messi sul mercato UE **nell'ambito di un'attività commerciale**. Se PadLink resta gratuito e senza guadagni sei probabilmente escluso; se lo monetizzi, rientri: devi gestire le vulnerabilità (già c'è `SECURITY.md`), dichiarare per quanto tempo fornirai aggiornamenti di sicurezza e segnalare entro 24 ore le falle sfruttate. Da verificare con il legale. |
| **Controlli di sicurezza prima di ogni rilascio** | Ogni versione | `cd client; npm audit --omit=dev` e `server\.venv\Scripts\python -m pip_audit -r server
equirements.lock`: entrambi devono dare 0 vulnerabilità. Poi rigenera le licenze (`scripts/collect_licenses.py`). |
| **Responsabilità** | Facoltativo | Le esclusioni di garanzia nei Termini riducono il rischio, ma non lo azzerano per danni causati da difetti gravi. Correggi subito le vulnerabilità segnalate (`SECURITY.md`) e tieni l'app aggiornata. |

---

## 1. Google Play (Android)

### Build firmata (AAB)
1. **Chiave di upload**: `~/.padlink-release/padlink-upload.jks` (alias `upload`, password in `~/.padlink-release/README.txt`). **Fanne un backup fuori dal PC.** `client/android/keystore.properties` (escluso da git) la indica a Gradle. Per crearne una nuova: `keytool -genkeypair -keystore padlink-upload.jks -storetype PKCS12 -alias upload -keyalg RSA -keysize 4096 -validity 10000`.
2. **Versione**: cambia solo `"version"` in `client/package.json` (e lo stesso numero in `server/kursor/__init__.py`, `packaging/windows/kursor.iss`, `version_info.txt`: `release_check.py` controlla che coincidano). `versionCode` si calcola da solo (1.1.0 → 10100).
3. **Build**:
   ```powershell
   cd client; npm run build; npx cap sync android
   cd android; .\gradlew bundleRelease     # app\build\outputs\bundle\release\app-release.aab
   ```
   La release usa **R8** (codice minimizzato e offuscato, regole in `app/proguard-rules.pro`): prova sempre l'APK release (`.\gradlew assembleRelease`) su un telefono vero prima dell'upload.
4. In Play Console attiva **Play App Signing** al primo upload: Google custodisce la chiave di firma dell'app, tu solo quella di upload. Se perdi la chiave di upload, Play Console permette di sostituirla.
5. CI (facoltativo): secrets `ANDROID_UPLOAD_KEYSTORE` (il .jks in base64) e `ANDROID_UPLOAD_PASSWORD`. Poi `gh workflow run build.yml -f targets=android` produce l'AAB firmato.

> L'APK installato a mano e la versione dal Play Store hanno firme diverse: per passare a quella dello store, disinstalla prima l'APK (poi associa di nuovo il telefono).

### Sicurezza dei dati (Data safety): risposte
- **La tua app raccoglie o condivide uno dei tipi di dati utente richiesti?** → **No.**
  Motivazione: i dati (indirizzo del PC, token cifrato, comandi, immagini dello schermo) restano sul dispositivo o viaggiano solo fra il telefono e il PC dell'utente. Per la definizione di Google, i dati che lasciano il dispositivo verso un server **controllato dall'utente stesso** non sono "raccolti" dallo sviluppatore.
- **I dati sono criptati in transito?** → Sì (TLS 1.2+, certificate pinning).
- **È possibile richiedere la cancellazione dei dati?** → Non si applica: non esistono dati sui server dello sviluppatore. Basta disinstallare l'app.
- **SDK di terze parti che raccolgono dati:** nessuno. Lo scanner QR usa ZXing (offline), **non** Google ML Kit. La finestra di valutazione usa la libreria *Play In-App Review*: è un flusso di Google Play stesso e non trasmette dati dall'app allo sviluppatore. La biometria è verificata dal sistema (AndroidX Biometric) e non lascia il telefono.
- **Rete locale (mDNS, Wake-on-LAN):** il traffico resta sulla rete dell'utente, quindi non rientra nella raccolta di dati.

### Altre dichiarazioni
- **Protezioni dello schermo:** le schermate di password/PIN e la visione dello schermo del PC usano `FLAG_SECURE` (niente screenshot o anteprima nelle app recenti), e la WebView ignora i tocchi quando un'altra app si sovrappone (anti-tapjacking). Non richiedono permessi.
- **Permessi:** `CAMERA` serve solo allo scanner QR. Non ci sono permessi sensibili soggetti a dichiarazione: niente Accessibility, niente SMS, niente posizione. Wake-on-LAN e mDNS usano solo `INTERNET`, e la biometria non richiede permessi da dichiarare.
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

### Permessi iOS dichiarati in `Info.plist`
`NSCameraUsageDescription` (QR), `NSLocalNetworkUsageDescription` (rete locale), `NSFaceIDUsageDescription` (sblocco facoltativo), `NSBonjourServices` = `_padlink._tcp` (ritrovare il PC dopo un cambio di IP). Su iPhone il Wake-on-LAN non c'è: servirebbe l'entitlement multicast di Apple, da richiedere a parte.

### Privacy dell'app (App Store Connect › App Privacy)
- **Do you or your third-party partners collect data from this app?** → **No, we do not collect data from this app.**
  L'etichetta risultante è **"Data Not Collected"**.

### Firma in CI (quando vorrai)
Aggiungi ai *secrets* del repository: `IOS_DIST_CERT_P12` (base64), `IOS_DIST_CERT_PASSWORD`, `IOS_PROFILE` (base64), `APPSTORE_API_KEY_ID`, `APPSTORE_API_ISSUER_ID`, `APPSTORE_API_KEY_P8`. Poi estendi il job `ios` con `xcodebuild archive` + `-exportArchive` + `xcrun altool --upload-app`.

---

## 3. Programma Windows (il "lato PC")

Gli utenti dello store devono poter scaricare il programma per il PC. Senza di lui l'app non fa nulla, e va scritto nella descrizione.

### Microsoft Store (consigliato): pacchetto MSIX
1. Partner Center › nuova app "PadLink" › *Product identity*: copia **Package/Identity/Name**, **Publisher** (`CN=…`) e **Publisher display name** in `release.json` (`ms_store_identity_name`, `ms_store_publisher`, `ms_store_publisher_display_name`).
2. `powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1 -Msix -Release` → `dist\PadLink-<ver>.msix` (serve il Windows SDK per `makeappx`). Carica quel file: **lo Store lo firma**, quindi niente certificato da comprare e niente blocchi di Smart App Control.
3. Nel questionario dichiara la capability `runFullTrust`: "PadLink è un programma desktop Win32 (server locale per il controllo dal telefono, icona nell'area di notifica)".
4. Cosa cambia nella versione Store (già gestito nel codice): la regola del firewall per la porta 8443 è nel manifest, **solo reti private**; l'avvio automatico è uno *StartupTask* che l'utente attiva da Impostazioni › App › Avvio; l'aggiornamento automatico interno è spento (aggiorna lo Store).
5. Prova in locale: `build.ps1 -Msix -TestSign`, poi installa il certificato `CN=PadLink Test` in *Persone attendibili* (come amministratore) e `Add-AppxPackage dist\PadLink-<ver>.msix`.

### Installer dal sito (alternativa)
`build.ps1` produce anche `dist\PadLink-Setup-<ver>.exe` (Inno Setup). Pubblicalo su GitHub Releases e mettine l'URL in `release.json` (`windows_download_url`). Per gli aggiornamenti automatici firmati vedi la sezione 8.

### Firma del codice dell'installer: obbligatoria nella pratica
Windows 11 con **Smart App Control** attivo **blocca** gli eseguibili non firmati (verificato su questo PC: `PadLink.exe` non firmato viene bloccato). Hai due strade:

1. **Microsoft Store (consigliato).** Lo store firma l'app: niente certificato da comprare e nessun avviso SmartScreen. Account sviluppatore individuale gratuito (2025+). Si pubblica come `.exe` o MSI (Win32) indicando l'URL dell'installer, oppure come MSIX.
2. **Firma Authenticode tua.** Azure Trusted Signing (circa 10 $/mese, richiede verifica dell'identità) oppure un certificato OV/EV da una CA. Imposta `PADLINK_SIGN_PFX` (percorso del .pfx) e `PADLINK_SIGN_PASSWORD`: `build.ps1` firma `PadLink.exe` e `PadLink-Setup-*.exe` da solo.

### Build
`powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1` produce `dist\PadLink\` e, se Inno Setup 6 è installato, `dist\PadLink-Setup-1.0.0.exe`.

### Cosa fa l'installer (trasparenza)
- Installa per l'utente corrente, **senza diritti di amministratore**.
- Mostra i Termini d'uso da accettare. Al primo avvio compare anche una schermata di consenso.
- L'avvio automatico è facoltativo e disattivato di default.
- La disinstallazione rimuove tutto e chiede se cancellare anche i dati.
- Firewall: Windows chiede l'autorizzazione al primo avvio. **Consenti solo le reti private.**

---

## 3b. Provare in produzione prima del lancio

Entrambi gli store permettono di distribuire la **build vera, firmata, dallo store vero**, ma solo a tester scelti da te, prima di renderla pubblica.

| Fase | Google Play | Apple | Windows |
|---|---|---|---|
| 1. Solo tu (minuti) | **Test interno**: fino a 100 tester via email, disponibile in pochi minuti, senza revisione completa. | **TestFlight interno**: fino a 100 membri del tuo team, nessuna revisione. | Installer firmato condiviso a mano, oppure Microsoft Store **pacchetto privato** (*private audience*). |
| 2. Amici e beta (settimane) | **Test chiuso**: lista di tester o Google Group. **Obbligatorio per gli account personali nuovi: almeno 12 tester per 14 giorni consecutivi** prima di poter chiedere la produzione. | **TestFlight esterno**: fino a 10.000 tester tramite link pubblico; la prima build passa una breve *beta review*. | Microsoft Store *package flights* (gruppi di tester). |
| 3. Lancio graduale | **Rilascio in produzione graduale** (es. 5% → 20% → 100%), con possibilità di fermarlo se ci sono problemi. Puoi anche limitarlo a un solo Paese. | **Phased release**: 7 giorni con percentuali crescenti, mettibile in pausa. Oppure rilascio manuale dopo l'approvazione. | Pubblicazione per mercato, con possibilità di nascondere la scheda. |

Cosa controllare durante i test:
- associazione con QR su telefoni diversi (Android vecchi e nuovi, iPhone), con il PC su Wi-Fi diversi;
- **report pre-lancio di Google Play** (Firebase Test Lab automatico): crash e problemi di accessibilità. Il robot non può associarsi a un PC, quindi valuta solo la schermata iniziale;
- installer Windows su un PC "pulito" con Smart App Control attivo, per verificare che la firma funzioni;
- pausa, revoca, cambio di rete del PC, PC spento e poi riacceso;
- dalle recensioni dei tester: testi poco chiari, permessi che spaventano.

Ordine consigliato: test interno (1-2 giorni) → test chiuso con 12+ tester (14 giorni, obbligatorio su Play) → TestFlight esterno in parallelo → produzione graduale.

---

## 4. Istruzioni per i revisori (copia nei campi "Review notes" / "App access")

```
PadLink is a remote control for the user's OWN Windows PC (mouse, keyboard,
screen view), similar to a wireless trackpad. It needs the free companion
program installed on the PC: <URL DOWNLOAD PROGRAMMA PC>.

No account, no sign-in, no data collected. Phone and PC talk directly over
the local network through TLS with certificate pinning.

How to test:
1. On a Windows 10/11 PC on the same Wi-Fi, install and open PadLink.
2. On first start choose a PC password (at least 8 characters, e.g.
   "review-padlink-2026"): the app asks for it on every start.
3. Press "Associa un telefono" (Pair a phone): a QR code appears.
4. In the app type the PC password, tap "Scansiona il QR code" and scan it.
5. Use Trackpad / Tastiera (Keyboard) / Schermo (Screen) tabs.

Demo video: <URL VIDEO 1-2 MINUTI>

The PC always shows a visible tray indicator and a notification when a
phone is connected; the user can pause or revoke access at any time.
iOS build: connects only to PCs on the same local network (Guideline 4.2.7).
```

Registra un video di 1-2 minuti: installazione sul PC, scansione del QR, trackpad, tastiera, schermo, revoca dal PC.

---

## 5. Scheda dello store (testo di partenza)

**Nome:** PadLink: controlla il tuo PC
**Breve (80 caratteri):** Trackpad, tastiera e schermo del tuo PC sul telefono. Sicuro e senza account.

**Descrizione:**
Trasforma il telefono in trackpad, tastiera e telecomando per il **tuo** PC Windows.

- Trackpad con gesti, click, scroll e trascinamento
- Tastiera, scorciatoie e tasti multimediali
- Visione dello schermo in tempo reale con controllo a tocco
- Blocco, sospensione e spegnimento del PC, con conferma
- Anche fuori casa, se vuoi, con Tailscale (gratuito, nessuna porta da aprire)

**Sicurezza e privacy**
- Nessun account, nessun server esterno, nessun dato raccolto
- Associazione con QR code o PIN monouso, più una password scelta da te sul PC
- Connessione cifrata con verifica del certificato del PC
- Sul PC un indicatore mostra sempre quando il telefono è connesso; puoi mettere in pausa o revocare l'accesso in qualsiasi momento

**Richiede** il programma gratuito PadLink sul PC (Windows 10/11): <URL>.
Usa PadLink solo su computer tuoi o che sei autorizzato a gestire.

**Screenshot:** pairing, trackpad, tastiera, schermo, finestra del PC con indicatore verde.

---

## 7. Recensioni e feedback (per avere voti alti)

**Già nell'app:**
- **Richiesta di valutazione:** compare solo dopo 3 sessioni riuscite, mai dopo un errore, al massimo ogni 120 giorni (`client/src/lib/pc.ts`). Rispetta le regole degli store: non chiede «5 stelle» e non offre premi.
- **«Segnala un problema» e «Suggerisci un'idea»** (Aiuto): aprono una mail precompilata verso di te, così le lamentele arrivano a te prima che diventino recensioni da una stella.
- **FAQ** nell'app e sul sito, con le risposte ai problemi più comuni (PC non trovato, firewall, certificato).

**Da fare tu:**
- Rispondi a **tutte** le recensioni nei primi mesi, con cortesia e una soluzione concreta (Play Console › Valutazioni e recensioni; App Store Connect › Valutazioni e recensioni). Chi riceve risposta spesso alza il voto.
- Pubblica **note di versione** chiare, che citano ciò che gli utenti hanno chiesto. Modello:
  ```
  Novità
  • Accendi il PC dal telefono (Wake-on-LAN) – richiesto da molti di voi
  • L'app ritrova il PC anche se cambia indirizzo
  Correzioni
  • Connessione più stabile dopo la sospensione del PC
  Grazie per le segnalazioni: scrivici da Altro › Aiuto.
  ```
- Fai partire una **beta pubblica** (test aperto su Play, TestFlight pubblico) prima del lancio: i primi utenti diventano tester affezionati.
- Mostra negli screenshot e nel video l'indicatore verde sul PC: comunica subito che l'app è trasparente e sicura.

## 8. Aggiornamenti del programma PC (firmati)

Il programma Windows controlla una volta al giorno se c'è una nuova versione, ma solo dopo che l'hai configurato:
1. `python scripts/release_keys.py keygen <cartella-fuori-dal-repo>` genera la coppia di chiavi. **Tieni la chiave privata offline.**
2. Copia la chiave pubblica stampata in `UPDATE_PUBLIC_KEY` e l'URL del manifest in `UPDATE_URL` (`server/kursor/updates.py`).
3. A ogni rilascio pubblica `latest.json` (versione, URL dell'installer, sha256) e firmalo con `python scripts/release_keys.py sign <chiave> latest.json`, che crea `latest.json.sig`.
4. Il programma mostra «È disponibile PadLink x.y» solo se la firma è valida: un sito compromesso non può spingere un falso aggiornamento.

## 6. Cose da NON fare (per non avere problemi)

- Non aggiungere modalità "nascoste" o senza icona sul PC: verresti classificato come stalkerware/RAT dagli antivirus e dagli store.
- Non integrare analytics, crash reporting o pubblicità senza aggiornare privacy, Data safety e App Privacy.
- Non promettere nella scheda funzioni che non ci sono (per esempio "funziona ovunque" su iOS).
- Non pubblicare il repository o le chiavi di firma (`*.jks`, `.p12`, `.p8`): sono già in `.gitignore`.
