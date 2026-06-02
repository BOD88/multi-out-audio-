"""
ui/vu_meter.py
==============
Animated stereo VU meter widget drawn with QPainter.

The meter shows left and right channel levels as vertical bars segmented
into three zones:
  • Green  (0 – 70 %)  — normal
  • Yellow (70 – 85 %) — approaching limit
  • Red    (85 – 100%) — clipping

A peak-hold dot decays slowly for visual comfort.
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QLinearGradient
from PyQt5.QtWidgets import QWidget


class VUMeter(QWidget):
    """
    Vertical stereo VU meter.

    Usage::

        meter = VUMeter(parent=self)
        meter.set_levels(left=0.75, right=0.60)   # 0.0 – 1.0
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

    # Peak hold duration (number of 50 ms ticks)
    _PEAK_HOLD_TICKS = 30  # ~1.5 seconds
    # Peak decay speed (fraction per tick)
    _PEAK_DECAY = 0.05

    def __init__(self, parent=None, bar_count: int = 2) -> None:
        super().__init__(parent)
        self._bar_count = bar_count
        self._levels = [0.0] * bar_count
        self._peaks = [0.0] * bar_count
        self._peak_timers = [0] * bar_count  # Ticks since last rise
        self.setMinimumSize(bar_count * 12 + (bar_count - 1) * 3, 80)
        self.setMaximumWidth(bar_count * 14 + (bar_count - 1) * 3 + 4)

    # ---------------------------------------------------------------- public API --

    def set_levels(self, *levels: float) -> None:
        """
        Set channel levels.  Pass one value per bar (0.0 – 1.0).
        Only the first *bar_count* values are used.
        """
        changed = False
        for i, val in enumerate(levels[: self._bar_count]):
            val = max(0.0, min(1.0, float(val)))
            if abs(val - self._levels[i]) > 0.002:
                changed = True
            self._levels[i] = val

            # Update peak hold
            if val >= self._peaks[i]:
                self._peaks[i] = val
                self._peak_timers[i] = 0
            else:
                self._peak_timers[i] += 1
                if self._peak_timers[i] > self._PEAK_HOLD_TICKS:
                    self._peaks[i] = max(0.0, self._peaks[i] - self._PEAK_DECAY)

        if changed:
            self.update()

    def reset(self) -> None:
        self._levels = [0.0] * self._bar_count
        self._peaks = [0.0] * self._bar_count
        self._peak_timers = [0] * self._bar_count
        self.update()

    # --------------------------------------------------------------- painting --

    def paintEvent(self, event) -> None:  # noqa: N802
        w, h = self.width(), self.height()
        if self._bar_count == 0:
            return

        bar_w = max(6, (w - (self._bar_count - 1) * 3) // self._bar_count)
        gap = 3
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        for i in range(self._bar_count):
            x = i * (bar_w + gap)
            self._draw_bar(painter, x, 0, bar_w, h, self._levels[i], self._peaks[i])

        painter.end()

    def _draw_bar(
        self,
        p: QPainter,
        x: int,
        y: int,
        w: int,
        h: int,
        level: float,
        peak: float,
    ) -> None:
        # Background
        p.fillRect(x, y, w, h, self._BG)

        if level <= 0.0:
            # Draw faint peak marker even when silent
            if peak > 0.01:
                py = y + int(h * (1.0 - peak))
                p.fillRect(x, py, w, 2, QColor(60, 70, 80))
            return

        # Filled bar height
        fill_h = int(h * level)
        fill_y = y + h - fill_h

        # Segment the bar into colour zones
        red_h = int(h * (1.0 - self._RED_THRESH))        # top portion
        yellow_h = int(h * (self._RED_THRESH - self._YELLOW_THRESH))
        green_h = h - red_h - yellow_h

        # Draw background segments (dim versions of each zone colour)
        p.fillRect(x, y, w, red_h, QColor(50, 15, 15))
        p.fillRect(x, y + red_h, w, yellow_h, QColor(45, 35, 5))
        p.fillRect(x, y + red_h + yellow_h, w, green_h, QColor(10, 30, 15))

        # Draw filled portion
        remaining = fill_h
        current_y = y + h  # draw upward

        def _fill_zone(zone_top: int, zone_h: int, colour: QColor) -> None:
            nonlocal remaining, current_y
            if remaining <= 0:
                return
            overlap = min(remaining, (current_y) - max(zone_top, current_y - remaining))
            if overlap <= 0:
                return
            drawn = min(remaining, max(0, current_y - zone_top))
            draw_y = current_y - drawn
            p.fillRect(x, draw_y, w, drawn, colour)
            remaining -= drawn
            current_y = draw_y

        _fill_zone(y + red_h + yellow_h, green_h, self._GREEN)
        _fill_zone(y + red_h, yellow_h, self._YELLOW)
        _fill_zone(y, red_h, self._RED)

        # Peak hold dot
        if peak > 0.01:
            py = y + int(h * (1.0 - peak))
            peak_colour = (
                self._RED if peak > self._RED_THRESH
                else self._YELLOW if peak > self._YELLOW_THRESH
                else self._GREEN
            )
            p.fillRect(x, py, w, 2, peak_colour.lighter(150))
