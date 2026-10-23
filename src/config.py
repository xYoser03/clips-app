"""
Configuration module for clipctl.
Handles loading, saving, validating, and calculating memory requirements for instant replays.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "clipctl"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG: Dict[str, Any] = {
    "video": {
        "monitor": "DP-2",             # DP-2, HDMI-A-1, screen, or portal
        "resolution": "1920x1080",
        "fps": 60,                     # 30, 60, 120, 144, 180
        "codec": "h264",               # h264, hevc, av1
        "bitrate": 30000,              # in kbps (30 Mbps for high quality 1080p60)
        "bitrate_mode": "cbr",         # cbr (constant RAM), vbr, qp
        "container": "mp4",            # mp4, mkv
        "tune": "performance",         # performance, quality
    },
    "replay": {
        "buffer_seconds": 120,         # 2 minutes default buffer
        "default_save_seconds": 120,   # Save last N seconds
        "storage": "ram",              # ram or disk
        "restart_on_save": False,      # Clear buffer after saving
    },
    "audio": {
        "record_desktop": True,
        "desktop_device": "default_output",
        "record_mic": False,
        "mic_device": "default_input",
        "codec": "opus",               # opus, aac, flac
    },
    "output": {
        "directory": str(Path.home() / "Videos" / "Clips"),
        "prefix": "Clip_",
    },
    "notifications": {
        "enabled": True,
        "sound": True,
        "sound_file": "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga",
    },
    "hyprland": {
        "keybind": "SUPER + F10",
    },
}


def estimate_ram_mb(buffer_seconds: int, bitrate_kbps: int) -> float:
    """
    Estimate RAM consumption of circular replay buffer in megabytes.
    Formula: (seconds * (bitrate in bps + audio overhead)) / (8 * 1024 * 1024)
    """
    # Audio ~ 160 kbps per track, video = bitrate_kbps
    total_kbps = bitrate_kbps + 320
    total_bytes = (total_kbps * 1000 / 8.0) * buffer_seconds
    # Add ~10% container / packet overhead
    return (total_bytes * 1.10) / (1024 * 1024)


def load_config() -> Dict[str, Any]:
    """Load configuration from disk, creating default if missing."""
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
        
        # Merge with defaults to ensure all keys exist
        merged = DEFAULT_CONFIG.copy()
        for section, values in data.items():
            if section in merged and isinstance(values, dict):
                merged[section].update(values)
            else:
                merged[section] = values
        return merged
    except Exception as e:
        print(f"[clipctl] Warning: Failed to load {CONFIG_FILE} ({e}). Using defaults.")
        return DEFAULT_CONFIG.copy()


def save_config(cfg: Dict[str, Any]) -> None:
    """Save configuration dictionary to TOML format."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# clipctl configuration",
        "# Generated automatically. Edit with care or use 'clipctl gui'",
        "",
    ]
    for section, values in cfg.items():
        lines.append(f"[{section}]")
        for k, v in values.items():
            if isinstance(v, bool):
                val_str = "true" if v else "false"
            elif isinstance(v, (int, float)):
                val_str = str(v)
            else:
                val_str = f'"{v}"'
            lines.append(f"{k} = {val_str}")
        lines.append("")

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
