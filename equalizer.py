"""
equalizer.py
============
Real-time 10-band parametric equalizer for stereo audio blocks.

The equalizer is designed for block-based processing and maintains per-band,
per-channel filter state so successive calls remain seamless. SciPy is used
only for stable biquad coefficient design and SOS filtering; if SciPy is not
available, the equalizer degrades gracefully and passes audio through
unchanged.
"""

import logging
import threading
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

SCIPY_AVAILABLE = False
try:
    from scipy.signal import iirpeak, sosfilt, sosfilt_zi, tf2sos

    SCIPY_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.warning("scipy import failed (%s). Equalizer disabled.", exc)


class Equalizer:
    """Block-based 10-band parametric equalizer with persistent filter state."""

    BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
    PRESETS = {
        "Flat": [0.0] * 10,
        "Bass Boost": [6.0, 5.0, 4.0, 3.0, 1.5, 0.0, -1.0, -2.0, -3.0, -4.0],
        "Treble Boost": [-4.0, -3.0, -2.0, -1.0, 0.0, 1.5, 3.0, 4.0, 5.0, 6.0],
        "Vocal": [-3.0, -2.0, -1.0, 1.0, 2.5, 4.0, 4.0, 2.0, -1.0, -2.0],
        "Rock": [4.0, 3.0, 2.0, 1.0, -1.0, -1.5, 1.0, 2.5, 3.5, 4.5],
        "Electronic": [5.0, 4.0, 3.0, 1.0, -1.0, 0.0, 1.5, 3.0, 4.0, 5.0],
    }

    MIN_GAIN_DB = -12.0
    MAX_GAIN_DB = 12.0
    DEFAULT_Q = np.sqrt(2.0)

    def __init__(self, sample_rate: int = 48000, channels: int = 2) -> None:
        self._sample_rate = int(sample_rate)
        self._channels = int(channels)
        self._enabled = True
        self._lock = threading.RLock()
        self._gains: List[float] = [0.0] * len(self.BANDS)
        self._sos_filters: List[np.ndarray] = []
        self._states: List[np.ndarray] = []

        if self._sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self._channels <= 0:
            raise ValueError("channels must be positive")

        self._rebuild_filters(reset_state=True)

    def set_gain(self, band_index: int, gain_db: float) -> None:
        """Update a single band gain in dB."""
        with self._lock:
            self._validate_band_index(band_index)
            self._gains[band_index] = self._clamp_gain(gain_db)
            if SCIPY_AVAILABLE:
                self._sos_filters[band_index] = self._design_band(
                    self.BANDS[band_index],
                    self._gains[band_index],
                )
                self._states[band_index] = self._make_initial_state(
                    self._sos_filters[band_index]
                )

    def set_gains(self, gains: List[float]) -> None:
        """Update all 10 band gains at once."""
        if len(gains) != len(self.BANDS):
            raise ValueError(f"expected {len(self.BANDS)} gains")

        with self._lock:
            self._gains = [self._clamp_gain(gain) for gain in gains]
            self._rebuild_filters(reset_state=True)

    def get_gains(self) -> List[float]:
        """Return a copy of the current band gains in dB."""
        with self._lock:
            return list(self._gains)

    def process(self, block: np.ndarray) -> np.ndarray:
        """Process a single audio block and return the equalized output."""
        if not isinstance(block, np.ndarray):
            raise TypeError("block must be a numpy.ndarray")
        if block.ndim != 2:
            raise ValueError("block must be a 2D array of shape (frames, channels)")
        if block.shape[1] != self._channels:
            raise ValueError(
                f"block channel count {block.shape[1]} does not match {self._channels}"
            )

        passthrough = np.asarray(block, dtype=np.float32)
        if passthrough.size == 0 or not self.enabled or not SCIPY_AVAILABLE:
            return passthrough.copy()

        with self._lock:
            processed = passthrough.astype(np.float64, copy=True)
            for band_index, sos in enumerate(self._sos_filters):
                band_output = np.empty_like(processed)
                band_state = self._states[band_index]
                for channel in range(self._channels):
                    band_output[:, channel], band_state[channel] = sosfilt(
                        sos,
                        processed[:, channel],
                        zi=band_state[channel],
                    )
                processed = band_output

        return np.clip(processed, -1.0, 1.0).astype(np.float32, copy=False)

    def reset(self) -> None:
        """Reset all filter states without changing the configured gains."""
        with self._lock:
            self._states = [self._make_initial_state(sos) for sos in self._sos_filters]

    def set_enabled(self, enabled: bool) -> None:
        """Enable or bypass the equalizer."""
        with self._lock:
            self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        """Return whether the equalizer is currently active."""
        with self._lock:
            return self._enabled

    def _rebuild_filters(self, reset_state: bool) -> None:
        self._sos_filters = []
        self._states = []

        if not SCIPY_AVAILABLE:
            return

        for center_frequency, gain_db in zip(self.BANDS, self._gains):
            sos = self._design_band(center_frequency, gain_db)
            self._sos_filters.append(sos)
            if reset_state:
                self._states.append(self._make_initial_state(sos))

    def _design_band(self, center_frequency: int, gain_db: float) -> np.ndarray:
        """Create an SOS peaking filter for one EQ band."""
        nyquist = self._sample_rate * 0.5
        if center_frequency >= nyquist:
            logger.debug(
                "Skipping EQ band %s Hz at sample rate %s Hz; above Nyquist.",
                center_frequency,
                self._sample_rate,
            )
            return np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64)

        normalized_frequency = center_frequency / nyquist
        b_peak, a_peak = iirpeak(normalized_frequency, self.DEFAULT_Q)

        linear_gain = float(10.0 ** (gain_db / 20.0))
        mix_gain = linear_gain - 1.0
        b_eq = a_peak + (mix_gain * b_peak)

        return tf2sos(b_eq, a_peak).astype(np.float64, copy=False)

    def _make_initial_state(self, sos: np.ndarray) -> np.ndarray:
        """Return per-channel SOS filter state."""
        base_state = sosfilt_zi(sos) * 0.0
        return np.repeat(base_state[np.newaxis, :, :], self._channels, axis=0)

    def _validate_band_index(self, band_index: int) -> None:
        if band_index < 0 or band_index >= len(self.BANDS):
            raise IndexError("band_index out of range")

    def _clamp_gain(self, gain_db: float) -> float:
        return float(np.clip(gain_db, self.MIN_GAIN_DB, self.MAX_GAIN_DB))
