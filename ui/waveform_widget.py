"""
ui/waveform_widget.py
=====================
Scrolling audio waveform widget drawn with QPainter.

The widget stores a down-sampled min/max envelope for the last few seconds of
incoming audio and renders it as a filled polygon, similar to editors such as
Audacity or SoundCloud.  Stereo input is shown as two stacked waveforms.
"""

from collections import deque
import math
import threading
from typing import Deque, List, Tuple

from PyQt5.QtCore import QLineF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget
import numpy as np


class WaveformWidget(QWidget):
    """
    Scrolling waveform visualiser for mono or stereo audio.

    Audio blocks may be pushed from a non-Qt audio callback thread via
    :meth:`push_samples`.  The widget stores only a compact min/max envelope to
    keep CPU usage low while still drawing a smooth scrolling waveform.
    """

    # Colour zones
    _GREEN = QColor("#3fb950")
    _YELLOW = QColor("#f0a500")
    _RED = QColor("#f85149")
    _BG = QColor("#21262d")
    _PEAK_HOLD = QColor("#ffffff")

    # Zone thresholds (linear amplitude, not dB)
    _YELLOW_THRESH = 0.70
    _RED_THRESH = 0.85

    _GRID = QColor(60, 70, 80, 140)
    _OUTLINE = QColor(255, 255, 255, 22)
    _CHANNEL_GAP = 8
    _DISPLAY_POINTS = 200
    _DEFAULT_UPDATE_MS = 33

    def __init__(self, parent=None, display_seconds: float = 5.0, sample_rate: int = 48000):
        super().__init__(parent)
        self._display_seconds = max(0.25, float(display_seconds))
        self._sample_rate = max(1, int(sample_rate))
        self._update_interval_ms = self._DEFAULT_UPDATE_MS

        self._lock = threading.Lock()
        self._channel_count = 0
        self._bucket_size = 1
        self._pending_count = 0
        self._pending_min = np.zeros(2, dtype=np.float32)
        self._pending_max = np.zeros(2, dtype=np.float32)
        self._buffers: List[Deque[Tuple[float, float]]] = [
            deque(maxlen=self._DISPLAY_POINTS),
            deque(maxlen=self._DISPLAY_POINTS),
        ]

        self._rebuild_buffers(reset_existing=True)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(self._update_interval_ms)
        self._refresh_timer.timeout.connect(self.update)
        self._refresh_timer.start()

        self.setMinimumHeight(120)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    # ---------------------------------------------------------------- public API --

    def push_samples(self, block: np.ndarray) -> None:
        """Push an audio block from the audio thread."""
        data = np.asarray(block)
        if data.size == 0:
            return

        if data.ndim == 1:
            data = data.reshape(-1, 1)
        elif data.ndim != 2:
            return

        if data.shape[1] == 0:
            return

        channels = min(2, data.shape[1])
        data = np.ascontiguousarray(data[:, :channels], dtype=np.float32)

        with self._lock:
            if self._channel_count not in (0, channels):
                self._reset_locked()
            self._channel_count = channels

            offset = 0
            frame_count = data.shape[0]
            while offset < frame_count:
                needed = self._bucket_size - self._pending_count
                chunk = data[offset : offset + needed]
                if chunk.size == 0:
                    break

                chunk_min = np.min(chunk, axis=0)
                chunk_max = np.max(chunk, axis=0)
                if self._pending_count == 0:
                    self._pending_min[:channels] = chunk_min
                    self._pending_max[:channels] = chunk_max
                else:
                    self._pending_min[:channels] = np.minimum(self._pending_min[:channels], chunk_min)
                    self._pending_max[:channels] = np.maximum(self._pending_max[:channels], chunk_max)

                self._pending_count += chunk.shape[0]
                offset += chunk.shape[0]

                if self._pending_count >= self._bucket_size:
                    for ch in range(channels):
                        self._buffers[ch].append((float(self._pending_min[ch]), float(self._pending_max[ch])))
                    self._pending_count = 0

    def reset(self) -> None:
        with self._lock:
            self._reset_locked()
        self.update()

    def set_display_seconds(self, seconds: float) -> None:
        self._display_seconds = max(0.25, float(seconds))
        with self._lock:
            self._rebuild_buffers(reset_existing=True)
        self.update()

    def set_update_interval(self, milliseconds: int) -> None:
        """Set repaint cadence for the visualiser."""
        self._update_interval_ms = max(15, int(milliseconds))
        self._refresh_timer.setInterval(self._update_interval_ms)

    # --------------------------------------------------------------- painting --

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), self._BG)

        with self._lock:
            channel_count = max(1, self._channel_count)
            envelopes = [list(buf) for buf in self._buffers[:channel_count]]
            if self._pending_count > 0 and self._channel_count > 0:
                for ch in range(self._channel_count):
                    envelopes[ch].append((float(self._pending_min[ch]), float(self._pending_max[ch])))

        width = self.width()
        height = self.height()
        if width <= 1 or height <= 1:
            painter.end()
            return

        gap = self._CHANNEL_GAP if channel_count > 1 else 0
        channel_height = max(1, (height - gap * (channel_count - 1)) // channel_count)

        for ch in range(channel_count):
            top = ch * (channel_height + gap)
            rect = QRectF(0.0, float(top), float(width), float(channel_height))
            self._draw_channel(painter, rect, envelopes[ch])

        painter.end()

    # -------------------------------------------------------------- internals --

    def _reset_locked(self) -> None:
        self._channel_count = 0
        self._pending_count = 0
        self._pending_min.fill(0.0)
        self._pending_max.fill(0.0)
        for buffer in self._buffers:
            buffer.clear()

    def _rebuild_buffers(self, reset_existing: bool) -> None:
        bucket = self._sample_rate * self._display_seconds / float(self._DISPLAY_POINTS)
        self._bucket_size = max(1, int(math.ceil(bucket)))
        self._buffers = [
            deque(self._buffers[0] if not reset_existing else (), maxlen=self._DISPLAY_POINTS),
            deque(self._buffers[1] if not reset_existing else (), maxlen=self._DISPLAY_POINTS),
        ]
        self._pending_count = 0
        self._pending_min.fill(0.0)
        self._pending_max.fill(0.0)
        if reset_existing:
            self._channel_count = 0

    def _draw_channel(self, painter: QPainter, rect: QRectF, envelope: List[Tuple[float, float]]) -> None:
        painter.fillRect(rect, self._BG.darker(110))

        centre_y = rect.center().y()
        half_height = max(1.0, rect.height() * 0.5 - 2.0)
        painter.setPen(QPen(self._GRID, 1))
        painter.drawLine(QLineF(rect.left(), centre_y, rect.right(), centre_y))

        if not envelope:
            return

        path = self._build_waveform_path(rect, centre_y, half_height, envelope)
        if path.isEmpty():
            return

        green_top = centre_y - half_height * self._YELLOW_THRESH
        green_bottom = centre_y + half_height * self._YELLOW_THRESH
        yellow_top = centre_y - half_height * self._RED_THRESH
        yellow_bottom = centre_y + half_height * self._RED_THRESH

        zones = (
            (QRectF(rect.left(), rect.top(), rect.width(), max(0.0, yellow_top - rect.top())), self._RED),
            (QRectF(rect.left(), yellow_top, rect.width(), max(0.0, green_top - yellow_top)), self._YELLOW),
            (QRectF(rect.left(), green_top, rect.width(), max(0.0, green_bottom - green_top)), self._GREEN),
            (QRectF(rect.left(), green_bottom, rect.width(), max(0.0, yellow_bottom - green_bottom)), self._YELLOW),
            (QRectF(rect.left(), yellow_bottom, rect.width(), max(0.0, rect.bottom() - yellow_bottom)), self._RED),
        )

        painter.setPen(Qt.NoPen)
        for clip_rect, colour in zones:
            if clip_rect.height() <= 0.0:
                continue
            painter.save()
            painter.setClipRect(clip_rect)
            painter.fillPath(path, colour)
            painter.restore()

        painter.setPen(QPen(self._OUTLINE, 1))
        painter.drawPath(path)

    def _build_waveform_path(
        self,
        rect: QRectF,
        centre_y: float,
        half_height: float,
        envelope: List[Tuple[float, float]],
    ) -> QPainterPath:
        count = len(envelope)
        if count == 0:
            return QPainterPath()

        if count == 1:
            min_val, max_val = envelope[0]
            x_positions = [rect.left(), rect.right()]
            upper_vals = [max_val, max_val]
            lower_vals = [min_val, min_val]
        else:
            step = rect.width() / float(count - 1)
            x_positions = [rect.left() + i * step for i in range(count)]
            upper_vals = [pair[1] for pair in envelope]
            lower_vals = [pair[0] for pair in envelope]

        path = QPainterPath()
        path.moveTo(x_positions[0], self._sample_to_y(upper_vals[0], centre_y, half_height))
        for x_pos, value in zip(x_positions[1:], upper_vals[1:]):
            path.lineTo(x_pos, self._sample_to_y(value, centre_y, half_height))

        for x_pos, value in zip(reversed(x_positions), reversed(lower_vals)):
            path.lineTo(x_pos, self._sample_to_y(value, centre_y, half_height))

        path.closeSubpath()
        return path

    @staticmethod
    def _sample_to_y(value: float, centre_y: float, half_height: float) -> float:
        value = max(-1.0, min(1.0, float(value)))
        return centre_y - value * half_height
