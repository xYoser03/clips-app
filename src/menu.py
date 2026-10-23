"""
Interactive Application Menu for clipctl.
Supports Fuzzel, Rofi, Wofi, or CLI interactive selection.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import List, Tuple

from src.client import is_daemon_running, send_ipc
from src.config import load_config


def get_menu_items() -> List[Tuple[str, str]]:
    active = is_daemon_running()
    toggle_text = "⏸️ Detener Buffer Continuo" if active else "▶️ Iniciar Buffer Continuo"
    return [
        ("💾 Guardar últimos 30 segundos", "save_30"),
        ("💾 Guardar últimos 60 segundos (1 min)", "save_60"),
        ("💾 Guardar últimos 2 minutos", "save_120"),
        ("💾 Guardar últimos 5 minutos", "save_300"),
        ("💾 Guardar todo el buffer activo", "save_all"),
        (toggle_text, "toggle"),
        ("⚙️ Configuración Completa (Ventana GTK4)", "gui"),
        ("📁 Abrir Carpeta de Videos (~/Videos/Clips)", "open_folder"),
        ("📊 Estado del Buffer y Rendimiento", "status"),
    ]


def run_fuzzel_or_rofi(items: List[Tuple[str, str]]) -> str | None:
    labels = [label for label, _ in items]
    input_text = "\n".join(labels)

    cmd = None
    if shutil.which("fuzzel"):
        cmd = ["fuzzel", "--dmenu", "--prompt=clipctl > ", "-l", str(len(items)), "-w", "45"]
    elif shutil.which("rofi"):
        cmd = ["rofi", "-dmenu", "-p", "clipctl", "-l", str(len(items))]
    elif shutil.which("wofi"):
        cmd = ["wofi", "--dmenu", "--prompt=clipctl", "-L", str(len(items))]

    if not cmd:
        return None

    try:
        proc = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
        if proc.returncode == 0:
            selected_label = proc.stdout.strip()
            for label, action in items:
                if label == selected_label:
                    return action
    except Exception as e:
        print(f"[clipctl-menu] Error running dmenu: {e}", file=sys.stderr)
    return None


def run_terminal_menu(items: List[Tuple[str, str]]) -> str | None:
    print("========================================")
    print("        clipctl - Menú de Acciones      ")
    print("========================================")
    for idx, (label, _) in enumerate(items, 1):
        print(f" [{idx}] {label}")
    print(" [0] Cancelar / Salir")
    print("========================================")

    try:
        choice = input("Selecciona una opción (0-9): ").strip()
        if choice in ("0", "", "q", "exit"):
            return None
        val = int(choice)
        if 1 <= val <= len(items):
            return items[val - 1][1]
    except (ValueError, KeyboardInterrupt, EOFError):
        pass
    return None


def handle_action(action: str) -> int:
    cfg = load_config()
    clips_dir = Path(cfg.get("output", {}).get("directory", Path.home() / "Videos" / "Clips")).expanduser()

    if action == "save_30":
        res = send_ipc("save", seconds=30)
        print(res.get("file", res.get("message")))
    elif action == "save_60":
        res = send_ipc("save", seconds=60)
        print(res.get("file", res.get("message")))
    elif action == "save_120":
        res = send_ipc("save", seconds=120)
        print(res.get("file", res.get("message")))
    elif action == "save_300":
        res = send_ipc("save", seconds=300)
        print(res.get("file", res.get("message")))
    elif action == "save_all":
        res = send_ipc("save")
        print(res.get("file", res.get("message")))
    elif action == "toggle":
        if is_daemon_running():
            send_ipc("stop")
            subprocess.run(["notify-send", "-a", "clipctl", "clipctl", "Buffer de grabación detenido."])
        else:
            send_ipc("start")
            subprocess.run(["notify-send", "-a", "clipctl", "clipctl", "Buffer continuo iniciado."])
    elif action == "gui":
        from src.gui import run_gui
        return run_gui()
    elif action == "open_folder":
        clips_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(clips_dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif action == "status":
        stat = send_ipc("status")
        msg = f"Estado: {stat.get('status')}\nMonitor: {stat.get('monitor')}\nCodec: {stat.get('codec')}\nRAM: ~{stat.get('estimated_ram_mb')}MB"
        subprocess.run(["notify-send", "-a", "clipctl", "-i", "video-x-generic", "clipctl Status", msg])
        print(msg)
    return 0


def run_menu() -> int:
    items = get_menu_items()
    # Check if graphical session
    is_gui = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))
    action = None
    if is_gui and (shutil.which("fuzzel") or shutil.which("rofi") or shutil.which("wofi")):
        action = run_fuzzel_or_rofi(items)
    if not action:
        # Fallback to terminal menu if run from TTY/terminal
        if sys.stdin.isatty():
            action = run_terminal_menu(items)
        else:
            # If not in a terminal and no dmenu was found/selected, open GTK4 GUI
            from src.gui import run_gui
            return run_gui()

    if action:
        return handle_action(action)
    return 0


if __name__ == "__main__":
    sys.exit(run_menu())
