"""
System Tray (StatusNotifierItem) implementation for clipctl.
Displays a tray icon in the background applications bar/panel with quick actions.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, GLib, Gtk

from src.client import is_daemon_running, send_ipc
from src.config import load_config


class ClipctlTray:
    def __init__(self) -> None:
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "clipctl",
            "media-record",
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("clipctl - Instant Replay")

        self.menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label="● Conectando...")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Save actions submenu or direct items
        save_menu = Gtk.Menu()
        save_parent = Gtk.MenuItem(label="💾 Guardar Clip")
        save_parent.set_submenu(save_menu)

        for sec, label in [
            (30, "Últimos 30 segundos"),
            (60, "Últimos 60 segundos (1 min)"),
            (120, "Últimos 2 minutos"),
            (300, "Últimos 5 minutos"),
            (None, "Todo el buffer activo"),
        ]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", self.on_save_clip, sec)
            save_menu.append(item)

        self.menu.append(save_parent)

        # Direct quick save
        item_quick = Gtk.MenuItem(label="⚡ Guardar Ahora (Atajo)")
        item_quick.connect("activate", self.on_save_clip, None)
        self.menu.append(item_quick)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Toggle recording
        self.toggle_item = Gtk.MenuItem(label="⏸️ Pausar Grabación")
        self.toggle_item.connect("activate", self.on_toggle_recording)
        self.menu.append(self.toggle_item)

        # Settings
        item_gui = Gtk.MenuItem(label="⚙️ Configuración...")
        item_gui.connect("activate", self.on_open_gui)
        self.menu.append(item_gui)

        # Open clips folder
        item_folder = Gtk.MenuItem(label="📁 Abrir Carpeta de Clips")
        item_folder.connect("activate", self.on_open_folder)
        self.menu.append(item_folder)

        self.menu.append(Gtk.SeparatorMenuItem())

        # Exit tray
        item_quit = Gtk.MenuItem(label="❌ Cerrar Icono de Bandeja")
        item_quit.connect("activate", lambda _: Gtk.main_quit())
        self.menu.append(item_quit)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        # Auto-start recording on tray startup if stopped
        if not is_daemon_running():
            send_ipc("start")

        # Periodic status refresh
        GLib.timeout_add_seconds(3, self.refresh_status)
        self.refresh_status()

    def refresh_status(self) -> bool:
        def query():
            stat = send_ipc("status")
            GLib.idle_add(self.apply_status, stat)

        threading.Thread(target=query, daemon=True).start()
        return True

    def apply_status(self, stat: dict[str, Any]) -> None:
        status = stat.get("status")
        if status == "recording":
            buf = stat.get("buffer_seconds", 120)
            mon = stat.get("monitor", "DP-2")
            fps = stat.get("fps", 60)
            self.indicator.set_icon_full("media-record", "Grabando")
            self.status_item.set_label(f"● Grabando ({buf}s @ {fps}fps - {mon})")
            self.toggle_item.set_label("⏸️ Detener Buffer Continuo")
        else:
            self.indicator.set_icon_full("media-record-symbolic", "Detenido")
            self.status_item.set_label("○ Buffer Detenido")
            self.toggle_item.set_label("▶️ Iniciar Buffer Continuo")

    def on_save_clip(self, widget: Gtk.MenuItem, seconds: int | None) -> None:
        def do_save():
            if seconds:
                send_ipc("save", seconds=seconds)
            else:
                send_ipc("save")

        threading.Thread(target=do_save, daemon=True).start()

    def on_toggle_recording(self, widget: Gtk.MenuItem) -> None:
        def do_toggle():
            if is_daemon_running():
                send_ipc("stop")
            else:
                send_ipc("start")
            self.refresh_status()

        threading.Thread(target=do_toggle, daemon=True).start()

    def on_open_gui(self, widget: Gtk.MenuItem) -> None:
        subprocess.Popen([sys.executable, "-m", "src.client", "gui"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def on_open_folder(self, widget: Gtk.MenuItem) -> None:
        cfg = load_config()
        clips_dir = Path(cfg.get("output", {}).get("directory", Path.home() / "Videos" / "Clips")).expanduser()
        clips_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(clips_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_tray() -> int:
    # Ensure single instance
    app = ClipctlTray()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(run_tray())
