"""
ui/device_card.py
=================
Widget representing a single audio output device in the device list.

Shows:
  • Enable checkbox (routes audio to this device when checked)
  • Device name and host-API badge
  • Stereo VU meter
  • Volume slider + percentage label
  • Mute button
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .vu_meter import VUMeter
from .styles import COLOURS


class DeviceCard(QFrame):
    """
    Emits signals when the user changes enable/volume/mute state.

    Signals
    -------
    enabled_changed(device_id, is_enabled)
    volume_changed(device_id, volume_float)
    mute_changed(device_id, is_muted)
    """

    enabled_changed = pyqtSignal(int, bool)
    volume_changed = pyqtSignal(int, float)
    mute_changed = pyqtSignal(int, bool)
    delay_changed = pyqtSignal(int, float)  # (device_id, delay_ms)

    def __init__(self, device_info: dict, parent=None) -> None:
        super().__init__(parent)
        self._device_id: int = device_info["id"]
        self._device_name: str = device_info["name"]
        self._hostapi: str = device_info.get("hostapi", "")
        self._default_latency_ms: float = device_info.get("default_latency_ms", 0.0)
        self._active: bool = False  # True while routing is live for this device
        self._delay_manually_set: bool = False  # True after user manually adjusts delay

        self.setObjectName("device_card")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build_ui()
        self._connect_signals()

    # ---------------------------------------------------------------- UI build --

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(10)

        # ── Checkbox ──
        self._chk = QCheckBox()
        self._chk.setToolTip("Enable routing to this device")
        root.addWidget(self._chk)

        # ── Name + badge ──
        name_col = QVBoxLayout()
        name_col.setSpacing(2)

        self._lbl_name = QLabel(self._device_name)
        self._lbl_name.setStyleSheet(
            f"color: {COLOURS['text_primary']}; font-weight: 600; font-size: 12px;"
        )
        self._lbl_name.setWordWrap(False)
        name_col.addWidget(self._lbl_name)

        self._lbl_api = QLabel(self._hostapi)
        self._lbl_api.setStyleSheet(
            f"color: {COLOURS['text_secondary']}; font-size: 10px;"
        )
        name_col.addWidget(self._lbl_api)

        root.addLayout(name_col, stretch=2)

        # ── VU meter ──
        self._vu = VUMeter(bar_count=2)
        self._vu.setFixedSize(28, 50)
        root.addWidget(self._vu)

        # ── Volume slider + label ──
        vol_col = QVBoxLayout()
        vol_col.setSpacing(2)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(100)
        self._slider.setFixedWidth(130)
        self._slider.setToolTip("Device volume")
        vol_col.addWidget(self._slider)

        self._lbl_vol = QLabel("100 %")
        self._lbl_vol.setAlignment(Qt.AlignCenter)
        self._lbl_vol.setStyleSheet(
            f"color: {COLOURS['text_secondary']}; font-size: 11px;"
        )
        self._lbl_vol.setFixedWidth(44)
        vol_col.addWidget(self._lbl_vol)

        root.addLayout(vol_col)

        # ── Mute button ──
        self._btn_mute = QPushButton("🔊")
        self._btn_mute.setObjectName("btn_mute")
        self._btn_mute.setCheckable(True)
        self._btn_mute.setToolTip("Mute this device")
        root.addWidget(self._btn_mute)

        # ── Delay slider ──
        delay_col = QVBoxLayout()
        delay_col.setSpacing(2)

        self._sld_delay = QSlider(Qt.Horizontal)
        self._sld_delay.setRange(0, 500)
        self._sld_delay.setValue(0)
        self._sld_delay.setFixedWidth(80)
        self._sld_delay.setToolTip(
            "Delay offset (ms) — compensate for latency differences\n"
            "between wired and wireless devices"
        )
        delay_col.addWidget(self._sld_delay)

        self._lbl_delay = QLabel("0 ms")
        self._lbl_delay.setAlignment(Qt.AlignCenter)
        self._lbl_delay.setStyleSheet(
            f"color: {COLOURS['text_secondary']}; font-size: 10px;"
        )
        self._lbl_delay.setFixedWidth(44)
        delay_col.addWidget(self._lbl_delay)

        root.addLayout(delay_col)

    # ---------------------------------------------------------------- signals --

    def _connect_signals(self) -> None:
        self._chk.toggled.connect(self._on_enable_toggled)
        self._slider.valueChanged.connect(self._on_volume_changed)
        self._btn_mute.toggled.connect(self._on_mute_toggled)
        self._sld_delay.valueChanged.connect(self._on_delay_changed)

    def _on_enable_toggled(self, checked: bool) -> None:
        self._update_active_style(checked)
        self.enabled_changed.emit(self._device_id, checked)

    def _on_volume_changed(self, value: int) -> None:
        self._lbl_vol.setText(f"{value} %")
        self.volume_changed.emit(self._device_id, value / 100.0)

    def _on_mute_toggled(self, checked: bool) -> None:
        self._btn_mute.setText("🔇" if checked else "🔊")
        self.mute_changed.emit(self._device_id, checked)

    def _on_delay_changed(self, value: int) -> None:
        self._lbl_delay.setText(f"{value} ms")
        self._delay_manually_set = True
        self.delay_changed.emit(self._device_id, float(value))

    # ---------------------------------------------------------------- public --

    @property
    def device_id(self) -> int:
        return self._device_id

    def is_enabled(self) -> bool:
        return self._chk.isChecked()

    def set_enabled(self, enabled: bool) -> None:
        self._chk.setChecked(enabled)

    def get_volume(self) -> float:
        return self._slider.value() / 100.0

    def set_volume(self, volume: float) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(volume * 100))
        self._lbl_vol.setText(f"{int(volume * 100)} %")
        self._slider.blockSignals(False)

    def set_levels(self, left: float, right: float) -> None:
        self._vu.set_levels(left, right)

    def get_delay(self) -> float:
        return float(self._sld_delay.value())

    def set_delay(self, delay_ms: float) -> None:
        self._sld_delay.blockSignals(True)
        self._sld_delay.setValue(int(delay_ms))
        self._lbl_delay.setText(f"{int(delay_ms)} ms")
        self._sld_delay.blockSignals(False)

    def set_delay_auto(self, delay_ms: float) -> None:
        """Set delay without marking as manually overridden."""
        self._sld_delay.blockSignals(True)
        self._sld_delay.setValue(int(delay_ms))
        self._lbl_delay.setText(f"{int(delay_ms)} ms")
        self._sld_delay.blockSignals(False)
        # Do not set _delay_manually_set — this is an automatic value

    @property
    def delay_manually_set(self) -> bool:
        return self._delay_manually_set

    def clear_manual_delay(self) -> None:
        """Reset the manual override flag (e.g. when auto-sync is toggled on)."""
        self._delay_manually_set = False

    @property
    def default_latency_ms(self) -> float:
        return self._default_latency_ms

    def reset_meter(self) -> None:
        self._vu.reset()

    def _update_active_style(self, active: bool) -> None:
        self._active = active
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
