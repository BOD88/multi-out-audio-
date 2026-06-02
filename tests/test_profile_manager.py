"""
tests/test_profile_manager.py
==============================
Unit tests for ProfileManager and AudioProfile.
"""

import unittest
from unittest.mock import patch, MagicMock


class TestAudioProfile(unittest.TestCase):
    """Test AudioProfile data class."""

    def test_to_dict_roundtrip(self):
        from profile_manager import AudioProfile

        p = AudioProfile(
            name="Test",
            enabled_devices=["A", "B"],
            device_volumes={"A": 0.5},
            device_delays={"B": 100.0},
            master_volume=0.8,
            master_muted=True,
            source_device="Source",
        )
        d = p.to_dict()
        p2 = AudioProfile.from_dict(d)
        self.assertEqual(p2.name, "Test")
        self.assertEqual(p2.enabled_devices, ["A", "B"])
        self.assertAlmostEqual(p2.device_volumes["A"], 0.5)
        self.assertAlmostEqual(p2.device_delays["B"], 100.0)
        self.assertAlmostEqual(p2.master_volume, 0.8)
        self.assertTrue(p2.master_muted)
        self.assertEqual(p2.source_device, "Source")

    def test_from_dict_defaults(self):
        from profile_manager import AudioProfile

        p = AudioProfile.from_dict({})
        self.assertEqual(p.name, "Unnamed")
        self.assertEqual(p.enabled_devices, [])
        self.assertAlmostEqual(p.master_volume, 1.0)
        self.assertFalse(p.master_muted)


class TestProfileManager(unittest.TestCase):
    """Test ProfileManager CRUD operations."""

    @patch("settings_manager.QSettings")
    def setUp(self, mock_qsettings_cls):
        self._store = {}
        mock_instance = MagicMock()
        mock_instance.value.side_effect = lambda k, d=None, type=None: self._store.get(k, d)
        mock_instance.setValue.side_effect = lambda k, v: self._store.update({k: v})
        mock_qsettings_cls.return_value = mock_instance

        from settings_manager import SettingsManager
        from profile_manager import ProfileManager

        self.settings = SettingsManager()
        self.mgr = ProfileManager(self.settings)

    def test_empty_by_default(self):
        self.assertEqual(self.mgr.list_profiles(), [])

    def test_save_and_list(self):
        from profile_manager import AudioProfile

        p = AudioProfile(name="Work", enabled_devices=["Headphones"])
        self.mgr.save_profile(p)
        self.assertIn("Work", self.mgr.list_profiles())

    def test_get_profile(self):
        from profile_manager import AudioProfile

        p = AudioProfile(name="Party", master_volume=0.9)
        self.mgr.save_profile(p)
        loaded = self.mgr.get_profile("Party")
        self.assertIsNotNone(loaded)
        self.assertAlmostEqual(loaded.master_volume, 0.9)

    def test_get_nonexistent(self):
        self.assertIsNone(self.mgr.get_profile("NoSuchProfile"))

    def test_delete_profile(self):
        from profile_manager import AudioProfile

        self.mgr.save_profile(AudioProfile(name="ToDelete"))
        self.assertTrue(self.mgr.delete_profile("ToDelete"))
        self.assertNotIn("ToDelete", self.mgr.list_profiles())

    def test_delete_nonexistent(self):
        self.assertFalse(self.mgr.delete_profile("NoSuchProfile"))

    def test_rename_profile(self):
        from profile_manager import AudioProfile

        self.mgr.save_profile(AudioProfile(name="OldName"))
        self.assertTrue(self.mgr.rename_profile("OldName", "NewName"))
        self.assertNotIn("OldName", self.mgr.list_profiles())
        self.assertIn("NewName", self.mgr.list_profiles())

    def test_rename_conflict(self):
        from profile_manager import AudioProfile

        self.mgr.save_profile(AudioProfile(name="A"))
        self.mgr.save_profile(AudioProfile(name="B"))
        self.assertFalse(self.mgr.rename_profile("A", "B"))

    def test_overwrite_profile(self):
        from profile_manager import AudioProfile

        self.mgr.save_profile(AudioProfile(name="X", master_volume=0.5))
        self.mgr.save_profile(AudioProfile(name="X", master_volume=0.9))
        loaded = self.mgr.get_profile("X")
        self.assertAlmostEqual(loaded.master_volume, 0.9)


if __name__ == "__main__":
    unittest.main()
