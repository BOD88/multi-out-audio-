"""
tests/test_hotkey_manager.py
============================
Unit tests for HotkeyManager.
"""

import unittest

from hotkey_manager import DEFAULT_HOTKEYS, HotkeyManager, MOD_ALT, MOD_CTRL, VK_CODES


class TestHotkeyConstants(unittest.TestCase):
    """Validate exported hotkey constants."""

    def test_default_bindings(self):
        self.assertEqual(
            DEFAULT_HOTKEYS["toggle_routing"],
            (MOD_CTRL | MOD_ALT, VK_CODES["R"]),
        )
        self.assertEqual(
            DEFAULT_HOTKEYS["toggle_mute"],
            (MOD_CTRL | MOD_ALT, VK_CODES["M"]),
        )
        self.assertEqual(
            DEFAULT_HOTKEYS["toggle_recording"],
            (MOD_CTRL | MOD_ALT, VK_CODES["P"]),
        )

    def test_common_vk_codes(self):
        self.assertEqual(VK_CODES["F1"], 0x70)
        self.assertEqual(VK_CODES["F12"], 0x7B)
        self.assertEqual(VK_CODES["0"], 0x30)
        self.assertEqual(VK_CODES["9"], 0x39)
        self.assertEqual(VK_CODES["A"], 0x41)
        self.assertEqual(VK_CODES["Z"], 0x5A)
        self.assertEqual(VK_CODES["SPACE"], 0x20)
        self.assertEqual(VK_CODES["RETURN"], 0x0D)
        self.assertEqual(VK_CODES["UP"], 0x26)
        self.assertEqual(VK_CODES["DOWN"], 0x28)


class TestHotkeyManagerFallback(unittest.TestCase):
    """Ensure non-Windows operation degrades gracefully."""

    def test_non_windows_noop_behaviour(self):
        mgr = HotkeyManager()
        self.assertFalse(mgr.available)
        self.assertFalse(mgr.register("test", MOD_CTRL, VK_CODES["A"], lambda: None))
        mgr.unregister("test")
        mgr.unregister_all()
        mgr.shutdown()


if __name__ == "__main__":
    unittest.main()
