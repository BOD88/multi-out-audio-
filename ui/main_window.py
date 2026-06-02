"""
ui/main_window.py
=================
Main application window for Multi-Output Audio Console.

Layout
------
┌─────────────────────────────────────────────────────────────────┐
│  Toolbar: [▶ START ROUTING]  [⏹ STOP]  ● Status  Source: ▼     │
├────────────────────┬────────────────────────────────────────────┤
│  MASTER CONTROL    │  OUTPUT DEVICES                [⟳ Refresh] │
│  ─────────────     │  ┌──────────────────────────────────────┐ │
│  VU meter          │  │  DeviceCard × N (scrollable)         │ │
│  Master vol slider │  └──────────────────────────────────────┘ │
│  [Mute All]        ├────────────────────────────────────────────┤
│                    │  APPLICATION MIXER             [⟳ Refresh] │
│                    │  ┌──────────────────────────────────────┐ │
│                    │  │  AppStrip × M (scrollable)           │ │
│                    │  └──────────────────────────────────────┘ │
└────────────────────┴────────────────────────────────────────────┘
│  Status bar: latency | active outputs | CPU             │
└─────────────────────────────────────────────────────────┘
"""

import logging
import sys
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from audio_engine import AudioRouter
from device_manager import DeviceManager
from ui.device_card import DeviceCard
from ui.app_strip import AppStrip
from ui.vu_meter import VUMeter
from ui.styles import COLOURS, STYLESHEET

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main window of the Multi-Output Audio Console."""

    METER_REFRESH_MS = 50   # 20 Hz metering updates
    APP_REFRESH_MS = 2_000  # Refresh app list every 2 s

    def __init__(self) -> None:
        super().__init__()
        self._router = AudioRouter()
        self._dev_mgr = DeviceManager()

        # Maps device_id → DeviceCard widget
        self._device_cards: Dict[int, DeviceCard] = {}
        # Maps pid → AppStrip widget
        self._app_strips: Dict[int, AppStrip] = {}

        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._populate_devices()
        self._populate_apps()
        self._start_timers()

    # ---------------------------------------------------------------- window setup --

    def _setup_window(self) -> None:
        self.setWindowTitle("🔊  Multi-Output Audio Console")
        self.setMinimumSize(900, 620)
        self.resize(1100, 720)
        self.setStyleSheet(STYLESHEET)

    # ---------------------------------------------------------------- UI build --

    def _build_ui(self) -> None:
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Toolbar ──
        self._build_toolbar()

        # ── Body (splitter: left master panel | right device+app panels) ──
        body = QSplitter(Qt.Horizontal)
        body.setHandleWidth(1)
        body.setStyleSheet(f"QSplitter::handle {{ background: {COLOURS['border']}; }}")
        main_layout.addWidget(body, stretch=1)

        body.addWidget(self._build_master_panel())
        body.addWidget(self._build_right_panel())
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setSizes([240, 860])

        # ── Status bar ──
        self._build_status_bar()

    # ── Toolbar ──────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setStyleSheet(
            f"QToolBar {{ background: {COLOURS['bg_panel']}; "
            f"border-bottom: 1px solid {COLOURS['border']}; "
            f"padding: 4px 8px; spacing: 8px; }}"
        )
        self.addToolBar(tb)

        # Start / Stop buttons
        self._btn_start = QPushButton("▶  START ROUTING")
        self._btn_start.setObjectName("btn_start")
        self._btn_start.setToolTip(
            "Capture system audio and send it to all enabled output devices"
        )
        tb.addWidget(self._btn_start)

        self._btn_stop = QPushButton("⏹  STOP")
        self._btn_stop.setObjectName("btn_stop")
        self._btn_stop.setEnabled(False)
        tb.addWidget(self._btn_stop)

        tb.addSeparator()

        # Status indicator
        self._lbl_status_dot = QLabel("⬤")
        self._lbl_status_dot.setStyleSheet(f"color: {COLOURS['text_secondary']}; font-size: 14px;")
        tb.addWidget(self._lbl_status_dot)

        self._lbl_status = QLabel("Idle")
        self._lbl_status.setObjectName("lbl_status_inactive")
        self._lbl_status.setMinimumWidth(120)
        tb.addWidget(self._lbl_status)

        tb.addSeparator()

        # Source device selector
        lbl_src = QLabel("  Capture Source:")
        lbl_src.setStyleSheet(f"color: {COLOURS['text_secondary']};")
        tb.addWidget(lbl_src)

        self._cmb_source = QComboBox()
        self._cmb_source.setToolTip(
            "The audio output device whose playback will be captured and routed.\n"
            "Normally this should be your current default speakers / headphones."
        )
        self._cmb_source.setMinimumWidth(240)
        tb.addWidget(self._cmb_source)

        # Refresh source list
        self._btn_refresh_src = QPushButton("⟳")
        self._btn_refresh_src.setToolTip("Refresh source device list")
        self._btn_refresh_src.setFixedWidth(32)
        tb.addWidget(self._btn_refresh_src)

        self._populate_source_combo()

    # ── Master panel (left) ───────────────────────────────────────────────────

    def _build_master_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(220)
        panel.setStyleSheet(
            f"background-color: {COLOURS['bg_panel']}; "
            f"border-right: 1px solid {COLOURS['border']};"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Title
        title = QLabel("MASTER")
        title.setObjectName("lbl_section")
        layout.addWidget(title, alignment=Qt.AlignHCenter)

        # Master VU meter (stereo)
        meter_row = QHBoxLayout()
        meter_row.setAlignment(Qt.AlignHCenter)
        self._master_vu = VUMeter(bar_count=2)
        self._master_vu.setFixedSize(40, 160)
        meter_row.addWidget(self._master_vu)
        layout.addLayout(meter_row)

        # dB labels next to the meter
        db_frame = QFrame()
        db_lay = QVBoxLayout(db_frame)
        db_lay.setContentsMargins(0, 0, 0, 0)
        db_lay.setSpacing(0)
        for label_text in ("0 dB", "-6", "-12", "-24", "–∞"):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {COLOURS['text_secondary']}; font-size: 9px;"
            )
            db_lay.addWidget(lbl, alignment=Qt.AlignRight)
        layout.addWidget(db_frame)

        # Master volume label
        self._lbl_master_vol_title = QLabel("MASTER VOLUME")
        self._lbl_master_vol_title.setObjectName("lbl_section")
        layout.addWidget(self._lbl_master_vol_title, alignment=Qt.AlignHCenter)

        # Master volume slider (vertical)
        self._sld_master = QSlider(Qt.Vertical)
        self._sld_master.setRange(0, 100)
        self._sld_master.setValue(100)
        self._sld_master.setFixedHeight(100)
        self._sld_master.setToolTip("Master volume — applied to all outputs")
        layout.addWidget(self._sld_master, alignment=Qt.AlignHCenter)

        self._lbl_master_vol = QLabel("100 %")
        self._lbl_master_vol.setAlignment(Qt.AlignHCenter)
        self._lbl_master_vol.setStyleSheet(
            f"color: {COLOURS['accent']}; font-size: 18px; font-weight: 700;"
        )
        layout.addWidget(self._lbl_master_vol)

        # Mute All button
        self._btn_mute_all = QPushButton("🔊  MUTE ALL")
        self._btn_mute_all.setCheckable(True)
        self._btn_mute_all.setToolTip("Mute all output devices instantly")
        layout.addWidget(self._btn_mute_all)

        layout.addStretch()
        return panel

    # ── Right panel (devices + apps) ──────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {COLOURS['bg_deep']};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {COLOURS['border']}; }}"
        )

        splitter.addWidget(self._build_devices_panel())
        splitter.addWidget(self._build_apps_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)
        return panel

    # ── Devices panel ─────────────────────────────────────────────────────────

    def _build_devices_panel(self) -> QGroupBox:
        box = QGroupBox("OUTPUT DEVICES")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(6)

        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.addStretch()

        self._btn_select_all = QPushButton("Select All")
        self._btn_select_all.setToolTip("Enable all output devices")
        ctrl_row.addWidget(self._btn_select_all)

        self._btn_select_none = QPushButton("Select None")
        self._btn_select_none.setToolTip("Disable all output devices")
        ctrl_row.addWidget(self._btn_select_none)

        self._btn_refresh_devices = QPushButton("⟳  Refresh")
        self._btn_refresh_devices.setToolTip("Re-scan for audio output devices")
        ctrl_row.addWidget(self._btn_refresh_devices)

        layout.addLayout(ctrl_row)

        # Scroll area for device cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._devices_container = QWidget()
        self._devices_layout = QVBoxLayout(self._devices_container)
        self._devices_layout.setContentsMargins(0, 0, 4, 0)
        self._devices_layout.setSpacing(6)
        self._devices_layout.addStretch()

        scroll.setWidget(self._devices_container)
        layout.addWidget(scroll)

        return box

    # ── Apps panel ────────────────────────────────────────────────────────────

    def _build_apps_panel(self) -> QGroupBox:
        box = QGroupBox("APPLICATION MIXER")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(6)

        # Controls row
        ctrl_row = QHBoxLayout()

        self._lbl_apps_info = QLabel(
            "Adjust per-application volume on this PC's audio session."
        )
        self._lbl_apps_info.setStyleSheet(
            f"color: {COLOURS['text_secondary']}; font-size: 11px;"
        )
        ctrl_row.addWidget(self._lbl_apps_info)
        ctrl_row.addStretch()

        self._btn_refresh_apps = QPushButton("⟳  Refresh")
        self._btn_refresh_apps.setToolTip("Refresh application audio sessions")
        ctrl_row.addWidget(self._btn_refresh_apps)

        layout.addLayout(ctrl_row)

        if not self._dev_mgr.available:
            warn = QLabel(
                "⚠  Application mixer requires pycaw (Windows only).\n"
                "   Run:  pip install pycaw"
            )
            warn.setStyleSheet(f"color: {COLOURS['warn']}; font-size: 11px;")
            layout.addWidget(warn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self._apps_container = QWidget()
        self._apps_layout = QVBoxLayout(self._apps_container)
        self._apps_layout.setContentsMargins(0, 0, 4, 0)
        self._apps_layout.setSpacing(4)
        self._apps_layout.addStretch()

        scroll.setWidget(self._apps_container)
        layout.addWidget(scroll)

        return box

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)

        self._sb_latency = QLabel("Latency: — ms")
        self._sb_outputs = QLabel("Active outputs: 0")
        self._sb_note = QLabel(
            "Tip: Select output devices above, choose a capture source, then click ▶ START ROUTING"
        )
        self._sb_note.setStyleSheet(f"color: {COLOURS['text_secondary']};")

        bar.addPermanentWidget(self._sb_latency)
        bar.addPermanentWidget(QLabel("  |  "))
        bar.addPermanentWidget(self._sb_outputs)
        bar.addWidget(self._sb_note)

    # ---------------------------------------------------------------- signals --

    def _connect_signals(self) -> None:
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_mute_all.toggled.connect(self._on_mute_all_toggled)
        self._sld_master.valueChanged.connect(self._on_master_volume_changed)
        self._btn_refresh_devices.clicked.connect(self._populate_devices)
        self._btn_refresh_apps.clicked.connect(self._populate_apps)
        self._btn_refresh_src.clicked.connect(self._populate_source_combo)
        self._btn_select_all.clicked.connect(self._select_all_devices)
        self._btn_select_none.clicked.connect(self._select_no_devices)

        self._router.on_routing_changed = self._on_routing_state_changed
        self._router.on_error = self._show_error

    # ---------------------------------------------------------------- timers --

    def _start_timers(self) -> None:
        self._meter_timer = QTimer(self)
        self._meter_timer.setInterval(self.METER_REFRESH_MS)
        self._meter_timer.timeout.connect(self._refresh_meters)
        self._meter_timer.start()

        self._app_timer = QTimer(self)
        self._app_timer.setInterval(self.APP_REFRESH_MS)
        self._app_timer.timeout.connect(self._populate_apps)
        self._app_timer.start()

    # ---------------------------------------------------------------- populate --

    def _populate_source_combo(self) -> None:
        self._cmb_source.blockSignals(True)
        self._cmb_source.clear()
        try:
            devices = self._router.get_output_devices()
            for d in devices:
                self._cmb_source.addItem(
                    f"{d['name']}  [{d['hostapi']}]", userData=d["id"]
                )
            # Pre-select default
            default_id = self._router.get_default_output_device_id()
            for i in range(self._cmb_source.count()):
                if self._cmb_source.itemData(i) == default_id:
                    self._cmb_source.setCurrentIndex(i)
                    break
        except Exception as exc:
            logger.error("Error populating source combo: %s", exc)
        self._cmb_source.blockSignals(False)

    def _populate_devices(self) -> None:
        """Re-scan and rebuild the device card list."""
        try:
            devices = self._router.get_output_devices()
        except Exception as exc:
            logger.error("Error fetching output devices: %s", exc)
            return

        # Remember which were enabled before refresh
        previously_enabled = {
            dev_id for dev_id, card in self._device_cards.items()
            if card.is_enabled()
        }

        # Clear existing cards
        for card in list(self._device_cards.values()):
            card.setParent(None)
            card.deleteLater()
        self._device_cards.clear()

        # Insert new cards (before the stretch)
        insert_idx = self._devices_layout.count() - 1
        for dev in devices:
            card = DeviceCard(dev, parent=self._devices_container)
            card.enabled_changed.connect(self._on_device_enabled_changed)
            card.volume_changed.connect(self._on_device_volume_changed)
            card.mute_changed.connect(self._on_device_mute_changed)

            if dev["id"] in previously_enabled:
                card.set_enabled(True)

            self._devices_layout.insertWidget(insert_idx, card)
            insert_idx += 1
            self._device_cards[dev["id"]] = card

    def _populate_apps(self) -> None:
        """Re-query audio sessions and rebuild app strips."""
        sessions = self._dev_mgr.get_sessions()

        # PIDs currently displayed
        existing_pids = set(self._app_strips.keys())
        new_pids = {s.pid for s in sessions}

        # Remove stale
        for pid in existing_pids - new_pids:
            strip = self._app_strips.pop(pid)
            strip.setParent(None)
            strip.deleteLater()

        # Add new
        insert_idx = self._apps_layout.count() - 1
        for s in sessions:
            if s.pid not in self._app_strips:
                strip = AppStrip(s, parent=self._apps_container)
                strip.volume_changed.connect(self._on_app_volume_changed)
                strip.mute_changed.connect(self._on_app_mute_changed)
                self._apps_layout.insertWidget(insert_idx, strip)
                insert_idx += 1
                self._app_strips[s.pid] = strip

        if not sessions and self._dev_mgr.available:
            # Show placeholder
            pass  # Stretch handles empty state

    # ---------------------------------------------------------------- slots --

    @pyqtSlot()
    def _on_start(self) -> None:
        enabled_ids = [
            dev_id for dev_id, card in self._device_cards.items()
            if card.is_enabled()
        ]
        if not enabled_ids:
            QMessageBox.information(
                self,
                "No Output Devices Selected",
                "Please enable at least one output device before starting routing.\n\n"
                "Tick the checkbox next to each device you want to receive audio.",
            )
            return

        source_id = self._cmb_source.currentData()
        if source_id is None:
            QMessageBox.warning(self, "No Source", "Please select a capture source device.")
            return

        # Sync router volume state before starting
        self._router.set_master_volume(self._sld_master.value() / 100.0)
        self._router.set_master_mute(self._btn_mute_all.isChecked())
        for dev_id, card in self._device_cards.items():
            self._router.set_device_volume(dev_id, card.get_volume())

        try:
            self._router.start_routing(enabled_ids, source_device_id=source_id)
        except RuntimeError as exc:
            self._show_error(str(exc))

    @pyqtSlot()
    def _on_stop(self) -> None:
        self._router.stop_routing()

    @pyqtSlot(bool)
    def _on_routing_state_changed(self, active: bool) -> None:
        """Called from the audio engine (possibly non-GUI thread)."""
        # Must update GUI from the main thread — post via QTimer
        QTimer.singleShot(0, lambda: self._apply_routing_state(active))

    def _apply_routing_state(self, active: bool) -> None:
        self._btn_start.setEnabled(not active)
        self._btn_stop.setEnabled(active)
        self._cmb_source.setEnabled(not active)

        if active:
            self._lbl_status_dot.setStyleSheet(
                f"color: {COLOURS['success']}; font-size: 14px;"
            )
            n = self._router.active_output_count
            self._lbl_status.setText(f"Routing active  ({n} output{'s' if n != 1 else ''})")
            self._lbl_status.setObjectName("lbl_status_active")
        else:
            self._lbl_status_dot.setStyleSheet(
                f"color: {COLOURS['text_secondary']}; font-size: 14px;"
            )
            self._lbl_status.setText("Idle")
            self._lbl_status.setObjectName("lbl_status_inactive")
            # Reset all meters
            self._master_vu.reset()
            for card in self._device_cards.values():
                card.reset_meter()

        self._lbl_status.style().unpolish(self._lbl_status)
        self._lbl_status.style().polish(self._lbl_status)

    @pyqtSlot(bool)
    def _on_mute_all_toggled(self, checked: bool) -> None:
        self._router.set_master_mute(checked)
        self._btn_mute_all.setText("🔇  UNMUTE ALL" if checked else "🔊  MUTE ALL")

    @pyqtSlot(int)
    def _on_master_volume_changed(self, value: int) -> None:
        self._router.set_master_volume(value / 100.0)
        self._lbl_master_vol.setText(f"{value} %")

    @pyqtSlot(int, bool)
    def _on_device_enabled_changed(self, device_id: int, enabled: bool) -> None:
        if not self._router.is_routing:
            return
        try:
            if enabled:
                self._router.add_output(device_id)
            else:
                self._router.remove_output(device_id)
                if device_id in self._device_cards:
                    self._device_cards[device_id].reset_meter()
        except Exception as exc:
            self._show_error(str(exc))

    @pyqtSlot(int, float)
    def _on_device_volume_changed(self, device_id: int, volume: float) -> None:
        self._router.set_device_volume(device_id, volume)

    @pyqtSlot(int, bool)
    def _on_device_mute_changed(self, device_id: int, muted: bool) -> None:
        self._router.set_device_mute(device_id, muted)

    @pyqtSlot(int, float)
    def _on_app_volume_changed(self, pid: int, volume: float) -> None:
        if pid in self._app_strips:
            strip = self._app_strips[pid]
            self._dev_mgr.set_session_volume(strip.session, volume)

    @pyqtSlot(int, bool)
    def _on_app_mute_changed(self, pid: int, muted: bool) -> None:
        if pid in self._app_strips:
            strip = self._app_strips[pid]
            self._dev_mgr.set_session_mute(strip.session, muted)

    # ── Convenience ──

    def _select_all_devices(self) -> None:
        for card in self._device_cards.values():
            card.set_enabled(True)

    def _select_no_devices(self) -> None:
        for card in self._device_cards.values():
            card.set_enabled(False)

    # ---------------------------------------------------------------- metering refresh --

    def _refresh_meters(self) -> None:
        """Called every METER_REFRESH_MS ms to update VU meters from engine data."""
        if self._router.is_routing:
            L, R = self._router.get_master_peak()
            self._master_vu.set_levels(L, R)

            for dev_id, card in self._device_cards.items():
                if card.is_enabled():
                    L2, R2 = self._router.get_device_peak(dev_id)
                    card.set_levels(L2, R2)

            # Update app peak meters via DeviceManager
            for pid, strip in self._app_strips.items():
                peak = self._dev_mgr.get_session_peak(strip.session)
                strip.set_peak(peak)

            # Status bar
            self._sb_latency.setText(
                f"Latency: {self._router.get_latency_ms():.0f} ms"
            )
            self._sb_outputs.setText(
                f"Active outputs: {self._router.active_output_count}"
            )

    # ---------------------------------------------------------------- helpers --

    def _show_error(self, message: str) -> None:
        """Show an error dialog (thread-safe via singleShot)."""
        QTimer.singleShot(
            0,
            lambda: QMessageBox.critical(self, "Audio Console Error", message),
        )

    # ---------------------------------------------------------------- close --

    def closeEvent(self, event) -> None:  # noqa: N802
        self._meter_timer.stop()
        self._app_timer.stop()
        self._router.stop_routing()
        self._dev_mgr.shutdown()
        event.accept()
