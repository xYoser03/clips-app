import unittest
from pathlib import Path
import sys

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import estimate_ram_mb, DEFAULT_CONFIG
from src.hyprland import format_lua_keybind, format_conf_keybind


class TestClipctlConfig(unittest.TestCase):
    def test_estimate_ram(self):
        # 120s buffer at 30,000 kbps:
        # (120 * (30000 + 320) * 1000 / 8) * 1.10 / (1024 * 1024) ~ 477 MB
        ram = estimate_ram_mb(120, 30000)
        self.assertGreater(ram, 400)
        self.assertLess(ram, 600)

    def test_estimate_ram_high_buffer(self):
        # 1200s (20 min) at 50,000 kbps should exceed 2 GB
        ram = estimate_ram_mb(1200, 50000)
        self.assertGreater(ram, 2000)

    def test_keybind_formatting(self):
        lua_bind = format_lua_keybind("SUPER + F10")
        self.assertEqual(lua_bind, "SUPER + F10")

        mods, key = format_conf_keybind("SUPER, F10")
        self.assertEqual(mods, "SUPER")
        self.assertEqual(key, "F10")

        mods2, key2 = format_conf_keybind("CTRL + ALT + S")
        self.assertEqual(mods2, "CTRL ALT")
        self.assertEqual(key2, "S")


if __name__ == "__main__":
    unittest.main()
