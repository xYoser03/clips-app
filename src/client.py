"""
CLI client module for clipctl.
Communicates with clipctl daemon over Unix socket.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from src.config import CONFIG_FILE, estimate_ram_mb, load_config, save_config

RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
CLIPCTL_SOCK = RUNTIME_DIR / "clipctl.sock"


def send_ipc(action: str, **kwargs: Any) -> Dict[str, Any]:
    """Send a JSON command to the daemon socket and return response."""
    if not CLIPCTL_SOCK.exists():
        return {"status": "error", "message": "Daemon not running (socket missing)"}

    payload = {"action": action, **kwargs}
    data = (json.dumps(payload) + "\n").encode("utf-8")

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10.0)
        s.connect(str(CLIPCTL_SOCK))
        s.sendall(data)
        response_data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response_data += chunk
            if b"\n" in chunk:
                break
        s.close()
        return json.loads(response_data.decode("utf-8"))
    except Exception as e:
        return {"status": "error", "message": f"IPC error: {e}"}


def is_daemon_running() -> bool:
    resp = send_ipc("status")
    return resp.get("status") in ("recording", "stopped")


def cmd_start(args: argparse.Namespace) -> int:
    if is_daemon_running():
        resp = send_ipc("start")
        print(f"[clipctl] {resp.get('message', 'Recording started')}")
        return 0

    # If daemon is not running, try starting systemd service first, or start daemon directly
    try:
        res = subprocess.run(["systemctl", "--user", "start", "clipctl.service"], capture_output=True, text=True)
        if res.returncode == 0:
            for _ in range(20):
                if CLIPCTL_SOCK.exists():
                    break
                time.sleep(0.1)
            print("[clipctl] Servicio systemd clipctl iniciado exitosamente.")
            return 0
    except Exception:
        pass

    # Fallback: start daemon directly in background
    cmd = [sys.executable, "-m", "src.daemon"]
    project_root = Path(__file__).resolve().parent.parent
    proc = subprocess.Popen(cmd, cwd=str(project_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if CLIPCTL_SOCK.exists():
            break
        time.sleep(0.1)

    print(f"[clipctl] Daemon iniciado en segundo plano (PID: {proc.pid}).")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    resp = send_ipc("stop")
    print(f"[clipctl] {resp.get('message', 'Recording stopped')}")
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    resp = send_ipc("restart")
    print(f"[clipctl] {resp.get('message', 'Recording restarted')}")
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    seconds = args.seconds
    resp = send_ipc("save", seconds=seconds)
    if resp.get("status") == "ok":
        file_path = resp.get("file")
        size_mb = resp.get("size_mb", 0)
        sec = resp.get("seconds_saved")
        print(f"✓ Clip guardado exitosamente: {file_path} ({size_mb} MB, últimos {sec}s)")
        return 0
    else:
        print(f"✗ Error al guardar clip: {resp.get('message', 'Error desconocido')}", file=sys.stderr)
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    resp = send_ipc("status")
    if args.json:
        print(json.dumps(resp, indent=2))
        return 0

    if resp.get("status") == "error":
        print("Estado: Daemon no está corriendo.")
        return 1

    status_str = "GRABANDO (Buffer Activo)" if resp.get("status") == "recording" else "DETENIDO"
    print("========================================")
    print("            clipctl Status              ")
    print("========================================")
    print(f" Estado:           {status_str}")
    print(f" Monitor:          {resp.get('monitor')}")
    print(f" Codec:            {resp.get('codec').upper()} (NVENC)")
    print(f" FPS / Res:        {resp.get('fps')} FPS @ {resp.get('resolution')}")
    print(f" Bitrate:          {resp.get('bitrate_kbps')} kbps")
    print(f" Buffer:           {resp.get('buffer_seconds')} segundos ({resp.get('storage').upper()})")
    print(f" Consumo RAM Est.: {resp.get('estimated_ram_mb')} MB")
    print(f" Tiempo activo:    {resp.get('uptime_seconds')} s")
    print(f" Destino clips:    {resp.get('output_dir')}")
    print("========================================")
    return 0


def cmd_menu(args: argparse.Namespace) -> int:
    """Launch the interactive application menu (fuzzel/rofi/terminal)."""
    from src.menu import run_menu
    return run_menu()


def cmd_config(args: argparse.Namespace) -> int:
    """Show or edit configuration."""
    cfg = load_config()
    if args.key and args.val:
        parts = args.key.split(".")
        if len(parts) == 2:
            sec, k = parts
            if sec in cfg and k in cfg[sec]:
                val = args.val
                # cast if int or bool
                if val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
                elif val.isdigit():
                    val = int(val)
                cfg[sec][k] = val
                save_config(cfg)
                print(f"[clipctl] Configuración actualizada: {sec}.{k} = {val}")
                return 0
        print(f"Error: Clave '{args.key}' no válida. Usa formato seccion.clave (ej: video.fps)")
        return 1

    print(f"Archivo de configuración: {CONFIG_FILE}")
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            print(f.read())
    return 0


def cmd_tray(args: argparse.Namespace) -> int:
    """Launch the system tray indicator."""
    from src.tray import run_tray
    return run_tray()


def cmd_gui(args: argparse.Namespace) -> int:
    """Launch the GTK4 GUI configuration interface."""
    from src.gui import run_gui
    return run_gui()


def cmd_daemon(args: argparse.Namespace) -> int:
    """Run the daemon in foreground (for systemd)."""
    from src.daemon import main as daemon_main
    daemon_main()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="clipctl",
        description="Sistema de Instant Replay ultraligero para Hyprland + NVIDIA (NVENC)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # daemon
    subparsers.add_parser("daemon", help="Ejecuta el daemon en primer plano (usado por systemd)")

    # tray
    subparsers.add_parser("tray", help="Inicia el icono en la bandeja del sistema (aplicaciones de segundo plano)")

    # start
    subparsers.add_parser("start", help="Inicia la grabación del buffer continuo")

    # stop
    subparsers.add_parser("stop", help="Detiene la grabación del buffer continuo")

    # restart
    subparsers.add_parser("restart", help="Reinicia la grabación aplicando nueva configuración")

    # save
    save_parser = subparsers.add_parser("save", help="Guarda instantáneamente el replay")
    save_parser.add_argument("seconds", type=int, nargs="?", default=None,
                             help="Duración en segundos a guardar (por defecto todo el buffer)")

    # status
    status_parser = subparsers.add_parser("status", help="Muestra el estado actual del buffer")
    status_parser.add_argument("--json", action="store_true", help="Salida en formato JSON (útil para Waybar)")

    # menu
    subparsers.add_parser("menu", help="Abre el menú interactivo de acciones rápidas (fuzzel/rofi/terminal)")

    # config
    cfg_parser = subparsers.add_parser("config", help="Muestra o edita la configuración TOML")
    cfg_parser.add_argument("key", nargs="?", default=None, help="Clave a modificar (ej. video.fps)")
    cfg_parser.add_argument("val", nargs="?", default=None, help="Nuevo valor")

    # gui
    subparsers.add_parser("gui", help="Abre el menú de configuración gráfico (GTK4)")

    args = parser.parse_args()
    if not args.command:
        # If no arguments provided, launch the menu
        from src.menu import run_menu
        sys.exit(run_menu())

    dispatch = {
        "daemon": cmd_daemon,
        "tray": cmd_tray,
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "save": cmd_save,
        "status": cmd_status,
        "menu": cmd_menu,
        "config": cmd_config,
        "gui": cmd_gui,
    }

    ret = dispatch[args.command](args)
    sys.exit(ret)


if __name__ == "__main__":
    main()
