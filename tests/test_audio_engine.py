"""
tests/test_audio_engine.py
==========================
Unit tests for the AudioRouter class.
"""

import sys
import unittest
from unittest.mock import MagicMock
import numpy as np

# Mock sounddevice before importing audio_engine
mock_sd = MagicMock()
sys.modules["sounddevice"] = mock_sd


class TestAudioRouterInit(unittest.TestCase):
    """Test AudioRouter initialisation and state defaults."""

    def test_default_state(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        self.assertFalse(router.is_routing)
        self.assertEqual(router.active_output_count, 0)
        self.assertEqual(router.active_device_ids, [])
        self.assertEqual(router.get_master_volume(), 1.0)
        self.assertFalse(router.is_master_muted())
        self.assertEqual(router.get_latency_ms(), 0.0)
        self.assertEqual(router.get_buffer_underruns(), 0)


class TestAudioRouterVolume(unittest.TestCase):
    """Test volume and mute controls."""

    def test_master_volume_clamp(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        router.set_master_volume(0.5)
        self.assertAlmostEqual(router.get_master_volume(), 0.5)

        router.set_master_volume(-0.1)
        self.assertAlmostEqual(router.get_master_volume(), 0.0)

        router.set_master_volume(1.5)
        self.assertAlmostEqual(router.get_master_volume(), 1.0)

    def test_master_mute(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        self.assertFalse(router.is_master_muted())
        router.set_master_mute(True)
        self.assertTrue(router.is_master_muted())
        router.set_master_mute(False)
        self.assertFalse(router.is_master_muted())

    def test_device_volume_clamp(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        router.set_device_volume(0, 0.7)
        self.assertAlmostEqual(router.get_device_volume(0), 0.7)

        router.set_device_volume(0, -1.0)
        self.assertAlmostEqual(router.get_device_volume(0), 0.0)

        router.set_device_volume(0, 2.0)
        self.assertAlmostEqual(router.get_device_volume(0), 1.0)

    def test_device_volume_default(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        self.assertAlmostEqual(router.get_device_volume(999), 1.0)

    def test_device_mute(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        self.assertFalse(router.is_device_muted(0))
        router.set_device_mute(0, True)
        self.assertTrue(router.is_device_muted(0))


class TestAudioRouterDelay(unittest.TestCase):
    """Test per-device delay compensation."""

    def test_delay_clamp(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        router.set_device_delay(0, 100.0)
        self.assertAlmostEqual(router.get_device_delay(0), 100.0)

        router.set_device_delay(0, -10.0)
        self.assertAlmostEqual(router.get_device_delay(0), 0.0)

        router.set_device_delay(0, 9999.0)
        self.assertAlmostEqual(router.get_device_delay(0), router.MAX_DELAY_MS)

    def test_delay_default(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        self.assertAlmostEqual(router.get_device_delay(999), 0.0)


class TestAudioRouterMetering(unittest.TestCase):
    """Test metering accessors."""

    def test_master_peak_default(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        peaks = router.get_master_peak()
        self.assertEqual(peaks, [0.0, 0.0])

    def test_device_peak_default(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        peaks = router.get_device_peak(999)
        self.assertEqual(peaks, [0.0, 0.0])


class TestAudioRouterDeviceDiscovery(unittest.TestCase):
    """Test device enumeration."""

    def test_get_output_devices(self):
        from audio_engine import AudioRouter

        mock_sd.query_devices.return_value = [
            {
                "name": "Speakers",
                "max_output_channels": 2,
                "max_input_channels": 0,
                "hostapi": 0,
                "default_samplerate": 48000,
            },
            {
                "name": "Microphone",
                "max_output_channels": 0,
                "max_input_channels": 2,
                "hostapi": 0,
                "default_samplerate": 44100,
            },
        ]
        mock_sd.query_hostapis.return_value = [{"name": "WASAPI"}]

        router = AudioRouter()
        devices = router.get_output_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["name"], "Speakers")
        self.assertEqual(devices[0]["channels"], 2)
        self.assertEqual(devices[0]["hostapi"], "WASAPI")

    def test_find_stereo_mix(self):
        from audio_engine import AudioRouter

        mock_sd.query_devices.return_value = [
            {"name": "Stereo Mix", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Microphone", "max_input_channels": 1, "max_output_channels": 0},
        ]

        router = AudioRouter()
        idx = router.find_stereo_mix_device()
        self.assertEqual(idx, 0)

    def test_find_stereo_mix_not_found(self):
        from audio_engine import AudioRouter

        mock_sd.query_devices.return_value = [
            {"name": "Microphone", "max_input_channels": 1, "max_output_channels": 0},
        ]

        router = AudioRouter()
        idx = router.find_stereo_mix_device()
        self.assertIsNone(idx)


class TestInputCallback(unittest.TestCase):
    """Test the input callback processes audio correctly."""

    def test_input_callback_stores_buffer(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        indata = np.random.rand(1024, 2).astype("float32")
        status = MagicMock()
        status.input_underflow = False

        router._input_callback(indata, 1024, None, status)

        np.testing.assert_array_almost_equal(
            router._audio_buffer[:1024], indata[:1024], decimal=5
        )

    def test_input_callback_mono_upmix(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        indata = np.random.rand(1024, 1).astype("float32")
        status = MagicMock()
        status.input_underflow = False

        router._input_callback(indata, 1024, None, status)

        self.assertEqual(router._audio_buffer.shape[1], 2)
        np.testing.assert_array_almost_equal(
            router._audio_buffer[:, 0], router._audio_buffer[:, 1]
        )

    def test_input_callback_updates_peaks(self):
        from audio_engine import AudioRouter

        router = AudioRouter()
        indata = np.zeros((1024, 2), dtype="float32")
        indata[0, 0] = 0.8
        indata[0, 1] = 0.6
        status = MagicMock()
        status.input_underflow = False

        router._input_callback(indata, 1024, None, status)

        peaks = router.get_master_peak()
        self.assertGreater(peaks[0], 0.0)
        self.assertGreater(peaks[1], 0.0)


if __name__ == "__main__":
    unittest.main()
