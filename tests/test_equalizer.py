"""
tests/test_equalizer.py
=======================
Unit tests for the Equalizer class.
"""

import threading
import unittest

import numpy as np

from equalizer import Equalizer, SCIPY_AVAILABLE


class TestEqualizerBasics(unittest.TestCase):
    """Test Equalizer configuration and bypass behavior."""

    def test_default_gains(self):
        eq = Equalizer()
        self.assertEqual(eq.get_gains(), [0.0] * 10)
        self.assertTrue(eq.enabled)

    def test_gain_clamp(self):
        eq = Equalizer()
        eq.set_gain(0, 99.0)
        eq.set_gain(1, -99.0)
        gains = eq.get_gains()
        self.assertAlmostEqual(gains[0], 12.0)
        self.assertAlmostEqual(gains[1], -12.0)

    def test_set_gains_requires_ten_values(self):
        eq = Equalizer()
        with self.assertRaises(ValueError):
            eq.set_gains([0.0] * 9)

    def test_process_passthrough_when_disabled(self):
        eq = Equalizer()
        eq.set_enabled(False)
        block = np.random.uniform(-0.25, 0.25, (128, 2)).astype("float32")
        out = eq.process(block)
        np.testing.assert_array_equal(out, block)

    def test_presets_have_ten_values(self):
        for gains in Equalizer.PRESETS.values():
            self.assertEqual(len(gains), 10)

    def test_thread_safe_gain_updates(self):
        eq = Equalizer()

        def worker(index: int, gain: float) -> None:
            eq.set_gain(index, gain)

        threads = [
            threading.Thread(target=worker, args=(i, float(i - 5)))
            for i in range(10)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(eq.get_gains(), [float(i - 5) for i in range(10)])


@unittest.skipUnless(SCIPY_AVAILABLE, "SciPy not installed")
class TestEqualizerDSP(unittest.TestCase):
    """Test DSP behavior when SciPy is available."""

    def test_process_keeps_shape_and_dtype(self):
        eq = Equalizer()
        eq.set_gain(4, 6.0)
        block = np.random.uniform(-0.1, 0.1, (256, 2)).astype("float32")
        out = eq.process(block)
        self.assertEqual(out.shape, block.shape)
        self.assertEqual(out.dtype, np.float32)

    def test_gain_changes_signal(self):
        eq = Equalizer(sample_rate=48000)
        eq.set_gain(Equalizer.BANDS.index(1000), 6.0)
        time_axis = np.arange(0, 512, dtype=np.float32) / 48000.0
        tone = np.sin(2.0 * np.pi * 1000.0 * time_axis).astype("float32")
        block = np.column_stack((tone, tone)).astype("float32")
        out = eq.process(block)
        self.assertFalse(np.allclose(out, block))

    def test_state_is_preserved_across_blocks(self):
        eq = Equalizer(sample_rate=48000)
        eq.set_gain(Equalizer.BANDS.index(500), 6.0)
        impulse = np.zeros((64, 2), dtype="float32")
        impulse[0, :] = 1.0
        first = eq.process(impulse)
        second = eq.process(np.zeros_like(impulse))
        self.assertGreater(float(np.max(np.abs(first))), 0.0)
        self.assertGreater(float(np.max(np.abs(second))), 0.0)


if __name__ == "__main__":
    unittest.main()
