"""PadLink for Windows: tray icon + pairing window around the same secure server.

    python -m kursor desktop [--minimized]

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

APP_NAME = "PadLink"
CONSENT_VERSION = 1
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

BG = "#0b0f17"
CARD = "#141a26"
FG = "#e5e7eb"
MUTED = "#9ca3af"
ACCENT = "#6366f1"
GREEN = "#10b981"
RED = "#ef4444"


# ---- environment -----------------------------------------------------------------------
def _fix_std_streams() -> None:
    # A windowed (no console) executable has no stdout/stderr.
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115


def _bundle_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _assets() -> Path:
    frozen = _bundle_dir() / "kursor" / "assets"
    return frozen if frozen.exists() else Path(__file__).resolve().parent / "assets"


def _legal_dir() -> Path:
    bundled = _bundle_dir() / "legal"
    return bundled if bundled.exists() else Path(__file__).resolve().parents[2] / "docs" / "legal"


def _configure_frozen_paths() -> None:
    if getattr(sys, "frozen", False):
        os.environ.setdefault("KURSOR_STATIC_DIR", str(_bundle_dir() / "client_dist"))


class SingleInstance:
    """Named mutex: a second launch exits instead of fighting over port 8443."""

    def __init__(self) -> None:
        self.handle = None
        self.already_running = False
        if sys.platform == "win32":
            self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\KursorDesktopSingleton")
            self.already_running = ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


# ---- autostart (HKCU, opt-in) -------------------------------------------------------------
def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m kursor desktop --minimized'


def autostart_enabled() -> bool:
    if sys.platform != "win32":
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
        super().__init__(name="kursor-server", daemon=True)
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
        self.devices_sig: tuple = ()
        self.session_expires: float | None = None
        self.qr_photo = None
        self.tray = None
        self.hidden_hint_shown = False
        self.quitting = False

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        # No fixed geometry: Tk sizes the window to its content, which scales with Windows DPI.
        self.root.minsize(400, 500)
        ico = _assets() / "kursor.ico"
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
        elif not self.svc.store.list():
            self.new_pairing()  # first launch: nothing paired yet, show the QR right away
        self.root.after(200, self._tick)

    # -- layout --
    def _style(self) -> None:
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        st.configure("Card.TLabel", background=CARD, foreground=FG)
        st.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI Semibold", 16))
        st.configure("Pin.TLabel", background=CARD, foreground=FG, font=("Consolas", 26, "bold"))
        st.configure("Code.TLabel", background=CARD, foreground="#22d3ee", font=("Consolas", 12, "bold"))
        st.configure("TButton", font=("Segoe UI", 10), padding=8, background="#1f2937", foreground=FG,
                     borderwidth=0)
        st.map("TButton", background=[("active", "#374151")])
        st.configure("Accent.TButton", background=ACCENT, foreground="white")
        st.map("Accent.TButton", background=[("active", "#4f46e5")])
        st.configure("TCheckbutton", background=BG, foreground=FG, font=("Segoe UI", 10))
        st.map("TCheckbutton", background=[("active", BG)])

    def _build(self) -> None:
        pad = {"padx": 16}
        top = ttk.Frame(self.root)
        top.pack(fill="x", pady=(14, 6), **pad)
        ttk.Label(top, text="PadLink", style="Title.TLabel").pack(side="left")
        self.status = ttk.Label(top, text="", foreground=MUTED)
        self.status.pack(side="right")

        # Control banner: always says whether someone is controlling this PC.
        self.banner = tk.Frame(self.root, bg=CARD)
        self.banner.pack(fill="x", pady=6, **pad)
        self.banner_dot = tk.Label(self.banner, text="●", bg=CARD, fg=MUTED, font=("Segoe UI", 14))
        self.banner_dot.pack(side="left", padx=(12, 6), pady=10)
        self.banner_text = tk.Label(self.banner, text="", bg=CARD, fg=FG, font=("Segoe UI", 10), anchor="w",
                                    justify="left", wraplength=250)
        self.banner_text.pack(side="left", fill="x", expand=True)
        self.pause_btn = ttk.Button(self.banner, text="Pausa", command=self.toggle_pause)
        self.pause_btn.pack(side="right", padx=10)

        # Pairing card
        self.pair_card = ttk.Frame(self.root, style="Card.TFrame")
        self.pair_card.pack(fill="x", pady=6, **pad)
        self.qr_label = tk.Label(self.pair_card, bg=CARD)
        self.pin_label = ttk.Label(self.pair_card, style="Pin.TLabel")
        self.code_label = ttk.Label(self.pair_card, style="Code.TLabel")
        self.pair_info = ttk.Label(self.pair_card, style="Muted.TLabel", wraplength=380, justify="center")
        self.pair_btn = ttk.Button(self.pair_card, text="Associa un nuovo telefono", style="Accent.TButton",
                                   command=self.new_pairing)
        self.cancel_btn = ttk.Button(self.pair_card, text="Chiudi associazione", command=self.close_pairing)
        self._render_pairing(None)

        # Devices
        ttk.Label(self.root, text="Dispositivi associati", foreground=MUTED).pack(anchor="w", pady=(12, 2), **pad)
        dev = ttk.Frame(self.root, style="Card.TFrame")
        dev.pack(fill="both", expand=True, pady=4, **pad)
        self.dev_list = tk.Listbox(dev, bg=CARD, fg=FG, selectbackground=ACCENT, borderwidth=0,
                                   highlightthickness=0, font=("Segoe UI", 10), activestyle="none", height=5)
        self.dev_list.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Button(dev, text="Revoca il dispositivo selezionato", command=self.revoke_selected).pack(
            fill="x", padx=8, pady=(0, 8))
        self.dev_ids: list[str] = []

        # Footer
        foot = ttk.Frame(self.root)
        foot.pack(fill="x", pady=(6, 12), **pad)
        self.autostart_var = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(foot, text="Avvia PadLink all'accesso a Windows", variable=self.autostart_var,
                        command=self._toggle_autostart).pack(anchor="w")
        links = ttk.Frame(foot)
        links.pack(fill="x", pady=(8, 0))
        for text, cmd in (("Privacy", lambda: self.show_doc("PRIVACY.md", "Privacy")),
                          ("Termini", lambda: self.show_doc("TERMS.md", "Termini d'uso")),
                          ("Licenze", lambda: self.show_doc("licenses/windows-third-party.txt", "Licenze open source")),
                          ("Registro accessi", self.open_logs),
                          ("Esci", self.quit)):
            ttk.Button(links, text=text, command=cmd).pack(side="left", padx=(0, 6))

    # -- pairing --
    def new_pairing(self) -> None:
        session = self.svc.pairing.new_session()
        self.audit("pairing_opened", source="desktop")
        self._render_pairing(session)

    def close_pairing(self) -> None:
        self.svc.pairing.close()
        self._render_pairing(None)

    def _render_pairing(self, session: Any) -> None:
        for w in (self.qr_label, self.pin_label, self.code_label, self.pair_info, self.pair_btn, self.cancel_btn):
            w.pack_forget()
        if session is None:
            self.session_expires = None
            self.pair_info.configure(text="Per collegare un telefono installa l'app PadLink (o apri il browser) "
                                          "e premi il pulsante qui sotto.")
            self.pair_info.pack(pady=(14, 8), padx=12)
            self.pair_btn.pack(pady=(0, 14))
            return

        import qrcode
        from PIL import ImageTk

        from .pairinfo import current_verification_code, pairing_url

        url = pairing_url(self.settings, session.code)
        img = qrcode.make(url, box_size=6, border=2).get_image().convert("RGB")
        self.qr_photo = ImageTk.PhotoImage(img)
        self.qr_label.configure(image=self.qr_photo)
        self.qr_label.pack(pady=(14, 6))
        self.pin_label.configure(text=f"{session.pin[:3]} {session.pin[3:]}")
        self.pin_label.pack()
        verify = current_verification_code(self.settings)
        if verify:
            self.code_label.configure(text=f"Codice di verifica  {verify}")
            self.code_label.pack(pady=(2, 4))
        self.session_expires = session.expires_at
        self.pair_info.pack(pady=(2, 6), padx=12)
        self.cancel_btn.pack(pady=(0, 14))
        self._update_countdown()

    def _update_countdown(self) -> None:
        if self.session_expires is None:
            return
        left = int(self.session_expires - time.time())
        active = self.svc.pairing.active_until()
        if left <= 0 or active is None:
            self._render_pairing(None)  # expired or already used: never leave a stale QR on screen
            return
        self.pair_info.configure(
            text=f"Inquadra il QR con l'app PadLink, oppure inserisci indirizzo e PIN.\n"
                 f"Valido ancora {left // 60}:{left % 60:02d} · monouso · non condividerlo")

    # -- devices / status --
    def _refresh(self) -> None:
        devices = self.svc.store.list()
        names = {d.id: d.name for d in devices}
        connected = set(self.svc.registry.device_ids())

        for dev_id in connected - self.connected:
            self._notify(f"{names.get(dev_id, 'Un dispositivo')} sta controllando questo PC")
        self.connected = connected

        if self.svc.paused:
            self.banner_dot.configure(fg=RED)
            self.banner_text.configure(text="Controllo in PAUSA: nessun telefono può controllare il PC.")
            self.pause_btn.configure(text="Riprendi")
        elif connected:
            who = ", ".join(sorted(names.get(i, "?") for i in connected))
            self.banner_dot.configure(fg=GREEN)
            self.banner_text.configure(text=f"Controllato ora da: {who}")
            self.pause_btn.configure(text="Pausa")
        else:
            self.banner_dot.configure(fg=MUTED)
            self.banner_text.configure(text="Nessun dispositivo connesso.")
            self.pause_btn.configure(text="Pausa")

        sig = tuple((d.id, d.name, int(d.last_seen) // 60, d.id in connected) for d in devices)
        if sig != self.devices_sig:
            self.devices_sig = sig
            self.dev_list.delete(0, "end")
            self.dev_ids = [d.id for d in devices]
            for d in devices:
                live = "  ● connesso" if d.id in connected else ""
                self.dev_list.insert("end", f"{d.name}  ·  ultimo accesso {_ago(d.last_seen)}{live}")
            if not devices:
                self.dev_list.insert("end", "Nessun dispositivo associato.")

        self.status.configure(text=f"{len(devices)} associati")
        self._update_tray(bool(connected) and not self.svc.paused)

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

    def revoke_selected(self) -> None:
        sel = self.dev_list.curselection()
        if not sel or sel[0] >= len(self.dev_ids):
            return
        dev_id = self.dev_ids[sel[0]]
        name = next((d.name for d in self.svc.store.list() if d.id == dev_id), dev_id)
        if not messagebox.askyesno(APP_NAME, f'Revocare "{name}"?\nNon potrà più controllare il PC '
                                             f"finché non verrà associato di nuovo."):
            return
        if self.svc.store.revoke(dev_id):
            self.audit("device_revoked", device=dev_id, by="desktop")
            self._close_sockets([dev_id], 4409, "revoked")
        self.devices_sig = ()

    def toggle_pause(self) -> None:
        self.svc.paused = not self.svc.paused
        self.audit("control_paused" if self.svc.paused else "control_resumed", by="desktop")
        if self.svc.paused:
            self._close_sockets(self.svc.registry.device_ids(), 4423, "paused")
        self._refresh()

    def _toggle_autostart(self) -> None:
        try:
            set_autostart(self.autostart_var.get())
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Impossibile modificare l'avvio automatico: {exc}")
            self.autostart_var.set(autostart_enabled())

    def open_logs(self) -> None:
        os.startfile(self.settings.log_dir)  # type: ignore[attr-defined]  # noqa: S606

    def show_doc(self, filename: str, title: str) -> None:
        path = _legal_dir() / filename
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = "Documento non trovato."
        win = tk.Toplevel(self.root, bg=BG)
        win.title(f"{APP_NAME} · {title}")
        win.geometry("620x640")
        box = tk.Text(win, wrap="word", bg=CARD, fg=FG, font=("Segoe UI", 10), borderwidth=0, padx=14, pady=12)
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
        if self.connected and not messagebox.askyesno(APP_NAME, "Un telefono è connesso. Chiudere PadLink?"):
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
            pystray.MenuItem("Apri PadLink", lambda: post(self.show), default=True),
            pystray.MenuItem("Associa un nuovo telefono", lambda: post(lambda: (self.show(), self.new_pairing()))),
            pystray.MenuItem("Pausa controllo", lambda: post(self.toggle_pause), checked=lambda _: self.svc.paused),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Esci", lambda: post(lambda: (self.show(), self.quit()))),
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
                self.tray.notify(message, APP_NAME)
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
    root.geometry("560x520")
    ico = _assets() / "kursor.ico"
    if ico.exists():
        root.iconbitmap(default=str(ico))
    accepted = tk.BooleanVar(value=False)
    text = (
        "PadLink permette di controllare questo PC (mouse, tastiera, schermo, blocco e spegnimento) "
        "da uno smartphone associato.\n\n"
        "• Usalo solo su computer tuoi o che sei autorizzato a gestire. Installarlo sul PC di altre persone "
        "senza il loro consenso è vietato e può costituire reato.\n"
        "• Chi possiede un telefono associato può controllare il PC: non condividere PIN o QR e revoca subito "
        "i dispositivi persi.\n"
        "• Quando un telefono è connesso l'icona nell'area di notifica diventa verde e compare un avviso. "
        "Puoi mettere in pausa il controllo in qualsiasi momento.\n"
        "• PadLink non raccoglie dati: tutto resta fra il PC e i tuoi dispositivi, in connessione cifrata.\n\n"
        "Proseguendo accetti i Termini d'uso e l'Informativa privacy (consultabili anche dopo, dalla finestra di PadLink)."
    )
    tk.Label(root, text="Benvenuto in PadLink", bg=BG, fg=FG, font=("Segoe UI Semibold", 16)).pack(
        anchor="w", padx=20, pady=(18, 8))
    tk.Label(root, text=text, bg=BG, fg=FG, font=("Segoe UI", 10), justify="left", wraplength=510).pack(
        anchor="w", padx=20)
    btns = tk.Frame(root, bg=BG)
    btns.pack(side="bottom", fill="x", padx=20, pady=18)

    def accept() -> None:
        accepted.set(True)
        root.destroy()

    tk.Button(btns, text="Accetto e continuo", command=accept, bg=ACCENT, fg="white", relief="flat",
              font=("Segoe UI", 10, "bold"), padx=14, pady=6).pack(side="right")
    tk.Button(btns, text="Esci", command=root.destroy, relief="flat", padx=14, pady=6).pack(side="right", padx=8)
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
    parser = argparse.ArgumentParser(prog="kursor-desktop")
    parser.add_argument("--minimized", action="store_true", help="avvia nell'area di notifica")
    parser.add_argument("--data-dir", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    from .config import Settings

    settings = Settings()
    if args.data_dir:
        settings.data_dir = Path(args.data_dir).expanduser()

    instance = SingleInstance()
    if instance.already_running:
        messagebox.showinfo(APP_NAME, "PadLink è già in esecuzione: cercalo nell'area di notifica (vicino all'orologio).")
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
    app = DesktopApp(rt, args.minimized)
    try:
        app.run(server)
    finally:
        server.stop()
        server.join(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
