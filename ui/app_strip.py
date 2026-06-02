"""
ui/app_strip.py
===============
Widget showing a single application's audio session controls:
  • App name (process name)
  • Animated peak level bar
  • Volume slider + percentage label
  • Mute button
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
)

from .vu_meter import VUMeter
from .styles import COLOURS


class AppStrip(QFrame):
    """
    Emits signals when the user adjusts volume or mute for an app session.

    Signals
    -------
    volume_changed(session_id, volume_float)
    mute_changed(session_id, is_muted)
    """

    volume_changed = pyqtSignal(int, float)   # (pid, volume)
    mute_changed = pyqtSignal(int, bool)       # (pid, muted)

    def __init__(self, session, parent=None) -> None:
        super().__init__(parent)
        self._session = session
        self._pid: int = session.pid
        self._name: str = session.process_name

        self.setObjectName("app_strip")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build_ui()
        self._connect_signals()

        # Initialise from session state
        try:
            vol = session.get_volume()
            muted = session.get_mute()
        except Exception:
            vol, muted = 1.0, False

        self._slider.blockSignals(True)
        self._slider.setValue(int(vol * 100))
        self._lbl_vol.setText(f"{int(vol * 100)} %")
        self._slider.blockSignals(False)

        if muted:
            self._btn_mute.setChecked(True)
            self._btn_mute.setText("🔇")

    # ---------------------------------------------------------------- UI build --

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 6)
        root.setSpacing(10)

        # App icon placeholder + name
        self._lbl_icon = QLabel("🎵")
        self._lbl_icon.setFixedWidth(20)
        root.addWidget(self._lbl_icon)

        self._lbl_name = QLabel(self._name)
        self._lbl_name.setStyleSheet(
            f"color: {COLOURS['text_primary']}; font-weight: 600;"
        )
        self._lbl_name.setMinimumWidth(120)
        self._lbl_name.setMaximumWidth(200)
        root.addWidget(self._lbl_name, stretch=1)

        # Peak meter (mono – single bar for app strip)
        self._vu = VUMeter(bar_count=1)
        self._vu.setFixedSize(14, 36)
        root.addWidget(self._vu)

        # Volume slider
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(100)
        self._slider.setFixedWidth(120)
        self._slider.setToolTip("Application volume")
        root.addWidget(self._slider)

        self._lbl_vol = QLabel("100 %")
        self._lbl_vol.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._lbl_vol.setStyleSheet(
            f"color: {COLOURS['text_secondary']}; font-size: 11px;"
        )
        self._lbl_vol.setFixedWidth(44)
        root.addWidget(self._lbl_vol)

        # Mute button
        self._btn_mute = QPushButton("🔊")
        self._btn_mute.setObjectName("btn_mute")
        self._btn_mute.setCheckable(True)
        self._btn_mute.setToolTip("Mute this application")
        root.addWidget(self._btn_mute)

    # ---------------------------------------------------------------- signals --

    def _connect_signals(self) -> None:
        self._slider.valueChanged.connect(self._on_volume_changed)
        self._btn_mute.toggled.connect(self._on_mute_toggled)

    def _on_volume_changed(self, value: int) -> None:
        self._lbl_vol.setText(f"{value} %")
        self.volume_changed.emit(self._pid, value / 100.0)

    def _on_mute_toggled(self, checked: bool) -> None:
        self._btn_mute.setText("🔇" if checked else "🔊")
        self.mute_changed.emit(self._pid, checked)

    # ---------------------------------------------------------------- public --

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def session(self):
        return self._session

    def set_peak(self, level: float) -> None:
        self._vu.set_levels(level)

    def reset_meter(self) -> None:
        self._vu.reset()
