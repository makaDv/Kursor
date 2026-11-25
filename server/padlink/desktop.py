"""PadLink for Windows: tray icon + pairing window around the same secure server.

    python -m padlink desktop [--minimized]

Design rules (transparency first, this is NOT a stealth tool):
* a visible tray icon is always present while PadLink runs; it turns green and a
  notification appears whenever a phone takes control;
* a "Pausa" switch refuses remote control instantly without unpairing;
* the pairing QR/PIN is only shown on request and expires after 5 minutes;
* explicit consent to the terms on first run; autostart is opt-in;
* runs as the normal user (no admin rights, no service, no hooks).
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from .i18n import _

APP_NAME = "PadLink"
CONSENT_VERSION = 1
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# ---- environment -----------------------------------------------------------------------
def _fix_std_streams() -> None:
    # A windowed (no console) executable has no stdout/stderr.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115


def _bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _assets() -> Path:
    frozen = _bundle_dir() / "padlink" / "assets"
    return frozen if frozen.exists() else Path(__file__).resolve().parent / "assets"


def _legal_dir() -> Path:
    bundled = _bundle_dir() / "legal"
    return bundled if bundled.exists() else Path(__file__).resolve().parents[2] / "docs" / "legal"


def _configure_frozen_paths() -> None:
    if getattr(sys, "frozen", False):
        os.environ.setdefault("PADLINK_STATIC_DIR", str(_bundle_dir() / "client_dist"))


class SingleInstance:
    """Named mutex: a second launch exits instead of fighting over port 8443."""

    def __init__(self) -> None:
        self.handle = None
        self.already_running = False
        if sys.platform == "win32":
            self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\PadLinkDesktopSingleton")
            self.already_running = ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


# Design tokens shared with the phone app (client/src/index.css).
BG = "#0b0f17"        # ink-950
CARD = "#121826"      # ink-900
CARD2 = "#1b2333"     # ink-800
LINE = "#273145"      # ink-700
FG = "#e5e7eb"
MUTED = "#94a3b8"
ACCENT = "#6366f1"
ACCENT_HOVER = "#4f46e5"
ACCENT2 = "#22d3ee"
GREEN = "#10b981"
AMBER = "#f59e0b"
RED = "#ef4444"
FONT = "Segoe UI"
FONT_TITLE = "Segoe UI Semibold"
FONT_MONO = "Consolas"

_BUTTON_KINDS = {
    #            bg        fg        hover
    "primary": (ACCENT, "#ffffff", ACCENT_HOVER),
    "secondary": (CARD2, FG, LINE),
    "danger": ("#3a1f27", "#fca5a5", "#4c2430"),
    "warn": ("#3b2f12", "#fcd34d", "#4a3a16"),
    "ghost": (CARD, MUTED, CARD2),
}


class Label(tk.Label):
    """tk.Label whose text is translated (see i18n.py)."""

    def __init__(self, master: Any = None, **kw: Any) -> None:
        if isinstance(kw.get("text"), str):
            kw["text"] = _(kw["text"])
        super().__init__(master, **kw)

    def configure(self, cnf: Any = None, **kw: Any) -> Any:  # type: ignore[override]
        if isinstance(kw.get("text"), str):
            kw["text"] = _(kw["text"])
        return super().configure(cnf, **kw)

    config = configure


class Checkbutton(tk.Checkbutton):
    def __init__(self, master: Any = None, **kw: Any) -> None:
        if isinstance(kw.get("text"), str):
            kw["text"] = _(kw["text"])
        super().__init__(master, **kw)


def _button(parent: Any, text: str, command: Callable[[], None], kind: str = "secondary") -> tk.Button:
    bg, fg, hover = _BUTTON_KINDS[kind]
    return tk.Button(parent, text=_(text), command=command, bg=bg, fg=fg, activebackground=hover,
                     activeforeground=fg, relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                     font=(FONT, 10, "bold" if kind in ("primary", "warn") else "normal"), padx=14, pady=7)


def _restyle(button: tk.Button, text: str, kind: str) -> None:
    bg, fg, hover = _BUTTON_KINDS[kind]
    button.configure(text=_(text), bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                     font=(FONT, 10, "bold" if kind in ("primary", "warn") else "normal"))


def _link(parent: Any, text: str, command: Callable[[], None]) -> tk.Label:
    lbl = Label(parent, text=text, bg=BG, fg=MUTED, font=(FONT, 9, "underline"), cursor="hand2")
    lbl.bind("<Button-1>", lambda _e: command())
    lbl.bind("<Enter>", lambda _e: lbl.configure(fg=ACCENT2))
    lbl.bind("<Leave>", lambda _e: lbl.configure(fg=MUTED))
    return lbl


def _logo_photo(size: int) -> Any:
    try:
        from PIL import Image, ImageTk

        with Image.open(_assets() / "tray.png") as img:
            return ImageTk.PhotoImage(img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS))
    except Exception:  # noqa: BLE001 - cosmetic only
        return None


# ---- autostart (HKCU, opt-in) -------------------------------------------------------------
def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m padlink desktop --minimized'


def autostart_enabled() -> bool:
    from .winpkg import is_packaged

    if sys.platform != "win32" or is_packaged():  # Store build: StartupTask, managed in Windows Settings
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# ---- server thread ---------------------------------------------------------------------------
class ServerThread(threading.Thread):
    def __init__(self, config: Any) -> None:
        super().__init__(name="padlink-server", daemon=True)
        import uvicorn

        self.server = uvicorn.Server(config)
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.server.run()
        except BaseException as exc:  # noqa: BLE001 - includes SystemExit on bind failure
            self.error = exc

    def wait_started(self, timeout: float = 15) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.server.started:
                return True
            if not self.is_alive():
                return False
            time.sleep(0.05)
        return False

    def stop(self) -> None:
        self.server.should_exit = True


# ---- UI ---------------------------------------------------------------------------------------
PERM_LABELS = {"screen": "Schermo", "apps": "App", "clipboard": "Appunti", "power": "Spegnimento"}
PERM_HELP = {
    "screen": "vedere lo schermo del PC",
    "apps": "vedere e gestire le finestre aperte",
    "clipboard": "leggere e scrivere gli appunti",
    "power": "bloccare, sospendere, spegnere, terminare programmi",
}


def _ago(ts: float) -> str:
    s = max(0, time.time() - ts)
    if s < 60:
        return "adesso"
    if s < 3600:
        return f"{int(s // 60)} min fa"
    if s < 86400:
        return f"{int(s // 3600)} h fa"
    return time.strftime("%d/%m/%Y", time.localtime(ts))


class DesktopApp:
    def __init__(self, rt: Any, start_minimized: bool) -> None:
        from .logging_setup import audit

        self.rt = rt
        self.svc = rt.svc
        self.settings = rt.settings
        self.audit = audit
        self.ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self.connected: set[str] = set()
        self.viewers: set[str] = set()
        self.devices_sig: tuple = ()
        self.session_expires: float | None = None
        self.qr_photo = None
        self.tray = None
        self.hidden_hint_shown = False
        self.quitting = False
        self.prompted: set[str] = set()       # approval dialogs already on screen
        self.public_network = False
        self.update_info = None
        self.svc.approver_available = True    # this window can answer "ask on the PC" requests

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        # No fixed geometry: Tk sizes the window to its content, which scales with Windows DPI.
        self.root.minsize(560, 520)
        ico = _assets() / "padlink.ico"
        if ico.exists():
            self.root.iconbitmap(default=str(ico))
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self._style()
        self._build()
        self._start_tray()

        if start_minimized:
            self.root.withdraw()
            # Started with Windows: say so every time, so PadLink can never run unnoticed.
            n = len(self.svc.store.list())
            self.root.after(2500, lambda: self._notify(
                f"PadLink è attivo: {n} telefon{'o' if n == 1 else 'i'} associat{'o' if n == 1 else 'i'} "
                "possono controllare questo PC. Apri l'icona per gestirli."))
        if not self.svc.password.is_set():
            # First start (or an update from a version without passwords): choose it now.
            then = None if start_minimized or self.svc.store.list() else self.new_pairing
            self.root.after(300, lambda: (self.show(), self.set_password(then=then, mandatory=True)))
        elif not start_minimized and not self.svc.store.list():
            self.new_pairing()  # first launch: nothing paired yet, show the QR right away
        self.root.after(200, self._tick)
        threading.Thread(target=self._background_checks, name="padlink-checks", daemon=True).start()

    # -- layout --------------------------------------------------------------------------
    # Same design tokens as the phone app (client/src/index.css): ink surfaces, indigo
    # accent, cyan highlights, green/amber/red states, rounded "cards" with a thin border.
    def _style(self) -> None:
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("PL.Horizontal.TProgressbar", troughcolor=CARD2, background=ACCENT, bordercolor=CARD2,
                     lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
        st.configure("PL.Vertical.TScrollbar", troughcolor=CARD, background=CARD2, bordercolor=CARD,
                     arrowcolor=MUTED, lightcolor=CARD2, darkcolor=CARD2)

    def _card(self, parent: Any, **pack: Any) -> tk.Frame:
        card = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=LINE, highlightcolor=LINE)
        card.pack(fill="x", **pack)
        return card

    def _section(self, text: str) -> tk.Label:
        lbl = Label(self.body, text=_(text).upper(), bg=BG, fg=MUTED, font=(FONT, 8, "bold"), anchor="w")
        lbl.pack(fill="x", pady=(16, 6))
        return lbl

    def _build(self) -> None:
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=20, pady=(16, 14))

        # Header: logo, name, tagline, live listening address.
        head = tk.Frame(self.body, bg=BG)
        head.pack(fill="x")
        self.logo_photo = _logo_photo(40)
        if self.logo_photo is not None:
            Label(head, image=self.logo_photo, bg=BG).pack(side="left", padx=(0, 12))
        names = tk.Frame(head, bg=BG)
        names.pack(side="left")
        Label(names, text="PadLink", bg=BG, fg=FG, font=(FONT_TITLE, 17)).pack(anchor="w")
        Label(names, text="Controlla questo PC dal telefono", bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w")
        self.listen_lbl = Label(head, text="", bg=BG, fg=MUTED, font=(FONT, 9))
        self.listen_lbl.pack(side="right", anchor="n", pady=(4, 0))

        # Warning banner (public network, update available): hidden unless needed.
        self.banner = tk.Frame(self.body, bg="#3b2f12")
        self.banner_lbl = Label(self.banner, text="", bg="#3b2f12", fg="#fcd34d", font=(FONT, 9),
                                   justify="left", anchor="w", wraplength=440)
        self.banner_lbl.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        self.banner_btn = _button(self.banner, "", lambda: None, "warn")

        # Status card: always says whether someone is controlling this PC.
        self.status_card = self._card(self.body, pady=(16, 0))
        self.status_stripe = tk.Frame(self.status_card, bg=MUTED, width=4)
        self.status_stripe.pack(side="left", fill="y")
        inner = tk.Frame(self.status_card, bg=CARD)
        inner.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        self.status_title = Label(inner, text="", bg=CARD, fg=FG, font=(FONT, 11, "bold"), anchor="w")
        self.status_title.pack(fill="x")
        self.status_sub = Label(inner, text="", bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w", justify="left",
                                   wraplength=330)
        self.status_sub.pack(fill="x")
        self.pause_btn = _button(self.status_card, "Pausa", self.toggle_pause, "secondary")
        self.pause_btn.pack(side="right", padx=14)

        # Pairing
        self._section("Associa un telefono")
        self.pair_card = self._card(self.body)
        self.pair_idle = tk.Frame(self.pair_card, bg=CARD)
        Label(self.pair_idle, text="Installa l'app PadLink sul telefono, poi premi il pulsante:\n"
                                      "comparirà un QR code da inquadrare.", bg=CARD, fg=MUTED,
                 font=(FONT, 10), justify="left", anchor="w").pack(side="left", padx=16, pady=16)
        _button(self.pair_idle, "Associa un telefono", self.new_pairing, "primary").pack(side="right", padx=16)

        self.pair_active = tk.Frame(self.pair_card, bg=CARD)
        self.qr_label = Label(self.pair_active, bg="white", bd=0)
        self.qr_label.pack(side="left", padx=16, pady=16)
        info = tk.Frame(self.pair_active, bg=CARD)
        info.pack(side="left", fill="both", expand=True, pady=16, padx=(0, 16))
        for n, text in ((1, "Apri l'app PadLink"), (2, "Tocca «Scansiona il QR code»"), (3, "Inquadra questo codice")):
            row = tk.Frame(info, bg=CARD)
            row.pack(fill="x", pady=1)
            Label(row, text=str(n), bg=CARD2, fg=ACCENT2, font=(FONT, 9, "bold"), width=2).pack(side="left")
            Label(row, text=text, bg=CARD, fg=FG, font=(FONT, 10)).pack(side="left", padx=8)
        Label(info, text="Senza fotocamera usa questi dati:", bg=CARD, fg=MUTED, font=(FONT, 9),
                 anchor="w").pack(fill="x", pady=(10, 2))
        self.pin_value = self._kv(info, "PIN", (FONT_MONO, 18, "bold"), FG)
        self.addr_value = self._kv(info, "Indirizzo", (FONT_MONO, 10, "bold"), ACCENT2)
        self.code_value = self._kv(info, "Verifica", (FONT_MONO, 10, "bold"), ACCENT2)
        self.progress = ttk.Progressbar(info, style="PL.Horizontal.TProgressbar", maximum=1.0)
        self.progress.pack(fill="x", pady=(10, 2))
        foot = tk.Frame(info, bg=CARD)
        foot.pack(fill="x")
        self.expiry_lbl = Label(foot, text="", bg=CARD, fg=MUTED, font=(FONT, 9))
        self.expiry_lbl.pack(side="left")
        _button(foot, "Annulla", self.close_pairing, "ghost").pack(side="right")
        self._render_pairing(None)

        # Devices
        self.dev_title = self._section("Dispositivi associati")
        dev_card = self._card(self.body)
        self.dev_canvas = tk.Canvas(dev_card, bg=CARD, highlightthickness=0, bd=0, height=60)
        self.dev_scroll = ttk.Scrollbar(dev_card, orient="vertical", command=self.dev_canvas.yview,
                                        style="PL.Vertical.TScrollbar")
        self.dev_canvas.configure(yscrollcommand=self.dev_scroll.set)
        self.dev_canvas.pack(side="left", fill="both", expand=True)
        self.dev_rows = tk.Frame(self.dev_canvas, bg=CARD)
        self.dev_window = self.dev_canvas.create_window(0, 0, window=self.dev_rows, anchor="nw")
        self.dev_canvas.bind("<Configure>", lambda e: self.dev_canvas.itemconfigure(self.dev_window, width=e.width))
        self.dev_canvas.bind("<MouseWheel>", lambda e: self.dev_canvas.yview_scroll(int(-e.delta / 120), "units"))

        # Settings
        self._section("Sicurezza e opzioni")
        opts = self._card(self.body)
        prefs = self.svc.prefs.value
        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        self.approval_var = tk.BooleanVar(value=prefs.require_approval)
        self.discover_var = tk.BooleanVar(value=prefs.discoverable)
        for text, var, cmd in (
                ("Avvia PadLink all'accesso a Windows", self.autostart_var, self._toggle_autostart),
                ("Chiedi conferma qui sul PC quando un telefono si collega", self.approval_var, self._toggle_approval),
                ("Fatti ritrovare dall'app se cambia l'indirizzo del PC (rete locale)", self.discover_var,
                 self._toggle_discovery)):
            Checkbutton(opts, text=text, variable=var, command=cmd, bg=CARD, fg=FG, selectcolor=CARD2,
                           activebackground=CARD, activeforeground=FG, font=(FONT, 9), bd=0, highlightthickness=0,
                           anchor="w").pack(fill="x", padx=12, pady=(6, 0))
        row = tk.Frame(opts, bg=CARD)
        row.pack(fill="x", padx=14, pady=(6, 10))
        Label(row, text="Revoca i telefoni non usati da", bg=CARD, fg=FG, font=(FONT, 9)).pack(side="left")
        from .prefs import INACTIVE_CHOICES

        labels = {0: _("mai"), 30: _("30 giorni"), 90: _("90 giorni"), 180: _("180 giorni")}
        self.inactive_var = tk.StringVar(value=labels[prefs.inactive_days])
        menu = tk.OptionMenu(row, self.inactive_var, *[labels[d] for d in INACTIVE_CHOICES],
                             command=lambda v: self.svc.prefs.update(
                                 inactive_days={lab: d for d, lab in labels.items()}[v]))
        menu.configure(bg=CARD2, fg=FG, activebackground=LINE, activeforeground=FG, relief="flat",
                       highlightthickness=0, bd=0, font=(FONT, 9))
        menu["menu"].configure(bg=CARD2, fg=FG, activebackground=ACCENT)
        menu.pack(side="left", padx=8)
        pw_row = tk.Frame(opts, bg=CARD)
        pw_row.pack(fill="x", padx=14, pady=(0, 12))
        self.pw_lbl = Label(pw_row, text="", bg=CARD, fg=FG, font=(FONT, 9), anchor="w")
        self.pw_lbl.pack(side="left")
        self.pw_btn = _button(pw_row, "Imposta password", self.set_password, "secondary")
        self.pw_btn.pack(side="right")
        self._render_password()

        # Access away from home (optional Tailscale)
        self._section("Accesso fuori casa")
        remote = self._card(self.body)
        self.remote_lbl = Label(remote, text="Controllo di Tailscale…", bg=CARD, fg=MUTED, font=(FONT, 9),
                                justify="left", anchor="w", wraplength=380)
        self.remote_lbl.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        self.remote_btn = _button(remote, "Come attivarlo", self._open_tailscale_help, "secondary")
        self.remote_btn.pack(side="right", padx=14)

        # Footer
        foot = tk.Frame(self.body, bg=BG)
        foot.pack(fill="x", pady=(16, 0))
        _button(foot, "Esci", self.quit, "secondary").pack(side="right")
        links = tk.Frame(self.body, bg=BG)
        links.pack(fill="x", pady=(10, 0))
        for i, (text, cmd) in enumerate((
                ("Privacy", lambda: self.show_doc("PRIVACY.md", "Privacy")),
                ("Termini", lambda: self.show_doc("TERMS.md", "Termini d'uso")),
                ("Licenze", lambda: self.show_doc("licenses/windows-third-party.txt", "Licenze open source")),
                ("Registro accessi", self.open_logs))):
            if i:
                Label(links, text="·", bg=BG, fg=LINE, font=(FONT, 9)).pack(side="left", padx=4)
            _link(links, text, cmd).pack(side="left")
        from . import __version__

        Label(links, text=f"v{__version__}", bg=BG, fg=LINE, font=(FONT, 8)).pack(side="right")

    def _kv(self, parent: Any, key: str, font: tuple, color: str) -> tk.Label:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x")
        Label(row, text=key, bg=CARD, fg=MUTED, font=(FONT, 9), width=9, anchor="w").pack(side="left")
        val = Label(row, text="", bg=CARD, fg=color, font=font, anchor="w")
        val.pack(side="left")
        return val

    # -- access away from home (Tailscale) --
    def _render_remote(self, ts_ip: str | None, ts_public: bool) -> None:
        from .netutil import tailscale_ipv4

        started_with = tailscale_ipv4(self.svc.lan_ips)
        if ts_ip and ts_ip == started_with and ts_public:
            text = _("Tailscale attivo ({ip}), ma Windows lo considera una rete pubblica: il firewall blocca i telefoni.").format(ip=ts_ip)
            _restyle(self.remote_btn, "Consenti nel firewall", "warn")
            self.remote_btn.configure(command=self._allow_tailscale_firewall)
        elif ts_ip and ts_ip == started_with:
            text = _("Attivo: i telefoni con Tailscale (stesso account) raggiungono questo PC anche fuori casa ({ip}).").format(ip=ts_ip)
            _restyle(self.remote_btn, "Come funziona", "ghost")
            self.remote_btn.configure(command=self._open_tailscale_help)
        elif ts_ip:
            text = _("Tailscale è attivo ({ip}) ma è partito dopo PadLink: esci da PadLink e riaprilo.").format(ip=ts_ip)
            _restyle(self.remote_btn, "Come funziona", "secondary")
            self.remote_btn.configure(command=self._open_tailscale_help)
        else:
            text = _("Facoltativo. Per usare il telefono fuori casa installa Tailscale (gratis) su PC e telefono con lo stesso account, poi riavvia PadLink.")
            _restyle(self.remote_btn, "Scarica Tailscale", "secondary")
            self.remote_btn.configure(command=self._open_tailscale_help)
        self.remote_lbl.configure(text=text, fg=FG if ts_ip else MUTED)

    def _open_tailscale_help(self) -> None:
        import webbrowser

        webbrowser.open("https://tailscale.com/download")

    def _allow_tailscale_firewall(self) -> None:
        """Runs the bundled firewall.ps1 elevated (UAC prompt): TCP 8443 only from 100.64.0.0/10."""
        import subprocess

        script = _bundle_dir() / "scripts" / "firewall.ps1"
        if not script.exists():
            script = Path(__file__).resolve().parents[2] / "scripts" / "firewall.ps1"
        if not script.exists():
            messagebox.showerror(APP_NAME, _("Script del firewall non trovato."))
            return
        # Single-quoted PowerShell string: a ' in the path (e.g. C:\Users\O'Neil) is doubled.
        args = f"-NoProfile -ExecutionPolicy Bypass -File \"{script}\" -Port {int(self.settings.port)}".replace("'", "''")
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Start-Process powershell -Verb RunAs -Wait -ArgumentList '{args}'"],
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=300)
        except (OSError, subprocess.SubprocessError):
            return
        self.audit("firewall_tailscale_rule", by="desktop")
        self._notify(_("Regole del firewall aggiornate per Tailscale."))

    # -- PC password --
    def _render_password(self) -> None:
        if self.svc.password.is_set():
            self.pw_lbl.configure(text="Password del PC: impostata (l'app la chiede a ogni apertura)", fg=FG)
            _restyle(self.pw_btn, "Cambia password", "secondary")
        else:
            self.pw_lbl.configure(text="Password del PC: non impostata (serve per associare i telefoni)", fg=AMBER)
            _restyle(self.pw_btn, "Imposta password", "primary")

    def set_password(self, then: Callable[[], None] | None = None, mandatory: bool = False) -> None:
        """``mandatory``: first start, no password yet. The dialog cannot be dismissed:
        without a password no phone can pair or connect."""
        from .security.password import MIN_LENGTH, PasswordError, validate

        changing = self.svc.password.is_set()
        win = tk.Toplevel(self.root, bg=BG)
        win.title(f"{APP_NAME} · {_('Password del PC')}")
        win.resizable(False, False)
        win.transient(self.root)
        Label(win, text="Cambia la password del PC" if changing else "Imposta la password del PC",
              bg=BG, fg=FG, font=(FONT_TITLE, 13)).pack(anchor="w", padx=20, pady=(18, 2))
        Label(win, text=_("L'app la chiede a ogni apertura, anche via Tailscale.") + "\n"
              + _("Almeno {n} caratteri; non usare la password di Windows.").format(n=MIN_LENGTH),
              bg=BG, fg=MUTED, font=(FONT, 9), justify="left").pack(anchor="w", padx=20, pady=(0, 10))
        entries = []
        for text in ("Nuova password", "Ripeti la password"):
            Label(win, text=text, bg=BG, fg=FG, font=(FONT, 9), anchor="w").pack(fill="x", padx=20)
            e = tk.Entry(win, show="•", bg=CARD2, fg=FG, insertbackground=FG, relief="flat", font=(FONT, 11), width=32)
            e.pack(fill="x", padx=20, pady=(2, 8), ipady=4)
            entries.append(e)
        err = Label(win, text="", bg=BG, fg=RED, font=(FONT, 9), anchor="w")
        err.pack(fill="x", padx=20)

        def save(_e: Any = None) -> None:
            first, second = entries[0].get(), entries[1].get()
            try:
                validate(first, self.svc.pc_name)
            except PasswordError as exc:
                err.configure(text=str(exc))
                return
            if first != second:
                err.configure(text="Le password non coincidono")
                return
            self.svc.password.set(first, self.svc.pc_name)
            for e in entries:
                e.delete(0, "end")
            self.audit("password_set", by="desktop", changed=changing)
            self._render_password()
            win.destroy()
            if changing:
                self._notify(_("Password cambiata: i telefoni connessi dovranno reinserirla."))
            if then is not None:
                then()

        entries[0].focus_set()
        entries[1].bind("<Return>", save)
        btns = tk.Frame(win, bg=BG)
        btns.pack(fill="x", padx=20, pady=16)
        _button(btns, "Salva", save, "primary").pack(side="right")
        if mandatory:
            win.protocol("WM_DELETE_WINDOW", lambda: err.configure(
                text=_("Serve una password per usare PadLink: i telefoni la chiederanno a ogni apertura.")))
        else:
            _button(btns, "Annulla", win.destroy, "secondary").pack(side="right", padx=8)
        win.grab_set()

    # -- pairing --
    def new_pairing(self) -> None:
        if not self.svc.password.is_set():
            # The app asks for this password at pairing and on every start: set it first.
            self.set_password(then=self.new_pairing)
            return
        session = self.svc.pairing.new_session()
        self.audit("pairing_opened", source="desktop")
        self._render_pairing(session)

    def close_pairing(self) -> None:
        self.svc.pairing.close()
        self._render_pairing(None)

    def _render_pairing(self, session: Any) -> None:
        self.pair_idle.pack_forget()
        self.pair_active.pack_forget()
        if session is None:
            self.session_expires = None
            self.pair_idle.pack(fill="x")
            return

        import qrcode
        from PIL import ImageTk

        from .pairinfo import base_url, current_verification_code, pairing_url

        img = qrcode.make(pairing_url(self.settings, session.code), box_size=5, border=2).get_image().convert("RGB")
        self.qr_photo = ImageTk.PhotoImage(img)
        self.qr_label.configure(image=self.qr_photo)
        self.pin_value.configure(text=f"{session.pin[:3]} {session.pin[3:]}")
        self.addr_value.configure(text=base_url(self.settings).split("://", 1)[-1])
        self.code_value.configure(text=current_verification_code(self.settings) or "—")
        self.session_expires = session.expires_at
        self.session_ttl = max(1.0, session.expires_at - time.time())
        self.pair_active.pack(fill="x")
        self._update_countdown()

    def _update_countdown(self) -> None:
        if self.session_expires is None:
            return
        left = int(self.session_expires - time.time())
        if left <= 0 or self.svc.pairing.active_until() is None:
            self._render_pairing(None)  # expired or already used: never leave a stale QR on screen
            return
        self.progress.configure(value=left / self.session_ttl)
        self.expiry_lbl.configure(text=f"Scade tra {left // 60}:{left % 60:02d} · monouso")

    # -- devices / status --
    def _set_status(self, color: str, title: str, sub: str, pause_text: str, pause_kind: str) -> None:
        self.status_stripe.configure(bg=color)
        self.status_title.configure(text=title, fg=color if color != MUTED else FG)
        self.status_sub.configure(text=sub)
        _restyle(self.pause_btn, pause_text, pause_kind)

    def _refresh(self) -> None:
        # Actions performed from phones ("Pixel ha spento il PC"): always tell whoever sits here.
        while self.svc.events:
            _ts, text = self.svc.events.popleft()
            self._notify(text)
        for dev_id in list(self.svc.approvals):
            if dev_id not in self.prompted:
                self.prompted.add(dev_id)
                self._ask_approval(dev_id)
        self._render_banner()
        devices = self.svc.store.list()
        names = {d.id: d.name for d in devices}
        connected = set(self.svc.registry.device_ids())

        for dev_id in connected - self.connected:
            self._notify(f"{names.get(dev_id, 'Un dispositivo')} sta controllando questo PC")
        self.connected = connected
        # Transparency: whoever sits at the PC must know when the screen is being watched.
        viewers = {d for d, n in list(self.svc.screen_viewers.items()) if n > 0}
        for dev_id in viewers - self.viewers:
            self._notify(f"{names.get(dev_id, 'Un dispositivo')} sta guardando il tuo schermo")
        self.viewers = viewers

        if self.svc.paused:
            self._set_status(AMBER, "Controllo in pausa",
                             "Nessun telefono può controllare il PC finché non riprendi.", "Riprendi", "warn")
        elif connected:
            who = ", ".join(sorted(names.get(i, "?") for i in connected))
            watching = ", ".join(sorted(names.get(i, "?") for i in viewers))
            detail = (f"Sta guardando lo schermo: {watching}" if watching
                      else "Puoi mettere in pausa o revocare l'accesso in qualsiasi momento.")
            self._set_status(GREEN, f"Controllato ora da {who}", detail, "Pausa", "secondary")
        else:
            self._set_status(MUTED, "Nessun telefono connesso",
                             "I telefoni associati possono collegarsi quando vogliono." if devices
                             else "Associa un telefono per iniziare.", "Pausa", "secondary")

        from .pairinfo import base_url

        self.listen_lbl.configure(text=f"● In ascolto su {base_url(self.settings).split('://', 1)[-1]}",
                                  fg=AMBER if self.svc.paused else GREEN)

        sig = tuple((d.id, d.name, int(d.last_seen) // 60, d.id in connected, tuple(sorted(d.perms.items())))
                    for d in devices)
        if sig != self.devices_sig:
            self.devices_sig = sig
            self._render_devices(devices, connected)
        self._update_tray(bool(connected) and not self.svc.paused)

    def _render_devices(self, devices: list, connected: set[str]) -> None:
        for child in self.dev_rows.winfo_children():
            child.destroy()
        self.dev_title.configure(text=f"DISPOSITIVI ASSOCIATI ({len(devices)})")
        if not devices:
            Label(self.dev_rows, text="Nessun dispositivo associato.", bg=CARD, fg=MUTED,
                     font=(FONT, 10)).pack(anchor="w", padx=16, pady=16)
        for i, d in enumerate(devices):
            if i:
                tk.Frame(self.dev_rows, bg=LINE, height=1).pack(fill="x", padx=16)
            row = tk.Frame(self.dev_rows, bg=CARD)
            row.pack(fill="x", padx=16, pady=10)
            text = tk.Frame(row, bg=CARD)
            text.pack(side="left", fill="x", expand=True)
            top = tk.Frame(text, bg=CARD)
            top.pack(fill="x")
            Label(top, text=d.name, bg=CARD, fg=FG, font=(FONT, 10, "bold")).pack(side="left")
            if d.id in connected:
                Label(top, text="● connesso", bg=CARD, fg=GREEN, font=(FONT, 9)).pack(side="left", padx=8)
            Label(text, text=f"Ultimo accesso {_ago(d.last_seen)}", bg=CARD, fg=MUTED,
                     font=(FONT, 9)).pack(anchor="w")
            _button(row, "Revoca", lambda dev_id=d.id, name=d.name: self.revoke(dev_id, name), "danger").pack(
                side="right")
            _button(row, "Permessi", lambda dev_id=d.id: self.edit_perms(dev_id), "ghost").pack(side="right", padx=6)
            limited = [p for p, on in d.perms.items() if not on]
            if limited:
                Label(text, text=_("Limitato: ") + ", ".join(_(PERM_LABELS[p]).lower() for p in limited), bg=CARD,
                         fg=AMBER, font=(FONT, 8)).pack(anchor="w")
        self.dev_rows.update_idletasks()
        height = min(self.dev_rows.winfo_reqheight(), 230)
        self.dev_canvas.configure(height=height, scrollregion=(0, 0, 0, self.dev_rows.winfo_reqheight()))
        if self.dev_rows.winfo_reqheight() > 230:
            self.dev_scroll.pack(side="right", fill="y")
        else:
            self.dev_scroll.pack_forget()
        for w in [self.dev_rows, *self.dev_rows.winfo_children()]:
            w.bind("<MouseWheel>", lambda e: self.dev_canvas.yview_scroll(int(-e.delta / 120), "units"))

    def _tick(self) -> None:
        while True:
            try:
                self.ui_queue.get_nowait()()
            except queue.Empty:
                break
        try:
            self._update_countdown()
            self._refresh()
        except Exception:  # noqa: BLE001 - never kill the UI loop
            import logging

            logging.getLogger(__name__).exception("UI refresh failed")
        if not self.quitting:
            self.root.after(1000, self._tick)

    def _close_sockets(self, device_ids: list[str], code: int, reason: str) -> None:
        loop = self.svc.loop
        if loop is None:
            return
        for dev_id in device_ids:
            asyncio.run_coroutine_threadsafe(self.svc.registry.close_device(dev_id, code, reason), loop)

    def revoke(self, dev_id: str, name: str) -> None:
        if not messagebox.askyesno(APP_NAME, _(f'Revocare "{name}"?\nNon potrà più controllare il PC '
                                               f"finché non verrà associato di nuovo.")):
            return
        if self.svc.store.revoke(dev_id):
            self.audit("device_revoked", device=dev_id, by="desktop")
            self._close_sockets([dev_id], 4409, "revoked")
        self.devices_sig = ()

    # -- approvals / permissions / options -------------------------------------------------
    def _ask_approval(self, dev_id: str) -> None:
        name = self.svc.device_name(dev_id)
        win = tk.Toplevel(self.root, bg=BG)
        win.title(f"{APP_NAME} · {_('Richiesta di accesso')}")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        Label(win, text=f"«{name}» vuole controllare questo PC", bg=BG, fg=FG,
                 font=(FONT_TITLE, 13)).pack(anchor="w", padx=20, pady=(18, 4))
        Label(win, text="Consenti solo se sei tu o una persona di cui ti fidi.\n"
                           "La richiesta scade tra 30 secondi.", bg=BG, fg=MUTED, font=(FONT, 9),
                 justify="left").pack(anchor="w", padx=20)
        btns = tk.Frame(win, bg=BG)
        btns.pack(fill="x", padx=20, pady=16)

        def answer(allow: bool) -> None:
            self.svc.answer_approval(dev_id, allow)
            self.audit("approval_" + ("granted" if allow else "denied"), device=dev_id, by="desktop")
            self.prompted.discard(dev_id)
            win.destroy()

        _button(btns, "Consenti", lambda: answer(True), "primary").pack(side="right")
        _button(btns, "Rifiuta", lambda: answer(False), "danger").pack(side="right", padx=8)
        win.protocol("WM_DELETE_WINDOW", lambda: answer(False))
        win.after(30_000, lambda: win.winfo_exists() and answer(False))
        self.show()
        win.lift()
        self._notify(f"«{name}» chiede di controllare questo PC")

    def edit_perms(self, dev_id: str) -> None:
        dev = self.svc.store.get(dev_id)
        if dev is None:
            return
        win = tk.Toplevel(self.root, bg=BG)
        win.title(f"{APP_NAME} · {_('Permessi')}")
        win.resizable(False, False)
        Label(win, text=f"Cosa può fare «{dev.name}»", bg=BG, fg=FG, font=(FONT_TITLE, 13)).pack(
            anchor="w", padx=20, pady=(18, 2))
        Label(win, text="Mouse e tastiera sono sempre consentiti.", bg=BG, fg=MUTED, font=(FONT, 9)).pack(
            anchor="w", padx=20, pady=(0, 8))
        vars_ = {}
        for perm, label in PERM_LABELS.items():
            vars_[perm] = tk.BooleanVar(value=dev.can(perm))
            Checkbutton(win, text=f"{label} — {PERM_HELP[perm]}", variable=vars_[perm], bg=BG, fg=FG,
                           selectcolor=CARD2, activebackground=BG, activeforeground=FG, font=(FONT, 10), bd=0,
                           highlightthickness=0, anchor="w").pack(fill="x", padx=18, pady=2)

        def save() -> None:
            perms = {k: v.get() for k, v in vars_.items()}
            self.svc.store.set_perms(dev_id, perms)
            self.audit("device_permissions", device=dev_id, by="desktop",
                       denied=",".join(k for k, v in perms.items() if not v) or None)
            # Reconnect live sessions so the new limits apply immediately (screen stream, UI).
            self._close_sockets([dev_id], 4401, "permissions_changed")
            self.devices_sig = ()
            win.destroy()

        btns = tk.Frame(win, bg=BG)
        btns.pack(fill="x", padx=20, pady=16)
        _button(btns, "Salva", save, "primary").pack(side="right")
        _button(btns, "Annulla", win.destroy, "secondary").pack(side="right", padx=8)

    def _toggle_approval(self) -> None:
        self.svc.prefs.update(require_approval=self.approval_var.get())
        self.svc.approved.clear()
        self.audit("setting_changed", setting="require_approval", value=self.approval_var.get())

    def _toggle_discovery(self) -> None:
        on = self.discover_var.get()
        self.svc.prefs.update(discoverable=on)
        if on:
            threading.Thread(target=self.rt.start_discovery, daemon=True).start()
        else:
            threading.Thread(target=self.rt.stop_discovery, daemon=True).start()

    def _background_checks(self) -> None:
        """Slow checks off the UI thread: network profile every 5 min, updates once a day."""
        from . import updates
        from .netutil import public_network_profile, tailscale_ipv4, tailscale_network_public

        last_update = 0.0
        while not self.quitting:
            public = public_network_profile()
            self.ui_queue.put(lambda public=public: setattr(self, "public_network", public))
            ts_ip = tailscale_ipv4()
            ts_public = bool(ts_ip) and tailscale_network_public()
            self.ui_queue.put(lambda ip=ts_ip, pub=ts_public: self._render_remote(ip, pub))
            if updates.enabled() and time.time() - last_update > updates.CHECK_INTERVAL_S:
                last_update = time.time()
                info = updates.check()
                if info:
                    self.ui_queue.put(lambda info=info: (setattr(self, "update_info", info),
                                                         self._notify(f"Disponibile PadLink {info.version}")))
            for _ in range(300):
                if self.quitting:
                    return
                time.sleep(1)

    def _render_banner(self) -> None:
        text, button = "", None
        if self.update_info is not None:
            info = self.update_info
            text = f"È disponibile PadLink {info.version}. Aggiorna per avere le ultime correzioni di sicurezza."
            button = ("Scarica", lambda: __import__("webbrowser").open(info.url))
        elif self.public_network:
            text = ("Questa rete è impostata come «Pubblica» in Windows. Usa PadLink solo su reti di cui ti fidi "
                    "(casa, ufficio); in luoghi pubblici metti in pausa il controllo.")
            button = ("Impostazioni rete", lambda: os.startfile("ms-settings:network-status"))  # noqa: S606
        if not text:
            self.banner.pack_forget()
            return
        self.banner_lbl.configure(text=text)
        if button:
            _restyle(self.banner_btn, button[0], "warn")
            self.banner_btn.configure(command=button[1])
            self.banner_btn.pack(side="right", padx=10)
        if not self.banner.winfo_ismapped():
            self.banner.pack(fill="x", pady=(12, 0), after=self.body.winfo_children()[0])

    def toggle_pause(self) -> None:
        self.svc.paused = not self.svc.paused
        self.audit("control_paused" if self.svc.paused else "control_resumed", by="desktop")
        if self.svc.paused:
            self._close_sockets(self.svc.registry.device_ids(), 4423, "paused")
        self._refresh()

    def _toggle_autostart(self) -> None:
        from .winpkg import is_packaged

        if is_packaged():
            # MSIX: autostart is the manifest StartupTask, switched on by the user in Settings.
            self.autostart_var.set(False)
            messagebox.showinfo(APP_NAME, _("Nella versione del Microsoft Store l'avvio automatico si attiva da "
                                            "Impostazioni › App › Avvio › PadLink. Si apre ora."))
            os.startfile("ms-settings:startupapps")  # type: ignore[attr-defined]
            return
        try:
            set_autostart(self.autostart_var.get())
        except OSError as exc:
            messagebox.showerror(APP_NAME, _(f"Impossibile modificare l'avvio automatico: {exc}"))
            self.autostart_var.set(autostart_enabled())

    def open_logs(self) -> None:
        path = str(self.settings.log_dir)
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
        else:
            import subprocess

            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])  # noqa: S603

    def show_doc(self, filename: str, title: str) -> None:
        path = _legal_dir() / filename
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = "Documento non trovato."
        win = tk.Toplevel(self.root, bg=BG)
        win.title(f"{APP_NAME} · {_(title)}")
        win.geometry("620x640")
        box = tk.Text(win, wrap="word", bg=CARD, fg=FG, font=(FONT, 10), borderwidth=0, padx=18, pady=14,
                      highlightthickness=1, highlightbackground=LINE, relief="flat")
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=10, pady=10)

    # -- window / tray --
    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()
        if not self.hidden_hint_shown:
            self.hidden_hint_shown = True
            self._notify("PadLink resta attivo nell'area di notifica. Usa \"Esci\" per chiuderlo.")

    def quit(self) -> None:
        if self.connected and not messagebox.askyesno(APP_NAME, _("Un telefono è connesso. Chiudere PadLink?")):
            return
        self.quitting = True
        self.rt_server.stop()
        if self.tray is not None:
            self.tray.stop()
        self.root.destroy()

    def _tray_image(self, active: bool) -> Any:
        from PIL import Image

        name = "tray-active.png" if active else "tray.png"
        path = _assets() / name
        if path.exists():
            return Image.open(path)
        return Image.new("RGBA", (64, 64), GREEN if active else ACCENT)

    def _start_tray(self) -> None:
        try:
            import pystray
        except ImportError:
            return
        post = self.ui_queue.put
        menu = pystray.Menu(
            pystray.MenuItem(_("Apri PadLink"), lambda: post(self.show), default=True),
            pystray.MenuItem(_("Associa un nuovo telefono"), lambda: post(lambda: (self.show(), self.new_pairing()))),
            pystray.MenuItem(_("Pausa controllo"), lambda: post(self.toggle_pause), checked=lambda _: self.svc.paused),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(_("Esci"), lambda: post(lambda: (self.show(), self.quit()))),
        )
        self.tray = pystray.Icon(APP_NAME, self._tray_image(False), APP_NAME, menu)
        self.tray_active = False
        self.tray.run_detached()

    def _update_tray(self, active: bool) -> None:
        if self.tray is None or active == getattr(self, "tray_active", None):
            return
        self.tray_active = active
        self.tray.icon = self._tray_image(active)
        self.tray.title = "PadLink · telefono connesso" if active else "PadLink"

    def _notify(self, message: str) -> None:
        if self.tray is not None:
            try:
                self.tray.notify(_(message), APP_NAME)
            except Exception:  # noqa: BLE001 - notifications are best effort
                pass

    def run(self, server: ServerThread) -> None:
        self.rt_server = server
        self.root.mainloop()


# ---- consent ----------------------------------------------------------------------------------
def _consent_file(settings: Any) -> Path:
    return settings.data_dir / "consent.json"


def ensure_consent(settings: Any) -> bool:
    path = _consent_file(settings)
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("version") == CONSENT_VERSION:
            return True
    except (OSError, ValueError):
        pass

    root = tk.Tk()
    root.title(f"{APP_NAME} · Benvenuto")
    root.configure(bg=BG)
    root.resizable(False, False)
    ico = _assets() / "padlink.ico"
    if ico.exists():
        root.iconbitmap(default=str(ico))
    accepted = tk.BooleanVar(value=False)
    body = tk.Frame(root, bg=BG)
    body.pack(fill="both", expand=True, padx=24, pady=20)

    head = tk.Frame(body, bg=BG)
    head.pack(fill="x")
    logo = _logo_photo(44)
    if logo is not None:
        Label(head, image=logo, bg=BG).pack(side="left", padx=(0, 12))
    names = tk.Frame(head, bg=BG)
    names.pack(side="left")
    Label(names, text="Benvenuto in PadLink", bg=BG, fg=FG, font=(FONT_TITLE, 16)).pack(anchor="w")
    Label(names, text="Controlla questo PC dal tuo telefono, in modo sicuro.", bg=BG, fg=MUTED,
             font=(FONT, 9)).pack(anchor="w")

    card = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=LINE)
    card.pack(fill="x", pady=(18, 0))
    points = (
        (ACCENT2, "Cosa fa", "Mouse, tastiera, schermo, app aperte, blocco e spegnimento del PC, dal telefono associato."),
        (AMBER, "Solo PC tuoi", "Usalo solo su computer tuoi o che sei autorizzato a gestire. Installarlo sul PC di altri "
                                "senza consenso è vietato e può costituire reato."),
        (GREEN, "Sempre visibile", "Quando un telefono è connesso l'icona vicino all'orologio diventa verde e compare un "
                                   "avviso. Puoi mettere in pausa o revocare l'accesso quando vuoi."),
        (ACCENT, "Privato", "Nessun account e nessun dato raccolto: tutto resta fra il PC e i tuoi dispositivi, cifrato."),
    )
    for i, (color, title, desc) in enumerate(points):
        if i:
            tk.Frame(card, bg=LINE, height=1).pack(fill="x", padx=16)
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=16, pady=10)
        Label(row, text="●", bg=CARD, fg=color, font=(FONT, 11)).pack(side="left", anchor="n", padx=(0, 10))
        col = tk.Frame(row, bg=CARD)
        col.pack(side="left", fill="x", expand=True)
        Label(col, text=title, bg=CARD, fg=FG, font=(FONT, 10, "bold"), anchor="w").pack(fill="x")
        Label(col, text=desc, bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w", justify="left",
                 wraplength=440).pack(fill="x")

    Label(body, text="Proseguendo accetti i Termini d'uso e l'Informativa privacy, consultabili in ogni momento "
                        "dalla finestra di PadLink.", bg=BG, fg=MUTED, font=(FONT, 9), justify="left",
             wraplength=480, anchor="w").pack(fill="x", pady=(14, 0))
    btns = tk.Frame(body, bg=BG)
    btns.pack(fill="x", pady=(16, 0))

    def accept() -> None:
        accepted.set(True)
        root.destroy()

    _button(btns, "Accetto e continuo", accept, "primary").pack(side="right")
    _button(btns, "Esci", root.destroy, "secondary").pack(side="right", padx=8)
    root.mainloop()

    if accepted.get():
        from .fsutil import atomic_write_bytes, ensure_private_dir

        ensure_private_dir(settings.data_dir)
        atomic_write_bytes(path, json.dumps({"version": CONSENT_VERSION, "accepted_at": int(time.time())}).encode())
    return accepted.get()


# ---- entry point ------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    _fix_std_streams()
    _configure_frozen_paths()
    parser = argparse.ArgumentParser(prog="padlink-desktop")
    parser.add_argument("--minimized", action="store_true", help="avvia nell'area di notifica")
    parser.add_argument("--data-dir", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    from .winpkg import is_packaged, started_at_logon

    if not args.minimized and is_packaged() and started_at_logon():
        args.minimized = True  # launched by the MSIX StartupTask (no arguments possible)

    from .config import Settings

    settings = Settings()
    if args.data_dir:
        settings.data_dir = Path(args.data_dir).expanduser()

    instance = SingleInstance()
    if instance.already_running:
        messagebox.showinfo(APP_NAME, _("PadLink è già in esecuzione: cercalo nell'area di notifica (vicino all'orologio)."))
        return 0

    if not ensure_consent(settings):
        return 0

    from .runtime import prepare
    from .logging_setup import audit
    from . import __version__

    rt = prepare(settings)
    server = ServerThread(rt.uvicorn_config())
    server.start()
    if not server.wait_started():
        messagebox.showerror(
            APP_NAME,
            f"Impossibile avviare il server sulla porta {settings.port}.\n"
            "Forse un'altra copia di PadLink (anche da terminale) è già attiva.",
        )
        return 1
    audit("server_start", version=__version__, host=settings.host, port=settings.port, tls=settings.tls,
          mode="desktop")
    threading.Thread(target=rt.start_discovery, name="padlink-mdns", daemon=True).start()
    app = DesktopApp(rt, args.minimized)
    try:
        app.run(server)
    finally:
        rt.stop_discovery()
        server.stop()
        server.join(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
