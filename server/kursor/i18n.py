"""English for the Windows program. Italian text is the key (fallback = Italian).

Language: PADLINK_LANG=it|en, else the Windows display language (Italian -> it,
anything else -> en). Strings built at runtime ("Pixel sta controllando questo PC")
are matched by the regex PATTERNS.
"""

from __future__ import annotations

import os
import re
import sys


def _detect() -> str:
    env = os.environ.get("PADLINK_LANG", "").lower()
    if env in ("it", "en"):
        return env
    if sys.platform == "win32":
        try:
            import ctypes

            return "it" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x10 else "en"
        except (AttributeError, OSError):
            pass
    import locale

    loc = (locale.getlocale()[0] or "").lower()
    return "it" if loc.startswith(("it", "italian")) else "en"


LANG = _detect()

EN: dict[str, str] = {
    "Controlla questo PC dal telefono": "Control this PC from your phone",
    "Pausa": "Pause",
    "Riprendi": "Resume",
    "Installa l'app PadLink sul telefono, poi premi il pulsante:\ncomparirà un QR code da inquadrare.":
        "Install the PadLink app on your phone, then press the button:\na QR code will appear for you to scan.",
    "Associa un telefono": "Pair a phone",
    "Password del PC": "PC password",
    "Imposta password": "Set password",
    "Cambia password": "Change password",
    "Password del PC: impostata (l'app la chiede a ogni apertura)":
        "PC password: set (the app asks for it every time it opens)",
    "Password del PC: non impostata (serve per associare i telefoni)":
        "PC password: not set (needed to pair phones)",
    "Imposta la password del PC": "Set the PC password",
    "Cambia la password del PC": "Change the PC password",
    "L'app la chiede a ogni apertura, anche via Tailscale.": "The app asks for it every time it opens, also over Tailscale.",
    "Almeno {n} caratteri; non usare la password di Windows.": "At least {n} characters; do not reuse your Windows password.",
    "Nuova password": "New password",
    "Ripeti la password": "Repeat the password",
    "Le password non coincidono": "The passwords do not match",
    "Password cambiata: i telefoni connessi dovranno reinserirla.": "Password changed: connected phones must enter it again.",
    "La password deve avere almeno 8 caratteri": "The password must be at least 8 characters long",
    "Apri l'app PadLink": "Open the PadLink app",
    "Tocca «Scansiona il QR code»": "Tap “Scan the QR code”",
    "Inquadra questo codice": "Scan this code",
    "Senza fotocamera usa questi dati:": "No camera? Use these details:",
    "Indirizzo": "Address",
    "Verifica": "Verify",
    "Annulla": "Cancel",
    "Associa un telefono ": "Pair a phone",
    "ASSOCIA UN TELEFONO": "PAIR A PHONE",
    "DISPOSITIVI ASSOCIATI": "PAIRED DEVICES",
    "SICUREZZA E OPZIONI": "SECURITY AND OPTIONS",
    "Sicurezza e opzioni": "Security and options",
    "Dispositivi associati": "Paired devices",
    "Benvenuto": "Welcome",
    "Limitato: ": "Limited: ",
    "Avvia PadLink all'accesso a Windows": "Start PadLink when I sign in to Windows",
    "Chiedi conferma qui sul PC quando un telefono si collega": "Ask for confirmation on this PC when a phone connects",
    "Fatti ritrovare dall'app se cambia l'indirizzo del PC (rete locale)":
        "Let the app find this PC again if its address changes (local network)",
    "Revoca i telefoni non usati da": "Revoke phones not used for",
    "mai": "never",
    "30 giorni": "30 days",
    "90 giorni": "90 days",
    "180 giorni": "180 days",
    "Esci": "Quit",
    "Privacy": "Privacy",
    "Termini": "Terms",
    "Termini d'uso": "Terms of use",
    "Licenze": "Licenses",
    "Licenze open source": "Open-source licenses",
    "Registro accessi": "Access log",
    "Controllo in pausa": "Control paused",
    "Nessun telefono può controllare il PC finché non riprendi.": "No phone can control this PC until you resume.",
    "Puoi mettere in pausa o revocare l'accesso in qualsiasi momento.": "You can pause or revoke access at any time.",
    "Nessun telefono connesso": "No phone connected",
    "I telefoni associati possono collegarsi quando vogliono.": "Paired phones can connect whenever they want.",
    "Associa un telefono per iniziare.": "Pair a phone to get started.",
    "Nessun dispositivo associato.": "No paired devices.",
    "Revoca": "Revoke",
    "Permessi": "Permissions",
    "● connesso": "● connected",
    "Consenti solo se sei tu o una persona di cui ti fidi.\nLa richiesta scade tra 30 secondi.":
        "Allow only if it is you or someone you trust.\nThe request expires in 30 seconds.",
    "Consenti": "Allow",
    "Rifiuta": "Deny",
    "Mouse e tastiera sono sempre consentiti.": "Mouse and keyboard are always allowed.",
    "Salva": "Save",
    "Schermo": "Screen",
    "App": "Apps",
    "Appunti": "Clipboard",
    "Spegnimento": "Power",
    "vedere lo schermo del PC": "view the PC screen",
    "vedere e gestire le finestre aperte": "see and manage open windows",
    "leggere e scrivere gli appunti": "read and write the clipboard",
    "bloccare, sospendere, spegnere, terminare programmi": "lock, sleep, shut down, end programs",
    "Scarica": "Download",
    "Impostazioni rete": "Network settings",
    "Questa rete è impostata come «Pubblica» in Windows. Usa PadLink solo su reti di cui ti fidi "
    "(casa, ufficio); in luoghi pubblici metti in pausa il controllo.":
        "This network is set as “Public” in Windows. Use PadLink only on networks you trust (home, office); "
        "pause control in public places.",
    "PadLink resta attivo nell'area di notifica. Usa \"Esci\" per chiuderlo.":
        "PadLink keeps running in the notification area. Use “Quit” to close it.",
    "Un telefono è connesso. Chiudere PadLink?": "A phone is connected. Quit PadLink?",
    "Apri PadLink": "Open PadLink",
    "Associa un nuovo telefono": "Pair a new phone",
    "Pausa controllo": "Pause control",
    "Benvenuto in PadLink": "Welcome to PadLink",
    "Controlla questo PC dal tuo telefono, in modo sicuro.": "Control this PC from your phone, securely.",
    "Cosa fa": "What it does",
    "Mouse, tastiera, schermo, app aperte, blocco e spegnimento del PC, dal telefono associato.":
        "Mouse, keyboard, screen, open apps, lock and shutdown of the PC, from the paired phone.",
    "Solo PC tuoi": "Only your PCs",
    "Usalo solo su computer tuoi o che sei autorizzato a gestire. Installarlo sul PC di altri senza consenso è vietato "
    "e può costituire reato.":
        "Use it only on computers you own or are authorised to manage. Installing it on someone else’s PC without "
        "consent is forbidden and may be a crime.",
    "Sempre visibile": "Always visible",
    "Quando un telefono è connesso l'icona vicino all'orologio diventa verde e compare un avviso. Puoi mettere in pausa "
    "o revocare l'accesso quando vuoi.":
        "When a phone is connected the icon next to the clock turns green and a notice appears. You can pause or "
        "revoke access whenever you want.",
    "Privato": "Private",
    "Nessun account e nessun dato raccolto: tutto resta fra il PC e i tuoi dispositivi, cifrato.":
        "No account and no data collected: everything stays between the PC and your devices, encrypted.",
    "Proseguendo accetti i Termini d'uso e l'Informativa privacy, consultabili in ogni momento dalla finestra di PadLink.":
        "By continuing you accept the Terms of use and the Privacy policy, available at any time from the PadLink window.",
    "Accetto e continuo": "I accept, continue",
    "PadLink è già in esecuzione: cercalo nell'area di notifica (vicino all'orologio).":
        "PadLink is already running: look for it in the notification area (next to the clock).",
    "Documento non trovato.": "Document not found.",
    "adesso": "just now",
    "Richiesta di accesso": "Access request",
}

PATTERNS: list[tuple[re.Pattern[str], str]] = [(re.compile(p), r) for p, r in [
    (r"^(.+) sta controllando questo PC$", r"\1 is controlling this PC"),
    (r"^(.+) sta guardando il tuo schermo$", r"\1 is viewing your screen"),
    (r"^Controllato ora da (.+)$", r"Controlled now by \1"),
    (r"^Sta guardando lo schermo: (.+)$", r"Viewing the screen: \1"),
    (r"^● In ascolto su (.+)$", r"● Listening on \1"),
    (r"^Scade tra (\d+:\d\d) · monouso$", r"Expires in \1 · single use"),
    (r"^DISPOSITIVI ASSOCIATI \((\d+)\)$", r"PAIRED DEVICES (\1)"),
    (r"^Ultimo accesso (\d+) min fa$", r"Last seen \1 min ago"),
    (r"^Ultimo accesso (\d+) h fa$", r"Last seen \1 h ago"),
    (r"^Ultimo accesso adesso$", r"Last seen just now"),
    (r"^Ultimo accesso (.+)$", r"Last seen \1"),
    (r"^Limitato: (.+)$", r"Limited: \1"),
    (r"^«(.+)» vuole controllare questo PC$", r"“\1” wants to control this PC"),
    (r"^«(.+)» chiede di controllare questo PC$", r"“\1” is asking to control this PC"),
    (r"^Cosa può fare «(.+)»$", r"What “\1” can do"),
    (r"^Disponibile PadLink (.+)$", r"PadLink \1 is available"),
    (r"^È disponibile PadLink (.+)\. Aggiorna per avere le ultime correzioni di sicurezza\.$",
     r"PadLink \1 is available. Update to get the latest security fixes."),
    (r"^(.+) ha bloccato il PC$", r"\1 locked the PC"),
    (r"^(.+) sta sospendendo il PC$", r"\1 is putting the PC to sleep"),
    (r"^(.+) sta spegnendo il PC$", r"\1 is shutting down the PC"),
    (r"^(.+) ha chiuso (.+)$", r"\1 closed \2"),
    (r"^(.+) ha terminato (.+)$", r"\1 ended \2"),
    (r"^(.+) ha copiato gli appunti del PC$", r"\1 copied the PC clipboard"),
    (r"^PadLink è attivo: (\d+) telefon[oi] associat[oi] possono controllare questo PC\. Apri l'icona per gestirli\.$",
     r"PadLink is running: \1 paired phone(s) can control this PC. Open the icon to manage them."),
    (r"^(.+) — (.+)$", None),  # handled by translating both halves
    (r"^Revocare \"(.+)\"\?\nNon potrà più controllare il PC finché non verrà associato di nuovo\.$",
     "Revoke “\\1”?\nIt will no longer control the PC until it is paired again."),
    (r"^Impossibile modificare l'avvio automatico: (.+)$", r"Could not change the autostart setting: \1"),
    (r"^(\d+) min fa$", r"\1 min ago"),
    (r"^(\d+) h fa$", r"\1 h ago"),
]]


def _(text: str) -> str:
    """Translate a UI string (exact match first, then runtime patterns)."""
    if LANG == "it" or not text:
        return text
    if text in EN:
        return EN[text]
    for pattern, repl in PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        if repl is None:  # "label — help": translate each half
            return f"{_(m.group(1))} — {_(m.group(2))}"
        return m.expand(repl)
    return text
