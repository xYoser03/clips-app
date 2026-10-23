"""
Daemon module for clipctl.
Manages gpu-screen-recorder lifecycle, circular replay buffer, IPC, and instant clip saving.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from src.config import CONFIG_FILE, estimate_ram_mb, load_config

RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
CLIPCTL_SOCK = RUNTIME_DIR / "clipctl.sock"
GSR_SOCK = RUNTIME_DIR / "clipctl-gsr.sock"


class ClipDaemon:
    def __init__(self) -> None:
        self.config = load_config()
        self.gsr_process: Optional[asyncio.subprocess.Process] = None
        self.server: Optional[asyncio.Server] = None
        self.running = False
        self.start_time: float = 0.0

    def build_gsr_command(self) -> list[str]:
        cfg = self.config
        video = cfg.get("video", {})
        replay = cfg.get("replay", {})
        audio = cfg.get("audio", {})
        output = cfg.get("output", {})

        out_dir = Path(output.get("directory", Path.home() / "Videos" / "Clips")).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)

        # Remove old GSR socket if lingering
        if GSR_SOCK.exists():
            try:
                GSR_SOCK.unlink()
            except OSError:
                pass

        cmd = [
            "gpu-screen-recorder",
            "-w", str(video.get("monitor", "DP-2")),
            "-c", str(video.get("container", "mp4")),
            "-f", str(video.get("fps", 60)),
            "-r", str(replay.get("buffer_seconds", 120)),
            "-replay-storage", str(replay.get("storage", "ram")),
            "-restart-replay-on-save", "yes" if replay.get("restart_on_save", False) else "no",
            "-k", str(video.get("codec", "h264")),
            "-bm", str(video.get("bitrate_mode", "cbr")),
            "-q", str(video.get("bitrate", 30000)),
            "-tune", str(video.get("tune", "performance")),
            "-encoder", "gpu",
            "-o", str(out_dir),
            "-ipc", str(GSR_SOCK),
        ]

        # Audio inputs (separate tracks)
        if audio.get("record_desktop", True):
            desktop_dev = audio.get("desktop_device", "default_output")
            cmd.extend(["-a", desktop_dev])

        if audio.get("record_mic", False):
            mic_dev = audio.get("mic_device", "default_input")
            cmd.extend(["-a", mic_dev])

        audio_codec = audio.get("codec", "opus")
        cmd.extend(["-ac", audio_codec])

        return cmd

    async def start_gsr(self) -> bool:
        if self.gsr_process and self.gsr_process.returncode is None:
            return True

        cmd = self.build_gsr_command()
        print(f"[clipctl-daemon] Starting GSR: {' '.join(cmd)}")
        try:
            self.gsr_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self.start_time = time.time()

            # Wait for GSR socket to appear (up to 3 seconds)
            for _ in range(30):
                if GSR_SOCK.exists():
                    break
                await asyncio.sleep(0.1)

            if not GSR_SOCK.exists():
                print("[clipctl-daemon] Warning: GSR socket did not appear promptly.")
            return True
        except Exception as e:
            print(f"[clipctl-daemon] Error launching gpu-screen-recorder: {e}", file=sys.stderr)
            return False

    async def stop_gsr(self) -> None:
        if not self.gsr_process:
            return

        print("[clipctl-daemon] Stopping GSR...")
        # Send stop command via gsr-cli if socket exists
        if GSR_SOCK.exists():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "gsr-cli", "-ipc", str(GSR_SOCK), "stop",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except Exception:
                pass

        if self.gsr_process.returncode is None:
            self.gsr_process.terminate()
            try:
                await asyncio.wait_for(self.gsr_process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self.gsr_process.kill()
        self.gsr_process = None

    async def send_gsr_command(self, cmd_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send JSON command to gpu-screen-recorder IPC socket."""
        if not GSR_SOCK.exists():
            return {"result": "error", "message": "GSR socket not active"}

        try:
            reader, writer = await asyncio.open_unix_connection(str(GSR_SOCK))
            payload = {"id": 1, "name": cmd_name}
            if args:
                payload["data"] = args
            data_bytes = (json.dumps(payload) + "\n").encode("utf-8")
            writer.write(data_bytes)
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            writer.close()
            await writer.wait_closed()
            return json.loads(line.decode("utf-8"))
        except Exception as e:
            return {"result": "error", "message": str(e)}

    def notify_save(self, filepath: str) -> None:
        """Trigger desktop notification and sound."""
        notif_cfg = self.config.get("notifications", {})
        if not notif_cfg.get("enabled", True):
            return

        filename = Path(filepath).name
        try:
            subprocess.Popen([
                "notify-send",
                "-a", "clipctl",
                "-i", "video-x-generic",
                "Instant Replay Guardado",
                f"{filename}\n{filepath}",
                "-u", "normal"
            ])
        except Exception as e:
            print(f"[clipctl-daemon] Notification error: {e}", file=sys.stderr)

        if notif_cfg.get("sound", True):
            sound_path = notif_cfg.get("sound_file", "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga")
            if Path(sound_path).exists():
                player = "pw-play" if shutil.which("pw-play") else "paplay"
                if shutil.which(player):
                    try:
                        subprocess.Popen([player, sound_path], stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                    except Exception:
                        pass

    async def save_replay(self, seconds: Optional[int] = None) -> Dict[str, Any]:
        """Save replay buffer, optionally rename to Clip_... format and notify."""
        if not self.gsr_process or self.gsr_process.returncode is not None:
            return {"status": "error", "message": "Recorder is not running"}

        save_args = {}
        if seconds and seconds > 0:
            save_args["seconds"] = seconds

        res = await self.send_gsr_command("save-replay", save_args if save_args else None)
        if res.get("result") != "ok":
            return {"status": "error", "message": res.get("data", "Save failed")}

        saved_path = res.get("data")
        if not saved_path or not Path(saved_path).exists():
            return {"status": "error", "message": "Saved file not found"}

        # Rename to custom prefix if configured (e.g. Replay_... -> Clip_...)
        final_path = saved_path
        prefix = self.config.get("output", {}).get("prefix", "Clip_")
        orig_file = Path(saved_path)
        if orig_file.name.startswith("Replay_") and prefix != "Replay_":
            new_name = orig_file.name.replace("Replay_", prefix, 1)
            new_path = orig_file.parent / new_name
            try:
                orig_file.rename(new_path)
                final_path = str(new_path)
            except Exception as e:
                print(f"[clipctl-daemon] Failed to rename: {e}")

        # Trigger notification and sound asynchronously
        self.notify_save(final_path)

        file_size_mb = Path(final_path).stat().st_size / (1024 * 1024)
        return {
            "status": "ok",
            "file": final_path,
            "size_mb": round(file_size_mb, 2),
            "seconds_saved": seconds or self.config.get("replay", {}).get("buffer_seconds", 120),
        }

    def get_status(self) -> Dict[str, Any]:
        is_active = bool(self.gsr_process and self.gsr_process.returncode is None and GSR_SOCK.exists())
        replay = self.config.get("replay", {})
        video = self.config.get("video", {})
        buf_sec = replay.get("buffer_seconds", 120)
        bitrate = video.get("bitrate", 30000)

        return {
            "status": "recording" if is_active else "stopped",
            "pid": self.gsr_process.pid if (self.gsr_process and self.gsr_process.returncode is None) else None,
            "uptime_seconds": round(time.time() - self.start_time, 1) if is_active else 0,
            "monitor": video.get("monitor", "DP-2"),
            "resolution": video.get("resolution", "1920x1080"),
            "fps": video.get("fps", 60),
            "codec": video.get("codec", "h264"),
            "bitrate_kbps": bitrate,
            "buffer_seconds": buf_sec,
            "storage": replay.get("storage", "ram"),
            "estimated_ram_mb": round(estimate_ram_mb(buf_sec, bitrate), 1),
            "output_dir": self.config.get("output", {}).get("directory"),
        }

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not line:
                writer.close()
                return

            req = json.loads(line.decode("utf-8"))
            action = req.get("action")

            if action == "status":
                resp = self.get_status()
            elif action == "save":
                sec = req.get("seconds")
                resp = await self.save_replay(sec)
            elif action == "restart":
                self.config = load_config()
                await self.stop_gsr()
                ok = await self.start_gsr()
                resp = {"status": "ok" if ok else "error", "message": "Recorder restarted"}
            elif action == "stop":
                await self.stop_gsr()
                resp = {"status": "ok", "message": "Recorder stopped"}
            elif action == "start":
                if not (self.gsr_process and self.gsr_process.returncode is None):
                    self.config = load_config()
                    ok = await self.start_gsr()
                    resp = {"status": "ok" if ok else "error", "message": "Recorder started"}
                else:
                    resp = {"status": "ok", "message": "Already recording"}
            else:
                resp = {"status": "error", "message": f"Unknown action '{action}'"}

            data = (json.dumps(resp) + "\n").encode("utf-8")
            writer.write(data)
            await writer.drain()
        except Exception as e:
            err = (json.dumps({"status": "error", "message": str(e)}) + "\n").encode("utf-8")
            writer.write(err)
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def run(self) -> None:
        self.running = True

        # Clean old socket
        if CLIPCTL_SOCK.exists():
            CLIPCTL_SOCK.unlink()

        self.server = await asyncio.start_unix_server(self.handle_client, path=str(CLIPCTL_SOCK))
        # Set proper permissions for user-only socket
        os.chmod(str(CLIPCTL_SOCK), 0o600)
        print(f"[clipctl-daemon] IPC listening on {CLIPCTL_SOCK}")

        # Setup signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        # SIGUSR1 saves replay instantly with default duration
        loop.add_signal_handler(sig=signal.SIGUSR1, callback=lambda: asyncio.create_task(self.save_replay()))

        # Start recorder
        await self.start_gsr()

        async with self.server:
            try:
                await self.server.serve_forever()
            except asyncio.CancelledError:
                pass

    async def shutdown(self) -> None:
        print("[clipctl-daemon] Shutting down...")
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        await self.stop_gsr()
        if CLIPCTL_SOCK.exists():
            try:
                CLIPCTL_SOCK.unlink()
            except OSError:
                pass
        loop = asyncio.get_running_loop()
        loop.stop()


def main() -> None:
    daemon = ClipDaemon()
    try:
        asyncio.run(daemon.run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
