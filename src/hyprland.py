"""
Hyprland integration module for clipctl.
Configures global hotkey (bindp / locked) and window rules idempotently.
Supports both Hyprland Lua (Caelestia) and classic hyprland.conf syntax.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Tuple

HYPR_DIR = Path.home() / ".config" / "hypr"
CAELESTIA_USER_LUA = Path.home() / ".config" / "caelestia" / "hypr-user.lua"
CLIPCTL_LUA = HYPR_DIR / "clipctl.lua"
CLIPCTL_CONF = HYPR_DIR / "clipctl.conf"


def format_lua_keybind(keybind: str) -> str:
    """Format keybind string for Hyprland Lua, e.g., 'SUPER + F10'."""
    parts = [p.strip().upper() for p in re.split(r"[,+\s]+", keybind) if p.strip()]
    return " + ".join(parts)


def format_conf_keybind(keybind: str) -> Tuple[str, str]:
    """Format keybind for hyprland.conf (mods, key), e.g. ('SUPER', 'F10')."""
    parts = [p.strip().upper() for p in re.split(r"[,+\s]+", keybind) if p.strip()]
    if len(parts) == 1:
        return ("", parts[0])
    mods = " ".join(parts[:-1])
    key = parts[-1]
    return (mods, key)


def update_hyprland_bind(keybind_str: str) -> bool:
    """
    Idempotently configures Hyprland hotkey and window rules.
    Writes clipctl.lua and clipctl.conf, updates hypr-user.lua if present,
    and executes hyprctl reload.
    """
    HYPR_DIR.mkdir(parents=True, exist_ok=True)
    lua_bind = format_lua_keybind(keybind_str)
    mods, key = format_conf_keybind(keybind_str)

    # 1. Write ~/.config/hypr/clipctl.lua
    lua_content = f"""-- clipctl Hyprland Lua Integration
-- Generated automatically by clipctl. Do not edit manually.

-- Keybind to save instant replay (locked = true ensures it triggers in fullscreen games)
hl.bind("{lua_bind}", hl.dsp.exec_cmd("clipctl save"), {{ locked = true }})

-- Keybind to open quick application menu
hl.bind("SUPER + ALT + F10", hl.dsp.exec_cmd("clipctl menu"), {{ locked = true }})

-- Window rules for clipctl GUI
hl.window_rule({{ match = {{ class = "com.clipctl.gui" }}, float = true, center = true }})

-- Background tray indicator autostart
hl.exec_cmd("pgrep -f 'clipctl tray' >/dev/null || clipctl tray")
"""
    with open(CLIPCTL_LUA, "w", encoding="utf-8") as f:
        f.write(lua_content)

    # 2. Write ~/.config/hypr/clipctl.conf
    conf_content = f"""# clipctl Hyprland Configuration
# Generated automatically by clipctl. Do not edit manually.

# bindp bypasses application shortcut inhibitors (Proton / Steam games)
bindp = {mods}, {key}, exec, clipctl save
bindp = SUPER ALT, F10, exec, clipctl menu

# Window rules for clipctl GUI
windowrulev2 = float, class:^(com.clipctl.gui)$
windowrulev2 = center, class:^(com.clipctl.gui)$

# Background tray indicator autostart
exec-once = pgrep -f 'clipctl tray' >/dev/null || clipctl tray
"""
    with open(CLIPCTL_CONF, "w", encoding="utf-8") as f:
        f.write(conf_content)

    # 3. Idempotently link/include in hypr-user.lua if Caelestia/Lua is active
    if CAELESTIA_USER_LUA.exists():
        try:
            with open(CAELESTIA_USER_LUA, "r", encoding="utf-8") as f:
                user_lua = f.read()

            include_line = 'pcall(dofile, os.getenv("HOME") .. "/.config/hypr/clipctl.lua")'
            if include_line not in user_lua:
                with open(CAELESTIA_USER_LUA, "a", encoding="utf-8") as f:
                    f.write(f"\n-- clipctl instant replay configuration\n{include_line}\n")
        except Exception as e:
            print(f"[clipctl] Warning: could not update {CAELESTIA_USER_LUA}: {e}", file=sys.stderr)

    # 4. Also check if hyprland.conf exists; if so, idempotently add source
    user_conf = HYPR_DIR / "hyprland.conf"
    if user_conf.exists():
        try:
            with open(user_conf, "r", encoding="utf-8") as f:
                conf_text = f.read()
            source_line = "source = ~/.config/hypr/clipctl.conf"
            if source_line not in conf_text:
                with open(user_conf, "a", encoding="utf-8") as f:
                    f.write(f"\n# clipctl instant replay bind\n{source_line}\n")
        except Exception as e:
            print(f"[clipctl] Warning: could not update {user_conf}: {e}", file=sys.stderr)

    # 5. Reload Hyprland
    try:
        res = subprocess.run(["hyprctl", "reload"], capture_output=True, text=True, timeout=3.0)
        return res.returncode == 0
    except Exception as e:
        print(f"[clipctl] Error reloading Hyprland: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    bind = sys.argv[1] if len(sys.argv) > 1 else "SUPER + F10"
    ok = update_hyprland_bind(bind)
    print(f"Hyprland keybind updated to '{bind}': {'Success' if ok else 'Failed'}")
