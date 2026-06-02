"""
ui/main_window.py
=================
Main application window for Multi-Output Audio Console.

Layout
------
┌─────────────────────────────────────────────────────────────────┐
│  Toolbar: [▶ START] [⏹ STOP] ● Status Source:▼ Profile:▼ 🌙    │
├────────────────────┬────────────────────────────────────────────┤
│  MASTER CONTROL    │  OUTPUT DEVICES   [Search] [⟳ Refresh]    │
│  ─────────────     │  ┌──────────────────────────────────────┐ │
│  VU meter          │  │  DeviceCard × N (scrollable)         │ │
│  Master vol slider │  └──────────────────────────────────────┘ │
│  [Mute All]        ├────────────────────────────────────────────┤
│                    │  APPLICATION MIXER             [⟳ Refresh] │
│                    │  ┌──────────────────────────────────────┐ │
│                    │  │  AppStrip × M (scrollable)           │ │
│                    │  └──────────────────────────────────────┘ │
│                    ├────────────────────────────────────────────┤
│                    │  ▼ LOG PANEL (collapsible)                │
└────────────────────┴────────────────────────────────────────────┘
│  Status bar: latency | active outputs | CPU | underruns   │
└─────────────────────────────────────────────────────────┘
"""

import logging
import os
import sys
import tempfile
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from audio_engine import AudioRouter
from device_manager import DeviceManager
from settings_manager import SettingsManager
from profile_manager import ProfileManager, AudioProfile
from ui.device_card import DeviceCard
from ui.app_strip import AppStrip
from ui.vu_meter import VUMeter
from ui.styles import COLOURS, COLOURS_LIGHT, STYLESHEET, STYLESHEET_LIGHT

logger = logging.getLogger(__name__)


# ── Qt log handler to feed log panel ──
class _QtLogHandler(logging.Handler):
    """Emits log records to a callback (log panel appendPlainText)."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s", "%H:%M:%S")
        )

    def emit(self, record):
        try:
            msg = self.format(record)
            self._callback(msg)
        except Exception:
            pass


class MainWindow(QMainWindow):
    """Main window of the Multi-Output Audio Console."""

    METER_REFRESH_MS = 50       # 20 Hz metering updates
    APP_REFRESH_MS = 2_000      # Refresh app list every 2 s
    DEVICE_POLL_MS = 5_000      # Check for new/removed devices every 5 s
    RECONNECT_MS = 3_000        # Retry failed devices every 3 s

    def __init__(self) -> None:
        super().__init__()
        self._router = AudioRouter()
        self._dev_mgr = DeviceManager()
        self._settings = SettingsManager()
        self._profile_mgr = ProfileManager(self._settings)

        # Current theme
        self._current_theme = self._settings.get_theme()
        self._colours = COLOURS if self._current_theme == "dark" else COLOURS_LIGHT

        # Maps device_id → DeviceCard widget
        self._device_cards: Dict[int, DeviceCard] = {}
        # Maps pid → AppStrip widget
        self._app_strips: Dict[int, AppStrip] = {}
        # Device names list for change detection
        self._known_device_names: List[str] = []

        self._setup_window()
        self._build_ui()
        self._setup_tray_icon()
        self._setup_shortcuts()
        self._connect_signals()
        self._restore_settings()
        self._populate_devices()
        self._populate_apps()
        self._start_timers()
        self._show_first_run_dialog()

    # ---------------------------------------------------------------- window setup --

    def _setup_window(self) -> None:
        self.setWindowTitle("🔊  Multi-Output Audio Console")
        self.setMinimumSize(900, 620)
        self.resize(1100, 720)
        self._apply_theme(self._current_theme)

    def _apply_theme(self, theme: str) -> None:
        self._current_theme = theme
        if theme == "light":
            self.setStyleSheet(STYLESHEET_LIGHT)
            self._colours = COLOURS_LIGHT
        else:
            self.setStyleSheet(STYLESHEET)
            self._colours = COLOURS

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
        body.setStyleSheet(f"QSplitter::handle {{ background: {self._colours['border']}; }}")
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
            f"QToolBar {{ background: {self._colours['bg_panel']}; "
            f"border-bottom: 1px solid {self._colours['border']}; "
            f"padding: 4px 8px; spacing: 8px; }}"
        )
        self.addToolBar(tb)

        # Start / Stop buttons
        self._btn_start = QPushButton("▶  START ROUTING")
        self._btn_start.setObjectName("btn_start")
        self._btn_start.setToolTip(
            "Begin routing system audio to all enabled output devices\n"
            "Shortcut: Ctrl+R"
        )
        tb.addWidget(self._btn_start)

        self._btn_stop = QPushButton("⏹  STOP")
        self._btn_stop.setObjectName("btn_stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.setToolTip("Stop all audio routing\nShortcut: Ctrl+R")
        tb.addWidget(self._btn_stop)

        self._btn_record = QPushButton("⏺  RECORD")
        self._btn_record.setObjectName("btn_record")
        self._btn_record.setToolTip(
            "Record all sound card audio to an M4A file\n"
            "Requires ffmpeg installed for M4A encoding (falls back to WAV)"
        )
        tb.addWidget(self._btn_record)

        tb.addSeparator()

        # Status indicator
        self._lbl_status_dot = QLabel("⬤")
        self._lbl_status_dot.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 14px;")
        tb.addWidget(self._lbl_status_dot)

        self._lbl_status = QLabel("Idle")
        self._lbl_status.setObjectName("lbl_status_inactive")
        self._lbl_status.setMinimumWidth(120)
        tb.addWidget(self._lbl_status)

        tb.addSeparator()

        # Source device selector
        lbl_src = QLabel("  Capture Source:")
        lbl_src.setStyleSheet(f"color: {self._colours['text_secondary']};")
        tb.addWidget(lbl_src)

        self._cmb_source = QComboBox()
        self._cmb_source.setToolTip(
            "The audio output device whose playback will be captured and routed.\n"
            "Normally this should be your current default speakers / headphones."
        )
        self._cmb_source.setMinimumWidth(240)
        tb.addWidget(self._cmb_source)

        self._btn_refresh_src = QPushButton("⟳")
        self._btn_refresh_src.setToolTip("Refresh source device list")
        self._btn_refresh_src.setFixedWidth(32)
        tb.addWidget(self._btn_refresh_src)

        tb.addSeparator()

        # Profile selector
        lbl_profile = QLabel("  Profile:")
        lbl_profile.setStyleSheet(f"color: {self._colours['text_secondary']};")
        tb.addWidget(lbl_profile)

        self._cmb_profile = QComboBox()
        self._cmb_profile.setToolTip(
            "Load a saved audio profile to restore device selections,\n"
            "volumes, and settings in one click."
        )
        self._cmb_profile.setMinimumWidth(150)
        self._cmb_profile.addItem("— No Profile —")
        tb.addWidget(self._cmb_profile)

        self._btn_save_profile = QPushButton("💾 Save")
        self._btn_save_profile.setToolTip("Save current configuration as a named profile")
        tb.addWidget(self._btn_save_profile)

        self._btn_delete_profile = QPushButton("🗑")
        self._btn_delete_profile.setToolTip("Delete the selected profile")
        self._btn_delete_profile.setFixedWidth(32)
        tb.addWidget(self._btn_delete_profile)

        tb.addSeparator()

        # Theme toggle
        self._btn_theme = QPushButton("🌙" if self._current_theme == "dark" else "☀️")
        self._btn_theme.setToolTip("Toggle dark / light theme")
        self._btn_theme.setFixedWidth(32)
        tb.addWidget(self._btn_theme)

        # Auto-start checkbox
        self._chk_auto_start = QCheckBox("Auto-start")
        self._chk_auto_start.setToolTip(
            "Automatically start routing with the last-used configuration\n"
            "when the application launches."
        )
        tb.addWidget(self._chk_auto_start)

        self._populate_source_combo()
        self._refresh_profile_combo()

    # ── Master panel (left) ───────────────────────────────────────────────────

    def _build_master_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(220)
        panel.setStyleSheet(
            f"background-color: {self._colours['bg_panel']}; "
            f"border-right: 1px solid {self._colours['border']};"
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
        for label_text in ("0 dB", "-6 dB", "-12 dB", "-24 dB", "-∞ dB"):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {self._colours['text_secondary']}; font-size: 9px;"
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
        self._sld_master.setToolTip(
            "Master volume — applied to all outputs\n"
            "Shortcuts: Ctrl+Up / Ctrl+Down"
        )
        layout.addWidget(self._sld_master, alignment=Qt.AlignHCenter)

        self._lbl_master_vol = QLabel("100 %")
        self._lbl_master_vol.setAlignment(Qt.AlignHCenter)
        self._lbl_master_vol.setStyleSheet(
            f"color: {self._colours['accent']}; font-size: 18px; font-weight: 700;"
        )
        layout.addWidget(self._lbl_master_vol)

        # Mute All button
        self._btn_mute_all = QPushButton("🔊  MUTE ALL")
        self._btn_mute_all.setCheckable(True)
        self._btn_mute_all.setToolTip("Mute all output devices instantly\nShortcut: Ctrl+M")
        layout.addWidget(self._btn_mute_all)

        layout.addStretch()
        return panel

    # ── Right panel (devices + apps + log) ────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {self._colours['bg_deep']};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {self._colours['border']}; }}"
        )

        splitter.addWidget(self._build_devices_panel())
        splitter.addWidget(self._build_apps_panel())
        splitter.addWidget(self._build_log_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([400, 200, 100])

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

        # Search / filter
        self._txt_search = QLineEdit()
        self._txt_search.setPlaceholderText("🔍  Search devices…")
        self._txt_search.setFixedWidth(200)
        self._txt_search.setToolTip(
            "Filter devices by name or API type.\n"
            "Start typing to narrow the list."
        )
        ctrl_row.addWidget(self._txt_search)

        ctrl_row.addStretch()

        self._btn_select_all = QPushButton("Select All")
        self._btn_select_all.setToolTip("Enable all output devices for routing")
        ctrl_row.addWidget(self._btn_select_all)

        self._btn_select_none = QPushButton("Select None")
        self._btn_select_none.setToolTip("Disable all output devices")
        ctrl_row.addWidget(self._btn_select_none)

        self._chk_auto_sync = QCheckBox("Auto-Sync Delay")
        self._chk_auto_sync.setToolTip(
            "Automatically delay faster devices to match the slowest one,\n"
            "keeping all outputs in sync. Manually adjusting a device's\n"
            "delay slider will override auto-sync for that device."
        )
        self._chk_auto_sync.setChecked(True)  # default on; restored later
        ctrl_row.addWidget(self._chk_auto_sync)

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
            f"color: {self._colours['text_secondary']}; font-size: 11px;"
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
            warn.setStyleSheet(f"color: {self._colours['warn']}; font-size: 11px;")
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

    # ── Log panel ─────────────────────────────────────────────────────────────

    def _build_log_panel(self) -> QGroupBox:
        box = QGroupBox("DIAGNOSTICS LOG")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 16, 8, 4)
        layout.setSpacing(4)

        self._log_text = QPlainTextEdit()
        self._log_text.setObjectName("log_panel")
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumBlockCount(500)
        self._log_text.setPlaceholderText("Engine and device log messages will appear here…")
        layout.addWidget(self._log_text)

        # Install log handler
        self._log_handler = _QtLogHandler(self._append_log)
        self._log_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(self._log_handler)

        return box

    def _append_log(self, message: str) -> None:
        """Thread-safe log append."""
        QTimer.singleShot(0, lambda: self._log_text.appendPlainText(message))

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)

        self._sb_latency = QLabel("Latency: — ms")
        self._sb_outputs = QLabel("Active outputs: 0")
        self._sb_cpu = QLabel("CB: — ms")
        self._sb_underruns = QLabel("Underruns: 0")
        self._sb_note = QLabel(
            "Tip: Select output devices above, choose a capture source, then click ▶ START ROUTING"
        )
        self._sb_note.setStyleSheet(f"color: {self._colours['text_secondary']};")

        bar.addPermanentWidget(self._sb_latency)
        bar.addPermanentWidget(QLabel("  |  "))
        bar.addPermanentWidget(self._sb_outputs)
        bar.addPermanentWidget(QLabel("  |  "))
        bar.addPermanentWidget(self._sb_cpu)
        bar.addPermanentWidget(QLabel("  |  "))
        bar.addPermanentWidget(self._sb_underruns)
        bar.addWidget(self._sb_note)

    # ── System tray ──────────────────────────────────────────────────────────

    def _setup_tray_icon(self) -> None:
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.setToolTip("Multi-Output Audio Console")

        # Use the app icon or a default
        icon = self.windowIcon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(
                QApplication.style().SP_MediaVolume
            )
        self._tray_icon.setIcon(icon)

        # Tray context menu
        tray_menu = QMenu()
        self._tray_action_show = tray_menu.addAction("Show Window")
        self._tray_action_show.triggered.connect(self._show_from_tray)

        tray_menu.addSeparator()

        self._tray_action_start = tray_menu.addAction("▶ Start Routing")
        self._tray_action_start.triggered.connect(self._on_start)

        self._tray_action_stop = tray_menu.addAction("⏹ Stop Routing")
        self._tray_action_stop.triggered.connect(self._on_stop)
        self._tray_action_stop.setEnabled(False)

        tray_menu.addSeparator()

        self._tray_action_mute = tray_menu.addAction("🔊 Mute All")
        self._tray_action_mute.setCheckable(True)
        self._tray_action_mute.triggered.connect(self._on_tray_mute_toggled)

        tray_menu.addSeparator()

        tray_action_quit = tray_menu.addAction("Quit")
        tray_action_quit.triggered.connect(self._quit_app)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_from_tray()

    def _on_tray_mute_toggled(self, checked: bool) -> None:
        self._btn_mute_all.setChecked(checked)

    def _quit_app(self) -> None:
        self._save_settings()
        self._tray_icon.hide()
        QApplication.quit()

    # ── Keyboard shortcuts ───────────────────────────────────────────────────

    def _setup_shortcuts(self) -> None:
        # Ctrl+R — toggle routing
        sc_route = QShortcut(QKeySequence("Ctrl+R"), self)
        sc_route.activated.connect(self._toggle_routing)

        # Ctrl+M — toggle mute all
        sc_mute = QShortcut(QKeySequence("Ctrl+M"), self)
        sc_mute.activated.connect(lambda: self._btn_mute_all.toggle())

        # Ctrl+Up — master volume up
        sc_vol_up = QShortcut(QKeySequence("Ctrl+Up"), self)
        sc_vol_up.activated.connect(lambda: self._sld_master.setValue(
            min(100, self._sld_master.value() + 5)
        ))

        # Ctrl+Down — master volume down
        sc_vol_down = QShortcut(QKeySequence("Ctrl+Down"), self)
        sc_vol_down.activated.connect(lambda: self._sld_master.setValue(
            max(0, self._sld_master.value() - 5)
        ))

        # Ctrl+S — save profile
        sc_save = QShortcut(QKeySequence("Ctrl+S"), self)
        sc_save.activated.connect(self._on_save_profile)

        # Ctrl+T — toggle theme
        sc_theme = QShortcut(QKeySequence("Ctrl+T"), self)
        sc_theme.activated.connect(self._toggle_theme)

    def _toggle_routing(self) -> None:
        if self._router.is_routing:
            self._on_stop()
        else:
            self._on_start()

    # ---------------------------------------------------------------- signals --

    def _connect_signals(self) -> None:
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_record.clicked.connect(self._on_record_toggle)
        self._btn_mute_all.toggled.connect(self._on_mute_all_toggled)
        self._sld_master.valueChanged.connect(self._on_master_volume_changed)
        self._btn_refresh_devices.clicked.connect(self._populate_devices)
        self._btn_refresh_apps.clicked.connect(self._populate_apps)
        self._btn_refresh_src.clicked.connect(self._populate_source_combo)
        self._btn_select_all.clicked.connect(self._select_all_devices)
        self._btn_select_none.clicked.connect(self._select_no_devices)
        self._btn_theme.clicked.connect(self._toggle_theme)
        self._chk_auto_start.toggled.connect(
            lambda v: self._settings.save_auto_start(v)
        )
        self._chk_auto_sync.toggled.connect(self._on_auto_sync_toggled)

        # Profiles
        self._btn_save_profile.clicked.connect(self._on_save_profile)
        self._btn_delete_profile.clicked.connect(self._on_delete_profile)
        self._cmb_profile.currentIndexChanged.connect(self._on_profile_selected)

        # Search / filter
        self._txt_search.textChanged.connect(self._filter_devices)

        # Router callbacks
        self._router.on_routing_changed = self._on_routing_state_changed
        self._router.on_error = self._show_error
        self._router.on_device_error = self._on_device_error
        self._router.on_device_recovered = self._on_device_recovered
        self._router.on_recording_changed = self._on_recording_state_changed

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

        # Device connection polling
        self._device_poll_timer = QTimer(self)
        self._device_poll_timer.setInterval(self.DEVICE_POLL_MS)
        self._device_poll_timer.timeout.connect(self._check_device_changes)
        self._device_poll_timer.start()

        # Reconnect timer for failed devices
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(self.RECONNECT_MS)
        self._reconnect_timer.timeout.connect(self._attempt_reconnects)
        self._reconnect_timer.start()

    # ---------------------------------------------------------------- settings --

    def _save_settings(self) -> None:
        """Persist current state."""
        self._settings.save_geometry(self.saveGeometry(), self.saveState())
        self._settings.save_master_volume(self._sld_master.value() / 100.0)
        self._settings.save_master_muted(self._btn_mute_all.isChecked())
        self._settings.save_theme(self._current_theme)

        # Source device name
        idx = self._cmb_source.currentIndex()
        if idx >= 0:
            self._settings.save_source_device(self._cmb_source.currentText())

        # Enabled device names & volumes & delays
        enabled_names = []
        vol_map = {}
        delay_map = {}
        for dev_id, card in self._device_cards.items():
            name = card._device_name
            if card.is_enabled():
                enabled_names.append(name)
            vol_map[name] = card.get_volume()
            delay_map[name] = card.get_delay()
        self._settings.save_enabled_devices(enabled_names)
        self._settings.save_device_volumes(vol_map)
        self._settings.save_device_delays(delay_map)
        self._settings.save_auto_sync_delay(self._chk_auto_sync.isChecked())

    def _restore_settings(self) -> None:
        """Restore persisted state."""
        # Window geometry
        geom = self._settings.restore_geometry()
        if geom:
            self.restoreGeometry(geom)
        state = self._settings.restore_state()
        if state:
            self.restoreState(state)

        # Master volume
        vol = self._settings.get_master_volume()
        self._sld_master.setValue(int(vol * 100))

        muted = self._settings.get_master_muted()
        if muted:
            self._btn_mute_all.setChecked(True)

        # Auto-start
        self._chk_auto_start.setChecked(self._settings.get_auto_start())

        # Restore source combo selection
        saved_src = self._settings.get_source_device()
        if saved_src:
            for i in range(self._cmb_source.count()):
                if self._cmb_source.itemText(i) == saved_src:
                    self._cmb_source.setCurrentIndex(i)
                    break

        # Restore device selections, volumes, delays
        enabled_names = self._settings.get_enabled_devices()
        saved_volumes = self._settings.get_device_volumes()
        saved_delays = self._settings.get_device_delays()
        for dev_id, card in self._device_cards.items():
            name = card._device_name
            if name in enabled_names:
                card.set_enabled(True)
            if name in saved_volumes:
                card.set_volume(saved_volumes[name])
            if name in saved_delays:
                card.set_delay(saved_delays[name])

        # Restore auto-sync delay setting
        self._chk_auto_sync.setChecked(self._settings.get_auto_sync_delay())

        # Auto-start routing if enabled
        if self._settings.get_auto_start():
            QTimer.singleShot(500, self._on_start)

    # ---------------------------------------------------------------- first run --

    def _show_first_run_dialog(self) -> None:
        if not self._settings.is_first_run():
            return

        QMessageBox.information(
            self,
            "Welcome to Multi-Output Audio Console! 🔊",
            "<h3>Quick Start Guide</h3>"
            "<ol>"
            "<li><b>Select Output Devices</b> — tick the checkbox next to each "
            "audio device you want to receive sound.</li>"
            "<li><b>Choose Capture Source</b> — in the toolbar, pick the device "
            "whose audio should be captured (usually your default speakers).</li>"
            "<li><b>Start Routing</b> — click <b>▶ START ROUTING</b>.</li>"
            "</ol>"
            "<p><b>Keyboard shortcuts:</b></p>"
            "<ul>"
            "<li><b>Ctrl+R</b> — Start / Stop routing</li>"
            "<li><b>Ctrl+M</b> — Mute / Unmute all</li>"
            "<li><b>Ctrl+↑/↓</b> — Master volume up / down</li>"
            "<li><b>Ctrl+S</b> — Save profile</li>"
            "<li><b>Ctrl+T</b> — Toggle dark / light theme</li>"
            "</ul>"
            "<p>The app minimises to the system tray when you close the window.</p>",
        )
        self._settings.mark_first_run_done()

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
        prev_volumes = {
            card._device_name: card.get_volume()
            for card in self._device_cards.values()
        }
        prev_delays = {
            card._device_name: card.get_delay()
            for card in self._device_cards.values()
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
            card.delay_changed.connect(self._on_device_delay_changed)

            if dev["id"] in previously_enabled:
                card.set_enabled(True)

            # Restore volume / delay from previous session
            if dev["name"] in prev_volumes:
                card.set_volume(prev_volumes[dev["name"]])
            if dev["name"] in prev_delays:
                card.set_delay(prev_delays[dev["name"]])

            self._devices_layout.insertWidget(insert_idx, card)
            insert_idx += 1
            self._device_cards[dev["id"]] = card

        self._known_device_names = [d["name"] for d in devices]

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
            pass  # Stretch handles empty state

    # ── Profile management ───────────────────────────────────────────────────

    def _refresh_profile_combo(self) -> None:
        self._cmb_profile.blockSignals(True)
        self._cmb_profile.clear()
        self._cmb_profile.addItem("— No Profile —")
        for name in self._profile_mgr.list_profiles():
            self._cmb_profile.addItem(name)
        self._cmb_profile.blockSignals(False)

    def _on_save_profile(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Save Profile", "Profile name:",
            text=self._cmb_profile.currentText()
            if self._cmb_profile.currentIndex() > 0
            else "",
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        # Capture current state
        enabled_names = [
            card._device_name
            for card in self._device_cards.values()
            if card.is_enabled()
        ]
        vol_map = {
            card._device_name: card.get_volume()
            for card in self._device_cards.values()
        }
        delay_map = {
            card._device_name: card.get_delay()
            for card in self._device_cards.values()
        }
        src_text = self._cmb_source.currentText() if self._cmb_source.currentIndex() >= 0 else None

        profile = AudioProfile(
            name=name,
            enabled_devices=enabled_names,
            device_volumes=vol_map,
            device_delays=delay_map,
            master_volume=self._sld_master.value() / 100.0,
            master_muted=self._btn_mute_all.isChecked(),
            source_device=src_text,
        )
        self._profile_mgr.save_profile(profile)
        self._refresh_profile_combo()

        # Select the saved profile
        for i in range(self._cmb_profile.count()):
            if self._cmb_profile.itemText(i) == name:
                self._cmb_profile.blockSignals(True)
                self._cmb_profile.setCurrentIndex(i)
                self._cmb_profile.blockSignals(False)
                break

        self.statusBar().showMessage(f"Profile '{name}' saved.", 3000)

    def _on_delete_profile(self) -> None:
        idx = self._cmb_profile.currentIndex()
        if idx <= 0:
            return
        name = self._cmb_profile.currentText()
        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._profile_mgr.delete_profile(name)
            self._refresh_profile_combo()

    def _on_profile_selected(self, index: int) -> None:
        if index <= 0:
            return
        name = self._cmb_profile.currentText()
        profile = self._profile_mgr.get_profile(name)
        if not profile:
            return

        # Apply profile
        was_routing = self._router.is_routing
        if was_routing:
            self._router.stop_routing()

        self._sld_master.setValue(int(profile.master_volume * 100))
        if profile.master_muted:
            self._btn_mute_all.setChecked(True)
        else:
            self._btn_mute_all.setChecked(False)

        # Select source
        if profile.source_device:
            for i in range(self._cmb_source.count()):
                if self._cmb_source.itemText(i) == profile.source_device:
                    self._cmb_source.setCurrentIndex(i)
                    break

        # Enable devices
        for card in self._device_cards.values():
            name_match = card._device_name in profile.enabled_devices
            card.set_enabled(name_match)
            if card._device_name in profile.device_volumes:
                card.set_volume(profile.device_volumes[card._device_name])
            if card._device_name in profile.device_delays:
                card.set_delay(profile.device_delays[card._device_name])

        self.statusBar().showMessage(f"Profile '{name}' loaded.", 3000)

    # ── Device search / filter ───────────────────────────────────────────────

    def _filter_devices(self, text: str) -> None:
        text_lower = text.lower()
        for card in self._device_cards.values():
            match = (
                not text_lower
                or text_lower in card._device_name.lower()
                or text_lower in card._hostapi.lower()
            )
            card.setVisible(match)

    # ── Theme toggle ─────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self._apply_theme(new_theme)
        self._btn_theme.setText("🌙" if new_theme == "dark" else "☀️")
        self._settings.save_theme(new_theme)

    # ── Device change detection ──────────────────────────────────────────────

    def _check_device_changes(self) -> None:
        """Poll for device list changes and auto-refresh."""
        try:
            devices = self._router.get_output_devices()
            new_names = [d["name"] for d in devices]
            if new_names != self._known_device_names:
                added = set(new_names) - set(self._known_device_names)
                removed = set(self._known_device_names) - set(new_names)

                if added:
                    logger.info("New audio devices detected: %s", ", ".join(added))
                    self._tray_icon.showMessage(
                        "Audio Device Connected",
                        f"New device(s): {', '.join(added)}",
                        QSystemTrayIcon.Information,
                        3000,
                    )
                if removed:
                    logger.info("Audio devices removed: %s", ", ".join(removed))
                    self._tray_icon.showMessage(
                        "Audio Device Disconnected",
                        f"Removed: {', '.join(removed)}",
                        QSystemTrayIcon.Warning,
                        3000,
                    )

                self._populate_devices()
                self._populate_source_combo()
        except Exception as exc:
            logger.debug("Device poll error: %s", exc)

    # ── Error recovery / reconnect ───────────────────────────────────────────

    def _on_device_error(self, device_id: int, error_msg: str) -> None:
        """Called when a device stream fails during routing."""
        QTimer.singleShot(0, lambda: self._handle_device_error_ui(device_id, error_msg))

    def _handle_device_error_ui(self, device_id: int, error_msg: str) -> None:
        if device_id in self._device_cards:
            card = self._device_cards[device_id]
            card.reset_meter()
        logger.warning("Device %d error: %s (will attempt reconnect)", device_id, error_msg)
        self._tray_icon.showMessage(
            "Audio Device Error",
            f"Device {device_id} failed — will retry automatically.",
            QSystemTrayIcon.Warning,
            3000,
        )

    def _on_device_recovered(self, device_id: int) -> None:
        QTimer.singleShot(0, lambda: self._handle_device_recovered_ui(device_id))

    def _handle_device_recovered_ui(self, device_id: int) -> None:
        logger.info("Device %d reconnected successfully", device_id)
        self._tray_icon.showMessage(
            "Audio Device Recovered",
            f"Device {device_id} is back online.",
            QSystemTrayIcon.Information,
            2000,
        )

    def _attempt_reconnects(self) -> None:
        """Periodically try to reconnect failed devices."""
        if not self._router.is_routing:
            return
        for dev_id in list(self._router.failed_device_ids):
            self._router.try_reconnect_device(dev_id)

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

        # Sync router volume/delay state before starting
        self._router.set_master_volume(self._sld_master.value() / 100.0)
        self._router.set_master_mute(self._btn_mute_all.isChecked())
        for dev_id, card in self._device_cards.items():
            self._router.set_device_volume(dev_id, card.get_volume())
            self._router.set_device_delay(dev_id, card.get_delay())

        # Apply auto-sync delays for enabled devices (before routing starts)
        if self._chk_auto_sync.isChecked():
            self._apply_auto_sync_delays(enabled_ids)

        try:
            self._router.start_routing(enabled_ids, source_device_id=source_id)
        except RuntimeError as exc:
            self._show_error(str(exc))

    @pyqtSlot()
    def _on_stop(self) -> None:
        # Stop any active recording first
        if self._router.is_recording:
            self._finish_recording()
        self._router.stop_routing()

    # ── Recording ────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_record_toggle(self) -> None:
        """Toggle recording on/off."""
        if self._router.is_recording:
            self._finish_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        """Start recording system audio."""
        # If not routing, we need a source device for standalone capture
        if not self._router.is_routing:
            source_id = self._cmb_source.currentData()
            if source_id is not None:
                self._router._source_device_id = source_id

        self._router.start_recording()

    def _finish_recording(self) -> None:
        """Stop recording and prompt user for save location."""
        if not self._router.is_recording:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Recording",
            "recording.m4a",
            "M4A Audio (*.m4a);;All Files (*)",
        )

        if not path:
            # User cancelled — still stop recording but discard
            self._router.stop_recording(os.path.join(tempfile.gettempdir(), "_discard.m4a"))
            logger.info("Recording discarded (user cancelled save)")
            return

        # Run conversion in a thread to avoid blocking the UI
        import threading as _threading

        def _save():
            result = self._router.stop_recording(path)
            if result:
                QTimer.singleShot(0, lambda: self.statusBar().showMessage(
                    f"Recording saved: {result}", 5000
                ))
            else:
                QTimer.singleShot(0, lambda: self._show_error(
                    "Failed to save recording. Check the log for details."
                ))

        _threading.Thread(target=_save, daemon=True, name="RecordSave").start()

    def _on_recording_state_changed(self, active: bool) -> None:
        """Called from the audio engine (possibly non-GUI thread)."""
        QTimer.singleShot(0, lambda: self._apply_recording_state(active))

    def _apply_recording_state(self, active: bool) -> None:
        if active:
            self._btn_record.setText("⏹  STOP REC")
            self._btn_record.setStyleSheet(
                f"QPushButton {{ background: {self._colours.get('danger', '#e74c3c')}; "
                f"color: white; font-weight: bold; }}"
            )
            self.statusBar().showMessage("⏺ Recording…")
            self._recording_elapsed = 0
            self._recording_timer = QTimer(self)
            self._recording_timer.setInterval(1000)
            self._recording_timer.timeout.connect(self._update_recording_time)
            self._recording_timer.start()
        else:
            self._btn_record.setText("⏺  RECORD")
            self._btn_record.setStyleSheet("")
            if hasattr(self, "_recording_timer"):
                self._recording_timer.stop()

    def _update_recording_time(self) -> None:
        if not self._router.is_recording:
            return
        self._recording_elapsed += 1
        mins, secs = divmod(self._recording_elapsed, 60)
        self.statusBar().showMessage(f"⏺ Recording… {mins:02d}:{secs:02d}")

    @pyqtSlot(bool)
    def _on_routing_state_changed(self, active: bool) -> None:
        """Called from the audio engine (possibly non-GUI thread)."""
        QTimer.singleShot(0, lambda: self._apply_routing_state(active))

    def _apply_routing_state(self, active: bool) -> None:
        self._btn_start.setEnabled(not active)
        self._btn_stop.setEnabled(active)
        self._cmb_source.setEnabled(not active)

        # Tray menu sync
        self._tray_action_start.setEnabled(not active)
        self._tray_action_stop.setEnabled(active)

        if active:
            self._lbl_status_dot.setStyleSheet(
                f"color: {self._colours['success']}; font-size: 14px;"
            )
            n = self._router.active_output_count
            self._lbl_status.setText(f"Routing active ({n} output{'s' if n != 1 else ''})")
            self._lbl_status.setObjectName("lbl_status_active")
        else:
            self._lbl_status_dot.setStyleSheet(
                f"color: {self._colours['text_secondary']}; font-size: 14px;"
            )
            self._lbl_status.setText("Idle")
            self._lbl_status.setObjectName("lbl_status_inactive")
            self._master_vu.reset()
            for card in self._device_cards.values():
                card.reset_meter()

        self._lbl_status.style().unpolish(self._lbl_status)
        self._lbl_status.style().polish(self._lbl_status)

    @pyqtSlot(bool)
    def _on_mute_all_toggled(self, checked: bool) -> None:
        self._router.set_master_mute(checked)
        self._btn_mute_all.setText("🔇  UNMUTE ALL" if checked else "🔊  MUTE ALL")
        self._tray_action_mute.setChecked(checked)
        self._tray_action_mute.setText("🔇 Unmute All" if checked else "🔊 Mute All")

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
            # Re-compute auto-sync when device set changes
            if self._chk_auto_sync.isChecked():
                active_ids = [
                    did for did, c in self._device_cards.items() if c.is_enabled()
                ]
                self._apply_auto_sync_delays(active_ids)
        except Exception as exc:
            self._show_error(str(exc))

    @pyqtSlot(int, float)
    def _on_device_volume_changed(self, device_id: int, volume: float) -> None:
        self._router.set_device_volume(device_id, volume)

    @pyqtSlot(int, bool)
    def _on_device_mute_changed(self, device_id: int, muted: bool) -> None:
        self._router.set_device_mute(device_id, muted)

    @pyqtSlot(int, float)
    def _on_device_delay_changed(self, device_id: int, delay_ms: float) -> None:
        self._router.set_device_delay(device_id, delay_ms)

    def _on_auto_sync_toggled(self, checked: bool) -> None:
        """Handle auto-sync checkbox toggle."""
        self._settings.save_auto_sync_delay(checked)
        if checked:
            # Clear manual overrides and re-apply auto-sync
            for card in self._device_cards.values():
                card.clear_manual_delay()
            enabled_ids = [
                dev_id
                for dev_id, card in self._device_cards.items()
                if card.is_enabled()
            ]
            if enabled_ids:
                self._apply_auto_sync_delays(enabled_ids)

    def _apply_auto_sync_delays(self, device_ids: List[int]) -> None:
        """
        Compute auto-sync delays and apply them to devices that have not been
        manually overridden.
        """
        offsets = self._router.compute_auto_sync_delays(device_ids)
        for dev_id, offset_ms in offsets.items():
            card = self._device_cards.get(dev_id)
            if card and not card.delay_manually_set:
                card.set_delay_auto(offset_ms)
                self._router.set_device_delay(dev_id, offset_ms)

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
            self._sb_cpu.setText(
                f"CB: {self._router.get_avg_cb_duration_ms():.2f} ms"
            )
            self._sb_underruns.setText(
                f"Underruns: {self._router.get_buffer_underruns()}"
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
        """Minimise to tray instead of quitting (unless user chose Quit)."""
        if self._settings.get_minimize_to_tray() and self._tray_icon.isVisible():
            self._save_settings()
            self.hide()
            self._tray_icon.showMessage(
                "Multi-Output Audio Console",
                "Application minimised to tray. Double-click the icon to restore.",
                QSystemTrayIcon.Information,
                2000,
            )
            event.ignore()
        else:
            self._save_settings()
            self._meter_timer.stop()
            self._app_timer.stop()
            self._device_poll_timer.stop()
            self._reconnect_timer.stop()
            self._router.stop_routing()
            self._dev_mgr.shutdown()
            self._tray_icon.hide()
            # Remove our log handler to prevent errors during shutdown
            logging.getLogger().removeHandler(self._log_handler)
            event.accept()
