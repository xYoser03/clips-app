"""
GTK4 Configuration Interface for clipctl.
Opens on demand with zero resident processes after closing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Tuple

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from src.client import is_daemon_running, send_ipc
from src.config import CONFIG_FILE, estimate_ram_mb, load_config, save_config
from src.hyprland import update_hyprland_bind


def get_available_monitors() -> List[Tuple[str, str]]:
    """Return list of (id, display_label) from hyprctl monitors -j."""
    monitors = []
    try:
        res = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=2.0)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            for m in data:
                name = m.get("name", "")
                w = m.get("width", 0)
                h = m.get("height", 0)
                rr = round(m.get("refreshRate", 60))
                model = m.get("model", "")
                label = f"{name} ({w}x{h} @ {rr}Hz - {model})"
                monitors.append((name, label))
    except Exception as e:
        print(f"[clipctl-gui] Error fetching monitors: {e}")

    if not monitors:
        monitors.append(("DP-2", "DP-2 (Monitor Principal)"))

    # Add portal option
    monitors.append(("portal", "Captura por Portal (Ventana / Selección Wayland)"))
    return monitors


def get_supported_codecs() -> List[Tuple[str, str]]:
    """Detect NVENC supported hardware codecs using gpu-screen-recorder --info."""
    all_codecs = [
        ("h264", "H.264 (NVENC - Máxima compatibilidad)"),
        ("hevc", "HEVC / H.265 (NVENC - Alta eficiencia)"),
        ("av1", "AV1 (NVENC - Próxima generación, RTX 40+)"),
    ]
    supported = []
    try:
        res = subprocess.run(["gpu-screen-recorder", "--info"], capture_output=True, text=True, timeout=2.0)
        if res.returncode == 0:
            output = res.stdout
            lines = [l.strip() for l in output.splitlines()]
            for cid, label in all_codecs:
                if cid in lines:
                    supported.append((cid, label))
    except Exception:
        pass

    return supported if supported else all_codecs


class ClipctlApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="com.clipctl.gui")
        self.config = load_config()

    def do_activate(self) -> None:
        win = ClipctlWindow(self, self.config)
        win.present()


class ClipctlWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, config: Dict[str, Any]) -> None:
        super().__init__(application=app, title="clipctl - Configuración de Instant Replay")
        self.set_default_size(580, 720)
        self.config = config

        # Main scrollable container
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_child(scrolled)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        scrolled.set_child(main_box)

        # Header Title
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_lbl = Gtk.Label(label="<b>Instant Replay (ShadowPlay para Hyprland)</b>", use_markup=True)
        title_lbl.set_halign(Gtk.Align.START)
        desc_lbl = Gtk.Label(
            label="Grabación en búfer circular acelerada por NVIDIA NVENC (DMA-BUF / KMS)."
        )
        desc_lbl.set_halign(Gtk.Align.START)
        title_box.append(title_lbl)
        title_box.append(desc_lbl)
        main_box.append(title_box)

        main_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Section 1: Estado del Servicio
        sec1 = self.create_section("1. Estado y Servicio")
        main_box.append(sec1)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.status_lbl = Gtk.Label()
        self.status_lbl.set_halign(Gtk.Align.START)
        self.update_status_label()

        self.btn_toggle_buffer = Gtk.Button()
        self.update_toggle_button()
        self.btn_toggle_buffer.connect("clicked", self.on_toggle_buffer_clicked)

        status_box.append(self.status_lbl)
        status_box.append(self.btn_toggle_buffer)
        sec1.append(status_box)

        self.chk_autostart = Gtk.CheckButton(label="Iniciar automáticamente con la sesión (systemd --user)")
        self.chk_autostart.set_active(self.is_service_enabled())
        sec1.append(self.chk_autostart)

        # Section 2: Buffer de Repetición y Memoria
        sec2 = self.create_section("2. Buffer de Repetición y Memoria")
        main_box.append(sec2)

        # Buffer Durations
        self.buffer_options = [
            (30, "30 segundos"),
            (60, "1 minuto"),
            (120, "2 minutos (Recomendado)"),
            (300, "5 minutos"),
            (600, "10 minutos"),
            (900, "15 minutos"),
            (1200, "20 minutos"),
        ]
        grid_buf = Gtk.Grid(column_spacing=12, row_spacing=8)
        sec2.append(grid_buf)

        grid_buf.attach(Gtk.Label(label="Duración del Buffer:", halign=Gtk.Align.START), 0, 0, 1, 1)
        self.combo_buffer = Gtk.DropDown.new_from_strings([lbl for _, lbl in self.buffer_options])
        current_buf = self.config.get("replay", {}).get("buffer_seconds", 120)
        self.select_option_by_value(self.combo_buffer, self.buffer_options, current_buf)
        self.combo_buffer.connect("notify::selected", self.on_buffer_or_bitrate_changed)
        grid_buf.attach(self.combo_buffer, 1, 0, 1, 1)

        grid_buf.attach(Gtk.Label(label="Duración a Guardar:", halign=Gtk.Align.START), 0, 1, 1, 1)
        self.combo_save_sec = Gtk.DropDown.new_from_strings([lbl for _, lbl in self.buffer_options])
        current_save = self.config.get("replay", {}).get("default_save_seconds", 120)
        self.select_option_by_value(self.combo_save_sec, self.buffer_options, current_save)
        grid_buf.attach(self.combo_save_sec, 1, 1, 1, 1)

        # Storage type
        grid_buf.attach(Gtk.Label(label="Almacenamiento del Búfer:", halign=Gtk.Align.START), 0, 2, 1, 1)
        self.storage_options = [("ram", "RAM (Ultrarrápido, 0 desgaste SSD)"), ("disk", "Disco NVMe / SSD")]
        self.combo_storage = Gtk.DropDown.new_from_strings([lbl for _, lbl in self.storage_options])
        cur_storage = self.config.get("replay", {}).get("storage", "ram")
        self.select_option_by_value(self.combo_storage, self.storage_options, cur_storage)
        grid_buf.attach(self.combo_storage, 1, 2, 1, 1)

        # RAM Estimate label
        self.ram_lbl = Gtk.Label(use_markup=True)
        self.ram_lbl.set_halign(Gtk.Align.START)
        sec2.append(self.ram_lbl)

        # Section 3: Captura de Video y NVENC
        sec3 = self.create_section("3. Captura y Encoder NVENC")
        main_box.append(sec3)

        grid_video = Gtk.Grid(column_spacing=12, row_spacing=8)
        sec3.append(grid_video)

        # Monitor
        self.monitor_list = get_available_monitors()
        grid_video.attach(Gtk.Label(label="Monitor / Fuente:", halign=Gtk.Align.START), 0, 0, 1, 1)
        self.combo_monitor = Gtk.DropDown.new_from_strings([lbl for _, lbl in self.monitor_list])
        cur_mon = self.config.get("video", {}).get("monitor", "DP-2")
        self.select_option_by_value(self.combo_monitor, self.monitor_list, cur_mon)
        grid_video.attach(self.combo_monitor, 1, 0, 1, 1)

        # Codec
        self.codec_list = get_supported_codecs()
        grid_video.attach(Gtk.Label(label="Codec Hardware NVENC:", halign=Gtk.Align.START), 0, 1, 1, 1)
        self.combo_codec = Gtk.DropDown.new_from_strings([lbl for _, lbl in self.codec_list])
        cur_codec = self.config.get("video", {}).get("codec", "h264")
        self.select_option_by_value(self.combo_codec, self.codec_list, cur_codec)
        grid_video.attach(self.combo_codec, 1, 1, 1, 1)

        # FPS
        self.fps_options = [(30, "30 FPS"), (60, "60 FPS (Estándar)"), (120, "120 FPS (Alta fluidez)"), (180, "180 FPS (Nativo DP-2)")]
        grid_video.attach(Gtk.Label(label="Cuadros por Segundo (FPS):", halign=Gtk.Align.START), 0, 2, 1, 1)
        self.combo_fps = Gtk.DropDown.new_from_strings([lbl for _, lbl in self.fps_options])
        cur_fps = self.config.get("video", {}).get("fps", 60)
        self.select_option_by_value(self.combo_fps, self.fps_options, cur_fps)
        grid_video.attach(self.combo_fps, 1, 2, 1, 1)

        # Bitrate
        grid_video.attach(Gtk.Label(label="Bitrate (Calidad de Video):", halign=Gtk.Align.START), 0, 3, 1, 1)
        cur_bitrate = self.config.get("video", {}).get("bitrate", 30000)
        self.bitrate_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5000, 80000, 5000)
        self.bitrate_scale.set_value(cur_bitrate)
        self.bitrate_scale.set_hexpand(True)
        self.bitrate_scale.set_digits(0)
        self.bitrate_scale.connect("value-changed", self.on_buffer_or_bitrate_changed)
        grid_video.attach(self.bitrate_scale, 1, 3, 1, 1)

        # Section 4: Audio en Pistas Separadas
        sec4 = self.create_section("4. Configuración de Audio (Pistas Separadas)")
        main_box.append(sec4)

        self.chk_audio_desktop = Gtk.CheckButton(label="Grabar audio del juego y sistema (Pista 1)")
        self.chk_audio_desktop.set_active(self.config.get("audio", {}).get("record_desktop", True))
        sec4.append(self.chk_audio_desktop)

        self.chk_audio_mic = Gtk.CheckButton(label="Grabar micrófono (Pista 2 separada - ideal para edición)")
        self.chk_audio_mic.set_active(self.config.get("audio", {}).get("record_mic", False))
        sec4.append(self.chk_audio_mic)

        # Section 5: Atajo Global y Destino
        sec5 = self.create_section("5. Atajo en Hyprland y Guardado")
        main_box.append(sec5)

        grid_bind = Gtk.Grid(column_spacing=12, row_spacing=8)
        sec5.append(grid_bind)

        grid_bind.attach(Gtk.Label(label="Atajo Global para Guardar:", halign=Gtk.Align.START), 0, 0, 1, 1)
        self.entry_bind = Gtk.Entry()
        self.entry_bind.set_text(self.config.get("hyprland", {}).get("keybind", "SUPER + F10"))
        grid_bind.attach(self.entry_bind, 1, 0, 1, 1)

        grid_bind.attach(Gtk.Label(label="Carpeta de Clips:", halign=Gtk.Align.START), 0, 1, 1, 1)
        self.entry_dir = Gtk.Entry()
        self.entry_dir.set_text(self.config.get("output", {}).get("directory", str(Path.home() / "Videos" / "Clips")))
        grid_bind.attach(self.entry_dir, 1, 1, 1, 1)

        self.chk_notif = Gtk.CheckButton(label="Mostrar notificación de escritorio al guardar")
        self.chk_notif.set_active(self.config.get("notifications", {}).get("enabled", True))
        sec5.append(self.chk_notif)

        self.chk_sound = Gtk.CheckButton(label="Reproducir sonido de obturador al guardar")
        self.chk_sound.set_active(self.config.get("notifications", {}).get("sound", True))
        sec5.append(self.chk_sound)

        # Update initial RAM estimation
        self.update_ram_estimate()

        # Bottom Action Buttons
        main_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.END)
        main_box.append(btn_box)

        self.btn_save = Gtk.Button(label="Guardar y Aplicar")
        self.btn_save.add_css_class("suggested-action")
        self.btn_save.connect("clicked", self.on_save_applied)

        btn_close = Gtk.Button(label="Cerrar")
        btn_close.connect("clicked", lambda b: self.close())

        btn_box.append(btn_close)
        btn_box.append(self.btn_save)

    def create_section(self, title: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        lbl = Gtk.Label(label=f"<b>{title}</b>", use_markup=True)
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)
        return box

    def select_option_by_value(self, dropdown: Gtk.DropDown, options: List[Tuple[Any, str]], target_val: Any) -> None:
        for idx, (val, _) in enumerate(options):
            if str(val).lower() == str(target_val).lower():
                dropdown.set_selected(idx)
                return
        dropdown.set_selected(0)

    def on_buffer_or_bitrate_changed(self, *args: Any) -> None:
        self.update_ram_estimate()

    def update_ram_estimate(self) -> None:
        buf_idx = self.combo_buffer.get_selected()
        buf_sec = self.buffer_options[buf_idx][0] if buf_idx < len(self.buffer_options) else 120
        bitrate = int(self.bitrate_scale.get_value())

        mb = round(estimate_ram_mb(buf_sec, bitrate), 1)
        if mb > 2000:
            self.ram_lbl.set_markup(
                f"<span foreground='#f5a97f'><b>⚠️ Consumo estimado de RAM: {mb} MB</b> (Supera 2 GB. Se sugiere cambiar a Disco NVMe)</span>"
            )
        else:
            self.ram_lbl.set_markup(
                f"<span foreground='#a6da95'><b>Consumo estimado de RAM:</b> ~{mb} MB (Ligero y seguro)</span>"
            )

    def update_status_label(self) -> None:
        active = is_daemon_running()
        if active:
            self.status_lbl.set_markup("<span foreground='#a6da95'>● <b>Buffer de Replay Activo</b></span>")
        else:
            self.status_lbl.set_markup("<span foreground='#ed8796'>○ <b>Buffer Detenido</b></span>")

    def update_toggle_button(self) -> None:
        active = is_daemon_running()
        self.btn_toggle_buffer.set_label("Detener Grabación" if active else "Iniciar Grabación")

    def is_service_enabled(self) -> bool:
        try:
            res = subprocess.run(["systemctl", "--user", "is-enabled", "clipctl.service"], capture_output=True, text=True)
            return res.stdout.strip() == "enabled"
        except Exception:
            return False

    def on_toggle_buffer_clicked(self, btn: Gtk.Button) -> None:
        active = is_daemon_running()
        if active:
            send_ipc("stop")
        else:
            send_ipc("start")
        GLib.timeout_add(300, lambda: (self.update_status_label(), self.update_toggle_button(), False))

    def on_save_applied(self, btn: Gtk.Button) -> None:
        # Extract UI values
        buf_idx = self.combo_buffer.get_selected()
        buf_sec = self.buffer_options[buf_idx][0]

        save_idx = self.combo_save_sec.get_selected()
        save_sec = self.buffer_options[save_idx][0]

        storage_idx = self.combo_storage.get_selected()
        storage = self.storage_options[storage_idx][0]

        mon_idx = self.combo_monitor.get_selected()
        monitor = self.monitor_list[mon_idx][0]

        codec_idx = self.combo_codec.get_selected()
        codec = self.codec_list[codec_idx][0]

        fps_idx = self.combo_fps.get_selected()
        fps = self.fps_options[fps_idx][0]

        bitrate = int(self.bitrate_scale.get_value())
        keybind = self.entry_bind.get_text().strip() or "SUPER + F10"
        out_dir = self.entry_dir.get_text().strip()

        # Update config dict
        self.config["replay"]["buffer_seconds"] = buf_sec
        self.config["replay"]["default_save_seconds"] = save_sec
        self.config["replay"]["storage"] = storage

        self.config["video"]["monitor"] = monitor
        self.config["video"]["codec"] = codec
        self.config["video"]["fps"] = fps
        self.config["video"]["bitrate"] = bitrate

        self.config["audio"]["record_desktop"] = self.chk_audio_desktop.get_active()
        self.config["audio"]["record_mic"] = self.chk_audio_mic.get_active()

        self.config["hyprland"]["keybind"] = keybind
        self.config["output"]["directory"] = out_dir

        self.config["notifications"]["enabled"] = self.chk_notif.get_active()
        self.config["notifications"]["sound"] = self.chk_sound.get_active()

        # Save to disk
        save_config(self.config)

        # Update Hyprland hotkey & windowrules
        update_hyprland_bind(keybind)

        # Update systemd autostart
        enable_service = self.chk_autostart.get_active()
        cmd = ["systemctl", "--user", "enable" if enable_service else "disable", "clipctl.service"]
        try:
            subprocess.run(cmd, capture_output=True)
        except Exception:
            pass

        # Restart recording with new settings
        if is_daemon_running():
            send_ipc("restart")

        self.update_status_label()
        self.update_toggle_button()

        # Visual feedback on button
        btn.set_label("✓ Configuración Aplicada!")
        GLib.timeout_add(1500, lambda: (btn.set_label("Guardar y Aplicar"), False))


def run_gui() -> int:
    app = ClipctlApp()
    return app.run(sys.argv[:1])


if __name__ == "__main__":
    sys.exit(run_gui())
