"""
audio_engine.py
===============
Core audio routing engine for Multi-Output Audio Console.

Captures PC system audio via WASAPI loopback and simultaneously fans it out
to any number of selected output devices (speakers, Bluetooth, HDMI, USB, etc.)
with per-device and master volume / mute control, per-device delay compensation,
and automatic error recovery.
"""

import collections
import sys
import threading
import logging
import time
import numpy as np
import sounddevice as sd
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AudioRouter:
    """
    Routes system audio to multiple output devices simultaneously.

    Workflow
    --------
    1. Open a WASAPI loopback InputStream pointed at the chosen output device
       (or 'Stereo Mix' on older systems).
    2. In the input callback, copy audio into a shared ring-slot buffer.
    3. For every selected output device, an OutputStream callback reads from
       that shared buffer, applies per-device gain / mute, and writes to
       its device — achieving multi-output playback in sync.
    """

    SAMPLE_RATE: int = 48_000
    CHANNELS: int = 2
    BLOCK_SIZE: int = 1024
    DTYPE: str = "float32"
    PEAK_DECAY: float = 0.80  # Decay factor per refresh cycle (~20 ms)
    MAX_DELAY_MS: float = 500.0  # Maximum per-device delay offset
    MAX_RECONNECT_ATTEMPTS: int = 3
    RECONNECT_INTERVAL_S: float = 2.0

    # ------------------------------------------------------------------ init --

    def __init__(self) -> None:
        # Streams
        self._input_stream: Optional[sd.InputStream] = None
        self._output_streams: Dict[int, sd.OutputStream] = {}

        # Volume / mute state
        self._master_volume: float = 1.0
        self._master_muted: bool = False
        self._device_volumes: Dict[int, float] = {}
        self._device_muted: Dict[int, bool] = {}

        # Per-device delay compensation (ms)
        self._device_delays: Dict[int, float] = {}
        # Delay ring buffer: stores recent blocks for delayed playback
        self._delay_buffer: collections.deque = collections.deque(maxlen=500)

        # Shared audio buffer (written by input CB, read by output CBs)
        self._audio_buffer = np.zeros((self.BLOCK_SIZE, self.CHANNELS), dtype=self.DTYPE)
        self._buffer_lock = threading.RLock()

        # State flags
        self._is_routing: bool = False
        self._source_device_id: Optional[int] = None

        # Metering
        self._master_peak: List[float] = [0.0, 0.0]
        self._device_peaks: Dict[int, List[float]] = {}

        # Error recovery
        self._failed_devices: Dict[int, int] = {}  # device_id → retry count
        self._device_errors: Dict[int, str] = {}   # device_id → last error message

        # Optional callbacks for UI notifications
        self.on_routing_changed: Optional[Callable[[bool], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_device_error: Optional[Callable[[int, str], None]] = None
        self.on_device_recovered: Optional[Callable[[int], None]] = None

        # Latency display
        self._latency_ms: float = 0.0

        # Performance monitoring
        self._cb_durations: collections.deque = collections.deque(maxlen=100)
        self._buffer_underruns: int = 0

    # --------------------------------------------------------------- discovery --

    def get_output_devices(self) -> List[Dict]:
        """Return a list of all audio output devices on the system."""
        devices: List[Dict] = []
        try:
            all_devs = sd.query_devices()
            all_apis = sd.query_hostapis()
            for i, d in enumerate(all_devs):
                if d["max_output_channels"] > 0:
                    api_name = (
                        all_apis[d["hostapi"]]["name"]
                        if d["hostapi"] < len(all_apis)
                        else "Unknown"
                    )
                    devices.append(
                        {
                            "id": i,
                            "name": d["name"],
                            "channels": d["max_output_channels"],
                            "hostapi": api_name,
                            "default_samplerate": int(
                                d.get("default_samplerate", 44_100)
                            ),
                        }
                    )
        except Exception as exc:
            logger.error("Error enumerating output devices: %s", exc)
        return devices

    def get_default_output_device_id(self) -> int:
        """Return the index of the current system default output device."""
        try:
            default = sd.default.device[1]
            return default if default >= 0 else 0
        except Exception:
            return 0

    def _get_wasapi_hostapi_idx(self) -> Optional[int]:
        try:
            for i, api in enumerate(sd.query_hostapis()):
                if "wasapi" in api["name"].lower():
                    return i
        except Exception:
            pass
        return None

    def find_stereo_mix_device(self) -> Optional[int]:
        """
        Fallback: look for a 'Stereo Mix' / 'What U Hear' input device.
        Returns the device index or None.
        """
        keywords = ("stereo mix", "what u hear", "wave out mix", "loopback")
        try:
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0 and any(
                    k in d["name"].lower() for k in keywords
                ):
                    return i
        except Exception:
            pass
        return None

    # ------------------------------------------------------------ volume / mute --

    def set_master_volume(self, volume: float) -> None:
        self._master_volume = max(0.0, min(1.0, volume))

    def get_master_volume(self) -> float:
        return self._master_volume

    def set_master_mute(self, muted: bool) -> None:
        self._master_muted = muted

    def is_master_muted(self) -> bool:
        return self._master_muted

    def set_device_volume(self, device_id: int, volume: float) -> None:
        self._device_volumes[device_id] = max(0.0, min(1.0, volume))

    def get_device_volume(self, device_id: int) -> float:
        return self._device_volumes.get(device_id, 1.0)

    def set_device_mute(self, device_id: int, muted: bool) -> None:
        self._device_muted[device_id] = muted

    def is_device_muted(self, device_id: int) -> bool:
        return self._device_muted.get(device_id, False)

    # ---------------------------------------------------------- delay offset --

    def set_device_delay(self, device_id: int, delay_ms: float) -> None:
        """Set per-device delay offset in milliseconds (0 – MAX_DELAY_MS)."""
        self._device_delays[device_id] = max(0.0, min(self.MAX_DELAY_MS, delay_ms))

    def get_device_delay(self, device_id: int) -> float:
        return self._device_delays.get(device_id, 0.0)

    # ---------------------------------------------------------- performance --

    def get_avg_cb_duration_ms(self) -> float:
        """Average audio callback duration in ms (for CPU monitoring)."""
        if not self._cb_durations:
            return 0.0
        return sum(self._cb_durations) / len(self._cb_durations) * 1000.0

    def get_buffer_underruns(self) -> int:
        return self._buffer_underruns

    def get_device_errors(self) -> Dict[int, str]:
        return dict(self._device_errors)

    # -------------------------------------------------------------- metering --

    def get_master_peak(self) -> List[float]:
        """Return [left, right] peak levels in range 0.0 – 1.0."""
        return list(self._master_peak)

    def get_device_peak(self, device_id: int) -> List[float]:
        return list(self._device_peaks.get(device_id, [0.0, 0.0]))

    def get_latency_ms(self) -> float:
        return self._latency_ms

    # ------------------------------------------------------------ audio CBs --

    def _input_callback(
        self, indata: np.ndarray, frames: int, time_info, status
    ) -> None:
        """Called by sounddevice from an audio thread on every captured block."""
        t0 = time.perf_counter()
        if status:
            logger.debug("Input CB status: %s", status)
            if status.input_underflow:
                self._buffer_underruns += 1

        with self._buffer_lock:
            # Normalise to 2-D (frames, channels)
            data = indata if indata.ndim == 2 else indata.reshape(-1, 1)

            # Up-mix to stereo if mono, down-mix if >2 ch
            if data.shape[1] == 1:
                data = np.concatenate([data, data], axis=1)
            elif data.shape[1] > 2:
                data = data[:, :2]

            block = data.astype(self.DTYPE, copy=True)
            self._audio_buffer = block

            # Store in delay ring buffer for delay compensation
            self._delay_buffer.append(block.copy())

            # Peak metering (master)
            if not self._master_muted:
                peaks = np.max(np.abs(data), axis=0)
                self._master_peak[0] = max(
                    float(peaks[0]), self._master_peak[0] * self.PEAK_DECAY
                )
                self._master_peak[1] = max(
                    float(peaks[1]), self._master_peak[1] * self.PEAK_DECAY
                )

        self._cb_durations.append(time.perf_counter() - t0)

    def _make_output_callback(self, device_id: int, out_channels: int) -> Callable:
        """Return a sounddevice output callback bound to *device_id*."""

        def callback(
            outdata: np.ndarray, frames: int, time_info, status
        ) -> None:
            if status:
                logger.debug("Output CB [%d] status: %s", device_id, status)
                if status.output_underflow:
                    self._buffer_underruns += 1

            with self._buffer_lock:
                muted = self._master_muted or self._device_muted.get(device_id, False)
                if muted:
                    outdata[:] = 0
                    self._device_peaks[device_id] = [0.0, 0.0]
                    return

                vol = self._master_volume * self._device_volumes.get(device_id, 1.0)

                # Delay compensation: pick the correct block from the ring buffer
                delay_ms = self._device_delays.get(device_id, 0.0)
                if delay_ms > 0 and len(self._delay_buffer) > 0:
                    block_duration_ms = self.BLOCK_SIZE / self.SAMPLE_RATE * 1000
                    blocks_back = int(delay_ms / block_duration_ms)
                    idx = max(0, len(self._delay_buffer) - 1 - blocks_back)
                    buf = self._delay_buffer[idx]
                else:
                    buf = self._audio_buffer  # shape (BLOCK_SIZE, 2)

                # Build output data with correct frame count
                if buf.shape[0] >= frames:
                    data = buf[:frames] * vol
                else:
                    data = np.zeros((frames, 2), dtype=self.DTYPE)
                    data[: buf.shape[0]] = buf * vol

                # Write to output (handle mono / multichannel outputs)
                if out_channels == 1:
                    outdata[:, 0] = (data[:, 0] + data[:, 1]) * 0.5
                elif out_channels == 2:
                    outdata[:] = data
                else:
                    outdata[:, :2] = data
                    outdata[:, 2:] = 0

                # Per-device peak metering
                peaks = np.max(np.abs(data), axis=0)
                prev = self._device_peaks.get(device_id, [0.0, 0.0])
                self._device_peaks[device_id] = [
                    max(float(peaks[0]), prev[0] * self.PEAK_DECAY),
                    max(float(peaks[1]), prev[1] * self.PEAK_DECAY),
                ]

        return callback

    # --------------------------------------------------------- routing control --

    def start_routing(
        self,
        output_device_ids: List[int],
        source_device_id: Optional[int] = None,
    ) -> None:
        """
        Begin routing system audio to the specified output devices.

        Parameters
        ----------
        output_device_ids : list of int
            Device indices to send audio to.
        source_device_id : int, optional
            The OUTPUT device whose audio will be captured via WASAPI loopback.
            Defaults to the system's current default output device.
        """
        if self._is_routing:
            self.stop_routing()

        if source_device_id is None:
            source_device_id = self.get_default_output_device_id()

        self._source_device_id = source_device_id

        # Ensure per-device defaults are set
        for dev_id in output_device_ids:
            self._device_volumes.setdefault(dev_id, 1.0)
            self._device_muted.setdefault(dev_id, False)
            self._device_peaks[dev_id] = [0.0, 0.0]

        # --- Open loopback capture stream ---
        try:
            if sys.platform == "win32":
                # WASAPI loopback: open the OUTPUT device as an INPUT with loopback=True
                extra = sd.WasapiSettings(loopback=True)
                dev_info = sd.query_devices(source_device_id)
                sr = int(dev_info.get("default_samplerate", self.SAMPLE_RATE))
                sr = sr if sr in (44_100, 48_000, 96_000) else self.SAMPLE_RATE

                self._input_stream = sd.InputStream(
                    device=source_device_id,
                    channels=self.CHANNELS,
                    samplerate=sr,
                    callback=self._input_callback,
                    blocksize=self.BLOCK_SIZE,
                    dtype=self.DTYPE,
                    extra_settings=extra,
                )
            else:
                # Non-Windows: try to open a regular input (for dev / testing)
                stereo_mix = self.find_stereo_mix_device()
                self._input_stream = sd.InputStream(
                    device=stereo_mix,
                    channels=self.CHANNELS,
                    samplerate=self.SAMPLE_RATE,
                    callback=self._input_callback,
                    blocksize=self.BLOCK_SIZE,
                    dtype=self.DTYPE,
                )

            self._input_stream.start()
            self._latency_ms = self.BLOCK_SIZE / self.SAMPLE_RATE * 1000
            logger.info("Loopback capture started (device %d)", source_device_id)

        except Exception as exc:
            msg = (
                f"Cannot start loopback capture: {exc}\n\n"
                "• Make sure the selected Source Device is active.\n"
                "• On older Windows systems, enable 'Stereo Mix' in "
                "Sound Settings → Recording tab."
            )
            if self.on_error:
                self.on_error(msg)
            raise RuntimeError(msg) from exc

        # --- Open output streams ---
        errors: List[str] = []
        for dev_id in output_device_ids:
            try:
                self._open_output_stream(dev_id)
            except Exception as exc:
                errors.append(f"  • Device {dev_id}: {exc}")
                logger.error("Failed to open output %d: %s", dev_id, exc)

        self._is_routing = True

        if not self._output_streams:
            self.stop_routing()
            msg = "Could not open any output streams:\n" + "\n".join(errors)
            if self.on_error:
                self.on_error(msg)
            raise RuntimeError(msg)

        if self.on_routing_changed:
            self.on_routing_changed(True)

    def _open_output_stream(self, device_id: int) -> None:
        """Open and start an output stream for *device_id*."""
        if device_id in self._output_streams:
            return  # Already open

        dev_info = sd.query_devices(device_id)
        out_ch = min(int(dev_info["max_output_channels"]), self.CHANNELS)

        # Pick best supported sample rate
        chosen_sr = self.SAMPLE_RATE
        for rate in (48_000, 44_100, 96_000, 32_000, 22_050):
            try:
                sd.check_output_settings(
                    device=device_id, channels=out_ch, samplerate=rate
                )
                chosen_sr = rate
                break
            except sd.PortAudioError:
                continue

        stream = sd.OutputStream(
            device=device_id,
            channels=out_ch,
            samplerate=chosen_sr,
            callback=self._make_output_callback(device_id, out_ch),
            blocksize=self.BLOCK_SIZE,
            dtype=self.DTYPE,
            latency="low",
        )
        stream.start()
        self._output_streams[device_id] = stream
        self._device_peaks.setdefault(device_id, [0.0, 0.0])
        # Clear any previous error state on successful open
        self._failed_devices.pop(device_id, None)
        self._device_errors.pop(device_id, None)
        logger.info(
            "Output stream opened: device %d  ch=%d  sr=%d",
            device_id,
            out_ch,
            chosen_sr,
        )

    def stop_routing(self) -> None:
        """Stop all loopback capture and output streams."""
        self._is_routing = False

        if self._input_stream:
            try:
                self._input_stream.stop()
                self._input_stream.close()
            except Exception as exc:
                logger.error("Error closing input stream: %s", exc)
            self._input_stream = None

        for dev_id in list(self._output_streams):
            self._close_output_stream(dev_id)

        self._master_peak = [0.0, 0.0]
        for dev_id in self._device_peaks:
            self._device_peaks[dev_id] = [0.0, 0.0]

        if self.on_routing_changed:
            self.on_routing_changed(False)

        logger.info("Audio routing stopped")

    def _close_output_stream(self, device_id: int) -> None:
        if device_id not in self._output_streams:
            return
        try:
            self._output_streams[device_id].stop()
            self._output_streams[device_id].close()
        except Exception as exc:
            logger.error("Error closing output stream %d: %s", device_id, exc)
        del self._output_streams[device_id]
        self._device_peaks[device_id] = [0.0, 0.0]

    def add_output(self, device_id: int) -> None:
        """Hot-add an output device without restarting routing."""
        if not self._is_routing:
            raise RuntimeError("Routing not active — call start_routing() first.")
        self._device_volumes.setdefault(device_id, 1.0)
        self._device_muted.setdefault(device_id, False)
        self._open_output_stream(device_id)

    def remove_output(self, device_id: int) -> None:
        """Hot-remove an output device without restarting routing."""
        self._close_output_stream(device_id)
        self._failed_devices.pop(device_id, None)
        self._device_errors.pop(device_id, None)

    def try_reconnect_device(self, device_id: int) -> bool:
        """
        Attempt to reconnect a failed output device.
        Returns True on success, False if the device could not be reopened.
        """
        if not self._is_routing:
            return False

        retries = self._failed_devices.get(device_id, 0)
        if retries >= self.MAX_RECONNECT_ATTEMPTS:
            return False

        try:
            # Close any leftover stream
            self._close_output_stream(device_id)
            self._open_output_stream(device_id)
            logger.info("Successfully reconnected device %d", device_id)
            if self.on_device_recovered:
                self.on_device_recovered(device_id)
            return True
        except Exception as exc:
            self._failed_devices[device_id] = retries + 1
            self._device_errors[device_id] = str(exc)
            logger.warning(
                "Reconnect attempt %d/%d failed for device %d: %s",
                retries + 1,
                self.MAX_RECONNECT_ATTEMPTS,
                device_id,
                exc,
            )
            return False

    def handle_device_failure(self, device_id: int, error_msg: str) -> None:
        """
        Called when an output device stream fails during routing.
        Gracefully removes the device and notifies the UI.
        """
        logger.error("Device %d failed: %s", device_id, error_msg)
        self._close_output_stream(device_id)
        self._failed_devices[device_id] = self._failed_devices.get(device_id, 0)
        self._device_errors[device_id] = error_msg

        if self.on_device_error:
            self.on_device_error(device_id, error_msg)

    # ------------------------------------------------------------ properties --

    @property
    def is_routing(self) -> bool:
        return self._is_routing

    @property
    def active_output_count(self) -> int:
        return len(self._output_streams)

    @property
    def active_device_ids(self) -> List[int]:
        return list(self._output_streams.keys())

    @property
    def failed_device_ids(self) -> List[int]:
        """Return IDs of devices that have failed and may need reconnection."""
        return list(self._failed_devices.keys())
