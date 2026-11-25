# Guida a PadLink

PadLink trasforma il tuo smartphone in un **trackpad, una tastiera e un telecomando** per il PC Windows. Puoi anche vedere lo schermo del PC sul telefono.
È **gratuito**, senza account e senza pubblicità. Telefono e PC si parlano direttamente in modo cifrato: nessun dato passa da server esterni.

> Usa PadLink solo su computer tuoi o che sei autorizzato a gestire.

## Indice
1. [Cosa ti serve](#1-cosa-ti-serve)
2. [Scaricare i file](#2-scaricare-i-file)
3. [Installare il programma sul PC](#3-installare-il-programma-sul-pc)
4. [Installare l'app sul telefono (Android)](#4-installare-lapp-sul-telefono-android)
5. [Collegare telefono e PC](#5-collegare-telefono-e-pc)
6. [Come si usa](#6-come-si-usa)
7. [Usarlo fuori casa (facoltativo)](#7-usarlo-fuori-casa-facoltativo)
8. [Sicurezza: pausa, revoca, password](#8-sicurezza-pausa-revoca-password)
9. [Problemi frequenti](#9-problemi-frequenti)
10. [Aggiornare e disinstallare](#10-aggiornare-e-disinstallare)
11. [Assistenza](#11-assistenza)

---

## 1. Cosa ti serve
- Un **PC con Windows 10 o 11**.
- Uno **smartphone Android 7.0 o più recente**.
- PC e telefono collegati alla **stessa rete Wi-Fi** (di casa o dell'ufficio).

## 2. Scaricare i file
Apri la pagina **[Releases](https://github.com/makaDv/Kursor/releases/latest)** e scarica dalla sezione *Assets*:
- `PadLink-Setup-x.y.z.exe`: il programma per il PC;
- `PadLink-x.y.z.apk`: l'app per Android (puoi scaricarla direttamente dal telefono).

## 3. Installare il programma sul PC
1. Fai doppio clic su `PadLink-Setup-x.y.z.exe`. Non servono diritti di amministratore.
2. Windows potrebbe mostrare **"Windows ha protetto il PC"** (SmartScreen). Il programma è gratuito e non ha una firma digitale a pagamento, per questo compare l'avviso. Clicca **Ulteriori informazioni** e poi **Esegui comunque**.
3. Segui l'installazione e avvia PadLink.
4. Al primo avvio:
   1. leggi e accetta i termini d'uso;
   2. **scegli una password per il PC**: il telefono la chiederà per collegarsi (evita password ovvie, verranno rifiutate);
   3. quando Windows chiede l'accesso alla rete, **consenti solo le "Reti private"**.

Se chiudi la finestra, PadLink resta attivo nell'**area di notifica**, l'icona vicino all'orologio. Dal menu dell'icona puoi riaprire la finestra, associare un telefono, mettere in pausa il controllo o uscire.

> **Smart App Control.** Su alcuni PC con Windows 11 è attivo *Smart App Control*, che blocca i programmi senza firma digitale senza permettere eccezioni. Se l'installazione viene bloccata, vedi [Problemi frequenti](#9-problemi-frequenti).

## 4. Installare l'app sul telefono (Android)
1. Sul telefono apri la pagina [Releases](https://github.com/makaDv/Kursor/releases/latest) e scarica `PadLink-x.y.z.apk`.
2. Apri il file scaricato. Android chiede di consentire l'installazione da **origini sconosciute** per il browser o il gestore file: attivala solo per questa installazione.
3. Tocca **Installa**. Se compare un avviso di Play Protect, scegli **Installa comunque**: l'app non è sul Play Store, quindi Google non la conosce.
4. Dopo l'installazione puoi disattivare di nuovo "origini sconosciute".

> **iPhone:** al momento non c'è un'app pronta da installare. Gli sviluppatori possono compilarla da sorgente: vedi [docs/SVILUPPO.md](SVILUPPO.md).

## 5. Collegare telefono e PC
1. Sul PC, nella finestra di PadLink, premi **Associa un nuovo telefono**: compaiono un **codice QR** e un **PIN a 6 cifre**.
2. Sul telefono apri PadLink e **inquadra il QR** con lo scanner dell'app. In alternativa, inserisci il PIN.
3. Inserisci la **password del PC** che hai scelto al punto 3.
4. Fatto: sul PC l'icona diventa verde quando un telefono è connesso.

Il QR e il PIN valgono **5 minuti** e si usano **una sola volta**. Per associare un altro telefono, premi di nuovo *Associa un nuovo telefono*.
**Più PC:** nell'app vai su *Altro*, scegli **Associa un altro PC** e inquadra il QR del secondo computer. Per passare da un PC all'altro, tocca il nome del PC in alto.

## 6. Come si usa
| Scheda | Cosa fa |
|---|---|
| **Trackpad** | 1 dito muove il puntatore · tocco = clic · 2 dita = scorrimento · tocco con 2 dita = clic destro · tocco con 3 dita = clic centrale · tieni premuto = trascina |
| **Tastiera** | Scrivi in tempo reale o invia un testo intero · tasti Ctrl/Alt/Shift/Win · Esc, Tab, frecce, F1-F12 · scorciatoie (Alt+Tab, copia/incolla, Win+D, Task Manager…) · tasti multimediali |
| **Schermo** | Vedi lo schermo del PC · modalità *Tocco* (tocchi dove vuoi cliccare) o *Trackpad* · scelta del monitor · qualità regolabile · schermo intero |
| **App** | Le app aperte sul PC, con le loro icone: tocca per passare da una all'altra |
| **Sistema** | Blocca, sospendi o spegni il PC (tieni premuto per confermare) |
| **Altro** | Sensibilità, scorrimento naturale, tema chiaro/scuro, lingua, dimensione del testo, PC associati, Aiuto |

Altre comodità:
- **appunti** condivisi tra telefono e PC, su richiesta;
- **tasti del volume** del telefono per regolare il volume del PC (Android);
- **Accendi PC** da spento con Wake-on-LAN, se il PC lo supporta (va attivato nel BIOS);
- l'app **ritrova il PC da sola** se cambia indirizzo in rete.

## 7. Usarlo fuori casa (facoltativo)
PadLink **non** si espone mai direttamente a Internet e **non devi aprire porte sul router**. Per usarlo fuori casa usa [Tailscale](https://tailscale.com/download), che è gratuito:
1. Installa Tailscale sul PC e sul telefono e accedi con **lo stesso account**.
2. Riavvia PadLink sul PC (icona vicino all'orologio, poi *Esci*, poi riapri).
3. Apri l'app una volta mentre sei a casa.

Da quel momento, quando sei fuori, l'app passa da sola alla connessione Tailscale. La verifica del certificato e la password restano le stesse.

## 8. Sicurezza: pausa, revoca, password
- **Icona verde** = un telefono è connesso. Quando un telefono guarda lo schermo, il PC lo indica sempre.
- **Pausa controllo**, dal menu dell'icona: blocca subito ogni comando dal telefono.
- **Revocare un telefono** perso o venduto: nella finestra di PadLink, sezione dispositivi, premi *Revoca*. Quel telefono non potrà più collegarsi.
- Nella finestra di PadLink puoi scegliere di **revocare in automatico** i telefoni non usati da un certo periodo.
- Puoi cambiare la password del PC dalla finestra di PadLink.
- Per motivi di sicurezza, Windows non permette di controllare la schermata di blocco né le finestre "Esegui come amministratore".

## 9. Problemi frequenti
**L'app non trova il PC.**
Controlla che PadLink sia aperto sul PC (icona vicino all'orologio) e che telefono e PC siano sulla stessa Wi-Fi. Poi tocca *Cerca il PC in rete*.

**Windows ha impostato la rete come "Pubblica".**
PadLink accetta connessioni solo sulle reti private. Vai su *Impostazioni > Rete e Internet > Wi-Fi*, apri la tua rete e scegli **Rete privata**.

**Windows blocca l'installazione (Smart App Control).**
Smart App Control non permette eccezioni per i programmi senza firma digitale. Puoi disattivarlo da *Sicurezza di Windows > Controllo app e browser > Smart App Control*. **Attenzione:** una volta disattivato, si può riattivare solo reinstallando Windows. Valuta bene prima di farlo. In alternativa, gli utenti esperti possono avviare PadLink da sorgente ([docs/SVILUPPO.md](SVILUPPO.md)).

**Il telefono dice "Certificato cambiato".**
Succede se hai reinstallato PadLink sul PC. Per sicurezza l'app blocca la connessione: associa di nuovo il telefono (punto 5).

**Non riesco a controllare alcune finestre.**
I programmi avviati come amministratore sono protetti da Windows. È una protezione voluta.

**Il PC si iberna invece di sospendersi.**
Dipende dalle impostazioni di risparmio energetico di Windows (ibernazione attiva).

## 10. Aggiornare e disinstallare
- **Aggiornare:** scarica la nuova versione da [Releases](https://github.com/makaDv/Kursor/releases/latest) e installala sopra la precedente, sia sul PC sia sul telefono. Telefoni associati e impostazioni restano.
- **Disinstallare dal PC:** *Impostazioni > App > App installate > PadLink > Disinstalla*.
- **Disinstallare dal telefono:** tieni premuta l'icona di PadLink e scegli *Disinstalla*.

## 11. Assistenza
- Domande, problemi e idee: apri una segnalazione su **[GitHub Issues](https://github.com/makaDv/Kursor/issues)**. Puoi farlo anche dall'app: *Altro > Aiuto > Segnala un problema*.
- Problemi di sicurezza: **non** pubblicarli. Segnalali in privato con [Report a vulnerability](https://github.com/makaDv/Kursor/security/advisories/new).
- [Privacy](legal/PRIVACY.md) · [Termini d'uso](legal/TERMS.md) · [Licenza Apache 2.0](../LICENSE)
