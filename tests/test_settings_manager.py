"""
tests/test_settings_manager.py
==============================
Unit tests for SettingsManager.
"""

import json
import unittest
from unittest.mock import patch, MagicMock


class TestSettingsManager(unittest.TestCase):
    """Test SettingsManager read/write operations."""

    @patch("settings_manager.QSettings")
    def setUp(self, mock_qsettings_cls):
        self._store = {}

        def mock_value(key, default=None, type=None):
            return self._store.get(key, default)

        def mock_set_value(key, value):
            self._store[key] = value

        mock_instance = MagicMock()
        mock_instance.value.side_effect = mock_value
        mock_instance.setValue.side_effect = mock_set_value
        mock_qsettings_cls.return_value = mock_instance

        from settings_manager import SettingsManager
        self.mgr = SettingsManager()

    def test_master_volume_roundtrip(self):
        self.mgr.save_master_volume(0.75)
        self.assertAlmostEqual(self.mgr.get_master_volume(), 0.75)

    def test_master_volume_default(self):
        self.assertAlmostEqual(self.mgr.get_master_volume(), 1.0)

    def test_master_muted_roundtrip(self):
        self.mgr.save_master_muted(True)
        self.assertTrue(self.mgr.get_master_muted())

    def test_enabled_devices_roundtrip(self):
        devices = ["Speakers", "Headphones"]
        self.mgr.save_enabled_devices(devices)
        self.assertEqual(self.mgr.get_enabled_devices(), devices)

    def test_enabled_devices_default(self):
        self.assertEqual(self.mgr.get_enabled_devices(), [])

    def test_device_volumes_roundtrip(self):
        vols = {"Speakers": 0.8, "Headphones": 0.5}
        self.mgr.save_device_volumes(vols)
        result = self.mgr.get_device_volumes()
        self.assertAlmostEqual(result["Speakers"], 0.8)
        self.assertAlmostEqual(result["Headphones"], 0.5)

    def test_device_delays_roundtrip(self):
        delays = {"Bluetooth": 150.0, "USB": 0.0}
        self.mgr.save_device_delays(delays)
        result = self.mgr.get_device_delays()
        self.assertAlmostEqual(result["Bluetooth"], 150.0)

    def test_theme_default(self):
        self.assertEqual(self.mgr.get_theme(), "dark")

    def test_theme_roundtrip(self):
        self.mgr.save_theme("light")
        self.assertEqual(self.mgr.get_theme(), "light")

    def test_auto_start_default(self):
        self.assertFalse(self.mgr.get_auto_start())

    def test_auto_start_roundtrip(self):
        self.mgr.save_auto_start(True)
        self.assertTrue(self.mgr.get_auto_start())

    def test_first_run(self):
        self.assertTrue(self.mgr.is_first_run())
        self.mgr.mark_first_run_done()
        self.assertFalse(self.mgr.is_first_run())

    def test_profiles_roundtrip(self):
        profiles = {
            "Work": {"name": "Work", "enabled_devices": ["Headphones"]},
            "Party": {"name": "Party", "enabled_devices": ["Speakers", "BT"]},
        }
        self.mgr.save_profiles(profiles)
        result = self.mgr.get_profiles()
        self.assertEqual(len(result), 2)
        self.assertIn("Work", result)

    def test_source_device_roundtrip(self):
        self.mgr.save_source_device("Speakers  [WASAPI]")
        self.assertEqual(self.mgr.get_source_device(), "Speakers  [WASAPI]")

    def test_minimize_to_tray_default(self):
        self.assertTrue(self.mgr.get_minimize_to_tray())


class TestSettingsManagerCorruptData(unittest.TestCase):
    """Test graceful handling of corrupt stored data."""

    @patch("settings_manager.QSettings")
    def test_corrupt_json_returns_default(self, mock_qsettings_cls):
        store = {"audio/enabled_device_names": "not valid json{{{"}
        mock_instance = MagicMock()
        mock_instance.value.side_effect = lambda k, d=None, type=None: store.get(k, d)
        mock_instance.setValue.side_effect = lambda k, v: store.update({k: v})
        mock_qsettings_cls.return_value = mock_instance

        from settings_manager import SettingsManager
        mgr = SettingsManager()
        self.assertEqual(mgr.get_enabled_devices(), [])


if __name__ == "__main__":
    unittest.main()
