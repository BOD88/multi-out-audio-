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
import json
import os
import sys
import tempfile
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, QMimeData, pyqtSlot
from PyQt5.QtGui import QIcon, QKeySequence, QDesktopServices
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
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
    QSpinBox,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
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
from ui.transcription_widget import TranscriptionWidget

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

        # Mini window reference
        self._mini_window = None

        # Hotkey manager
        self._hotkey_mgr = None

        # Waveform widget reference
        self._waveform_widget = None

        # Ducking state
        self._ducking_active = False
        self._ducking_original_volume: Optional[float] = None

        self._setup_window()
        self._build_ui()
        self._setup_tray_icon()
        self._setup_shortcuts()
        self._connect_signals()
        self._restore_settings()
        self._populate_devices()
        self._populate_apps()
        self._start_timers()
        self._setup_hotkeys()
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

        # Timed recording controls
        self._spn_rec_minutes = QSpinBox()
        self._spn_rec_minutes.setRange(0, 999)
        self._spn_rec_minutes.setValue(0)
        self._spn_rec_minutes.setSuffix(" min")
        self._spn_rec_minutes.setToolTip("Timed recording duration (0 = unlimited)")
        self._spn_rec_minutes.setFixedWidth(80)
        tb.addWidget(self._spn_rec_minutes)

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

        self._btn_export_profile = QPushButton("📤")
        self._btn_export_profile.setToolTip("Export all profiles to a JSON file")
        self._btn_export_profile.setFixedWidth(32)
        tb.addWidget(self._btn_export_profile)

        self._btn_import_profile = QPushButton("📥")
        self._btn_import_profile.setToolTip("Import profiles from a JSON file")
        self._btn_import_profile.setFixedWidth(32)
        tb.addWidget(self._btn_import_profile)

        tb.addSeparator()

        # Theme toggle
        self._btn_theme = QPushButton("🌙" if self._current_theme == "dark" else "☀️")
        self._btn_theme.setToolTip("Toggle dark / light theme")
        self._btn_theme.setFixedWidth(32)
        tb.addWidget(self._btn_theme)

        # Mini mode button
        self._btn_mini = QPushButton("🔲")
        self._btn_mini.setToolTip("Switch to compact mini-mode window")
        self._btn_mini.setFixedWidth(32)
        tb.addWidget(self._btn_mini)

        # Auto-start checkbox
        self._chk_auto_start = QCheckBox("Auto-start")
        self._chk_auto_start.setToolTip(
            "Automatically start routing with the last-used configuration\n"
            "when the application launches."
        )
        tb.addWidget(self._chk_auto_start)

        # Notification sounds checkbox
        self._chk_notifications = QCheckBox("🔔")
        self._chk_notifications.setToolTip("Enable notification sounds for events")
        self._chk_notifications.setChecked(True)
        tb.addWidget(self._chk_notifications)

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

        # ── Limiter toggle ──
        limiter_frame = QFrame()
        limiter_lay = QVBoxLayout(limiter_frame)
        limiter_lay.setContentsMargins(0, 8, 0, 0)
        limiter_lay.setSpacing(4)

        lbl_limiter = QLabel("LIMITER")
        lbl_limiter.setObjectName("lbl_section")
        limiter_lay.addWidget(lbl_limiter, alignment=Qt.AlignHCenter)

        self._chk_limiter = QCheckBox("Enable Limiter")
        self._chk_limiter.setToolTip(
            "Soft-clip audio peaks to prevent clipping distortion"
        )
        limiter_lay.addWidget(self._chk_limiter)

        thresh_row = QHBoxLayout()
        thresh_lbl = QLabel("Threshold:")
        thresh_lbl.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 10px;")
        thresh_row.addWidget(thresh_lbl)
        self._sld_limiter_thresh = QSlider(Qt.Horizontal)
        self._sld_limiter_thresh.setRange(50, 100)
        self._sld_limiter_thresh.setValue(95)
        self._sld_limiter_thresh.setToolTip("Limiter threshold (50%–100%)")
        thresh_row.addWidget(self._sld_limiter_thresh)
        self._lbl_limiter_thresh = QLabel("95%")
        self._lbl_limiter_thresh.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 10px;")
        thresh_row.addWidget(self._lbl_limiter_thresh)
        limiter_lay.addLayout(thresh_row)

        layout.addWidget(limiter_frame)

        # ── Audio Format ──
        format_frame = QFrame()
        format_lay = QVBoxLayout(format_frame)
        format_lay.setContentsMargins(0, 8, 0, 0)
        format_lay.setSpacing(4)

        lbl_format = QLabel("FORMAT")
        lbl_format.setObjectName("lbl_section")
        format_lay.addWidget(lbl_format, alignment=Qt.AlignHCenter)

        sr_row = QHBoxLayout()
        sr_lbl = QLabel("Sample Rate:")
        sr_lbl.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 10px;")
        sr_row.addWidget(sr_lbl)
        self._cmb_sample_rate = QComboBox()
        self._cmb_sample_rate.addItems(["44100 Hz", "48000 Hz", "96000 Hz"])
        self._cmb_sample_rate.setCurrentIndex(1)  # 48000 default
        self._cmb_sample_rate.setToolTip("Audio sample rate (takes effect on next routing start)")
        sr_row.addWidget(self._cmb_sample_rate)
        format_lay.addLayout(sr_row)

        layout.addWidget(format_frame)

        # ── Auto-Start with Windows ──
        self._chk_auto_start_win = QCheckBox("Start with Windows")
        self._chk_auto_start_win.setToolTip(
            "Launch Multi-Output Audio Console automatically when you log in to Windows"
        )
        layout.addWidget(self._chk_auto_start_win)

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

        # Tabbed lower panel for Apps, EQ, Waveform, Ducking, Groups, Diagnostics
        self._lower_tabs = QTabWidget()
        self._lower_tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {self._colours['border']}; "
            f"border-radius: 4px; background: {self._colours['bg_deep']}; }}"
            f"QTabBar::tab {{ background: {self._colours['bg_card']}; "
            f"color: {self._colours['text_secondary']}; "
            f"border: 1px solid {self._colours['border']}; "
            f"padding: 4px 10px; margin-right: 2px; border-radius: 4px 4px 0 0; }}"
            f"QTabBar::tab:selected {{ background: {self._colours['bg_deep']}; "
            f"color: {self._colours['accent']}; border-bottom: none; }}"
        )
        self._lower_tabs.addTab(self._build_apps_panel(), "🎵 Apps")
        self._lower_tabs.addTab(self._build_eq_panel(), "🎛 EQ")
        self._lower_tabs.addTab(self._build_waveform_panel(), "〰 Waveform")
        self._lower_tabs.addTab(self._build_ducking_panel(), "🔉 Ducking")
        self._lower_tabs.addTab(self._build_groups_panel(), "📁 Groups")
        self._lower_tabs.addTab(self._build_diagnostics_panel(), "📊 Health")
        self._lower_tabs.addTab(self._build_transcription_panel(), "🎤 Transcribe")
        self._lower_tabs.addTab(self._build_log_panel(), "📋 Log")

        splitter.addWidget(self._lower_tabs)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 300])

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

    # ── EQ panel ──────────────────────────────────────────────────────────────

    def _build_eq_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header row
        header = QHBoxLayout()
        self._chk_eq = QCheckBox("Enable Equalizer")
        self._chk_eq.setToolTip("Apply 10-band equalizer to audio output")
        header.addWidget(self._chk_eq)

        header.addStretch()

        self._cmb_eq_preset = QComboBox()
        self._cmb_eq_preset.setToolTip("Load an EQ preset")
        self._cmb_eq_preset.setMinimumWidth(120)
        # Populate with presets from Equalizer module
        try:
            from equalizer import Equalizer
            for name in Equalizer.PRESETS:
                self._cmb_eq_preset.addItem(name)
        except ImportError:
            self._cmb_eq_preset.addItem("Flat")
        header.addWidget(QLabel("Preset:"))
        header.addWidget(self._cmb_eq_preset)

        self._btn_eq_reset = QPushButton("Reset")
        self._btn_eq_reset.setToolTip("Reset all EQ bands to 0 dB")
        header.addWidget(self._btn_eq_reset)

        layout.addLayout(header)

        # EQ sliders
        eq_row = QHBoxLayout()
        eq_row.setSpacing(4)
        self._eq_sliders: List[QSlider] = []
        self._eq_labels: List[QLabel] = []

        try:
            from equalizer import Equalizer
            bands = Equalizer.BANDS
        except ImportError:
            bands = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

        for freq in bands:
            band_col = QVBoxLayout()
            band_col.setSpacing(2)

            gain_lbl = QLabel("0")
            gain_lbl.setAlignment(Qt.AlignHCenter)
            gain_lbl.setStyleSheet(f"color: {self._colours['accent']}; font-size: 10px;")
            gain_lbl.setFixedWidth(30)
            band_col.addWidget(gain_lbl)
            self._eq_labels.append(gain_lbl)

            slider = QSlider(Qt.Vertical)
            slider.setRange(-120, 120)  # -12 to +12 dB × 10
            slider.setValue(0)
            slider.setFixedHeight(100)
            slider.setToolTip(f"{freq} Hz")
            band_col.addWidget(slider, alignment=Qt.AlignHCenter)
            self._eq_sliders.append(slider)

            freq_text = f"{freq // 1000}k" if freq >= 1000 else str(freq)
            freq_lbl = QLabel(freq_text)
            freq_lbl.setAlignment(Qt.AlignHCenter)
            freq_lbl.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 9px;")
            band_col.addWidget(freq_lbl)

            eq_row.addLayout(band_col)

        layout.addLayout(eq_row)

        # Status label
        self._lbl_eq_status = QLabel("")
        self._lbl_eq_status.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 10px;")
        layout.addWidget(self._lbl_eq_status)

        try:
            from equalizer import SCIPY_AVAILABLE
            if not SCIPY_AVAILABLE:
                self._lbl_eq_status.setText(
                    "⚠ scipy not installed — EQ is in passthrough mode. "
                    "Run: pip install scipy"
                )
        except ImportError:
            self._lbl_eq_status.setText("⚠ equalizer module not available")

        layout.addStretch()
        return panel

    # ── Waveform panel ────────────────────────────────────────────────────────

    def _build_waveform_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        try:
            from ui.waveform_widget import WaveformWidget
            self._waveform_widget = WaveformWidget(
                parent=panel,
                display_seconds=5.0,
                sample_rate=self._router.get_sample_rate(),
            )
            self._waveform_widget.setMinimumHeight(120)
            layout.addWidget(self._waveform_widget)

            # Connect to audio engine
            self._router.set_waveform_callback(self._waveform_widget.push_samples)
        except ImportError:
            lbl = QLabel("⚠ Waveform widget not available")
            lbl.setStyleSheet(f"color: {self._colours['warn']};")
            layout.addWidget(lbl)

        layout.addStretch()
        return panel

    # ── Ducking panel ─────────────────────────────────────────────────────────

    def _build_ducking_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        desc = QLabel(
            "Audio ducking automatically lowers the master volume when a "
            "priority application (e.g., Discord, Teams) produces audio."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 11px;")
        layout.addWidget(desc)

        self._chk_ducking = QCheckBox("Enable Audio Ducking")
        self._chk_ducking.setToolTip("Lower volume when a priority app is active")
        layout.addWidget(self._chk_ducking)

        app_row = QHBoxLayout()
        app_lbl = QLabel("Priority App:")
        app_lbl.setStyleSheet(f"color: {self._colours['text_secondary']};")
        app_row.addWidget(app_lbl)
        self._txt_ducking_app = QLineEdit()
        self._txt_ducking_app.setPlaceholderText("e.g. Discord.exe, Teams.exe")
        self._txt_ducking_app.setToolTip(
            "Process name of the priority application.\n"
            "When this app produces audio, other volume is reduced."
        )
        app_row.addWidget(self._txt_ducking_app)
        layout.addLayout(app_row)

        red_row = QHBoxLayout()
        red_lbl = QLabel("Volume Reduction:")
        red_lbl.setStyleSheet(f"color: {self._colours['text_secondary']};")
        red_row.addWidget(red_lbl)
        self._sld_ducking_reduction = QSlider(Qt.Horizontal)
        self._sld_ducking_reduction.setRange(10, 90)
        self._sld_ducking_reduction.setValue(30)
        self._sld_ducking_reduction.setToolTip("How much to reduce volume (10%–90%)")
        red_row.addWidget(self._sld_ducking_reduction)
        self._lbl_ducking_pct = QLabel("30%")
        self._lbl_ducking_pct.setStyleSheet(f"color: {self._colours['text_secondary']};")
        red_row.addWidget(self._lbl_ducking_pct)
        layout.addLayout(red_row)

        self._lbl_ducking_status = QLabel("Ducking: Inactive")
        self._lbl_ducking_status.setStyleSheet(f"color: {self._colours['text_secondary']};")
        layout.addWidget(self._lbl_ducking_status)

        layout.addStretch()
        return panel

    # ── Device Groups panel ───────────────────────────────────────────────────

    def _build_groups_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        desc = QLabel(
            "Create named device groups (zones) for quick switching.\n"
            "Select a group to enable only those devices."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 11px;")
        layout.addWidget(desc)

        ctrl_row = QHBoxLayout()
        self._cmb_groups = QComboBox()
        self._cmb_groups.setMinimumWidth(150)
        self._cmb_groups.addItem("— Select Group —")
        ctrl_row.addWidget(self._cmb_groups)

        self._btn_save_group = QPushButton("💾 Save Group")
        self._btn_save_group.setToolTip("Save currently enabled devices as a named group")
        ctrl_row.addWidget(self._btn_save_group)

        self._btn_delete_group = QPushButton("🗑 Delete")
        self._btn_delete_group.setToolTip("Delete the selected group")
        ctrl_row.addWidget(self._btn_delete_group)

        self._btn_apply_group = QPushButton("✅ Apply")
        self._btn_apply_group.setToolTip("Enable only devices in the selected group")
        ctrl_row.addWidget(self._btn_apply_group)

        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        self._lbl_group_info = QLabel("")
        self._lbl_group_info.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 11px;")
        self._lbl_group_info.setWordWrap(True)
        layout.addWidget(self._lbl_group_info)

        layout.addStretch()

        # Load saved groups
        self._device_groups: Dict[str, List[str]] = self._settings.get_device_groups()
        self._refresh_groups_combo()

        return panel

    # ── Diagnostics / Health panel ────────────────────────────────────────────

    def _build_diagnostics_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        desc = QLabel("Real-time device health and performance diagnostics.")
        desc.setStyleSheet(f"color: {self._colours['text_secondary']}; font-size: 11px;")
        layout.addWidget(desc)

        self._diag_text = QPlainTextEdit()
        self._diag_text.setObjectName("log_panel")
        self._diag_text.setReadOnly(True)
        self._diag_text.setPlaceholderText("Start routing to see device diagnostics…")
        layout.addWidget(self._diag_text)

        btn_row = QHBoxLayout()
        self._btn_diag_refresh = QPushButton("⟳ Refresh")
        self._btn_diag_refresh.setToolTip("Refresh device diagnostics")
        btn_row.addWidget(self._btn_diag_refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return panel

    # ── Transcription panel ──────────────────────────────────────────────────

    def _build_transcription_panel(self) -> QWidget:
        self._transcription_widget = TranscriptionWidget(self._colours, self)
        return self._transcription_widget

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
        if self._hotkey_mgr is not None:
            self._hotkey_mgr.shutdown()
        if self._mini_window is not None:
            self._mini_window.close()
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
        self._btn_export_profile.clicked.connect(self._on_export_profiles)
        self._btn_import_profile.clicked.connect(self._on_import_profiles)
        self._cmb_profile.currentIndexChanged.connect(self._on_profile_selected)

        # Search / filter
        self._txt_search.textChanged.connect(self._filter_devices)

        # Router callbacks
        self._router.on_routing_changed = self._on_routing_state_changed
        self._router.on_error = self._show_error
        self._router.on_device_error = self._on_device_error
        self._router.on_device_recovered = self._on_device_recovered
        self._router.on_recording_changed = self._on_recording_state_changed
        self._router.on_scheduled_recording_done = self._on_scheduled_recording_done

        # Mini mode
        self._btn_mini.clicked.connect(self._on_mini_mode)

        # Limiter
        self._chk_limiter.toggled.connect(self._on_limiter_toggled)
        self._sld_limiter_thresh.valueChanged.connect(self._on_limiter_threshold_changed)

        # Sample rate
        self._cmb_sample_rate.currentIndexChanged.connect(self._on_sample_rate_changed)

        # EQ
        self._chk_eq.toggled.connect(self._on_eq_toggled)
        self._cmb_eq_preset.currentTextChanged.connect(self._on_eq_preset_changed)
        self._btn_eq_reset.clicked.connect(self._on_eq_reset)
        for i, slider in enumerate(self._eq_sliders):
            slider.valueChanged.connect(lambda val, idx=i: self._on_eq_band_changed(idx, val))

        # Ducking
        self._chk_ducking.toggled.connect(self._on_ducking_toggled)
        self._sld_ducking_reduction.valueChanged.connect(
            lambda v: self._lbl_ducking_pct.setText(f"{v}%")
        )

        # Device groups
        self._btn_save_group.clicked.connect(self._on_save_group)
        self._btn_delete_group.clicked.connect(self._on_delete_group)
        self._btn_apply_group.clicked.connect(self._on_apply_group)

        # Diagnostics
        self._btn_diag_refresh.clicked.connect(self._refresh_diagnostics)

        # Auto-start Windows
        self._chk_auto_start_win.toggled.connect(self._on_auto_start_windows_toggled)

        # Notification sounds
        self._chk_notifications.toggled.connect(
            lambda v: self._settings.save_notification_sounds(v)
        )

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

        # Ducking check timer
        self._ducking_timer = QTimer(self)
        self._ducking_timer.setInterval(500)  # Check every 500 ms
        self._ducking_timer.timeout.connect(self._check_ducking)
        self._ducking_timer.start()

        # Diagnostics refresh timer
        self._diag_timer = QTimer(self)
        self._diag_timer.setInterval(2000)
        self._diag_timer.timeout.connect(self._refresh_diagnostics)

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

        # EQ settings
        self._settings.save_eq_enabled(self._chk_eq.isChecked())
        gains = [s.value() / 10.0 for s in self._eq_sliders]
        self._settings.save_eq_gains(gains)
        self._settings.save_eq_preset(self._cmb_eq_preset.currentText())

        # Limiter settings
        self._settings.save_limiter_enabled(self._chk_limiter.isChecked())
        self._settings.save_limiter_threshold(self._sld_limiter_thresh.value() / 100.0)

        # Sample rate
        sr_values = [44100, 48000, 96000]
        sr_idx = self._cmb_sample_rate.currentIndex()
        if 0 <= sr_idx < len(sr_values):
            self._settings.save_sample_rate(sr_values[sr_idx])

        # Ducking
        self._settings.save_ducking_enabled(self._chk_ducking.isChecked())
        self._settings.save_ducking_app(self._txt_ducking_app.text())
        self._settings.save_ducking_reduction(self._sld_ducking_reduction.value() / 100.0)

        # Device groups
        self._settings.save_device_groups(self._device_groups)

        # Monitor config
        self._settings.save_monitor_config(self._get_monitor_config_str())

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

        # Restore EQ settings
        self._chk_eq.setChecked(self._settings.get_eq_enabled())
        saved_gains = self._settings.get_eq_gains()
        if saved_gains and len(saved_gains) == len(self._eq_sliders):
            for i, gain in enumerate(saved_gains):
                self._eq_sliders[i].setValue(int(gain * 10))
        saved_preset = self._settings.get_eq_preset()
        idx = self._cmb_eq_preset.findText(saved_preset)
        if idx >= 0:
            self._cmb_eq_preset.setCurrentIndex(idx)

        # Restore limiter settings
        self._chk_limiter.setChecked(self._settings.get_limiter_enabled())
        thresh = self._settings.get_limiter_threshold()
        self._sld_limiter_thresh.setValue(int(thresh * 100))

        # Restore sample rate
        sr = self._settings.get_sample_rate()
        sr_map = {44100: 0, 48000: 1, 96000: 2}
        if sr in sr_map:
            self._cmb_sample_rate.setCurrentIndex(sr_map[sr])
            self._router.set_sample_rate(sr)

        # Restore ducking settings
        self._chk_ducking.setChecked(self._settings.get_ducking_enabled())
        self._txt_ducking_app.setText(self._settings.get_ducking_app())
        reduction = self._settings.get_ducking_reduction()
        self._sld_ducking_reduction.setValue(int(reduction * 100))

        # Restore notification sounds
        self._chk_notifications.setChecked(self._settings.get_notification_sounds())

        # Restore auto-start Windows
        try:
            from autostart import is_auto_start_enabled
            self._chk_auto_start_win.setChecked(is_auto_start_enabled())
        except ImportError:
            self._chk_auto_start_win.setEnabled(False)

        # Restore monitor config for multi-monitor support
        saved_config = self._settings.get_monitor_config()
        current_config = self._get_monitor_config_str()
        if saved_config and saved_config != current_config:
            logger.info("Monitor configuration changed since last session")

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
            "<p><b>Global hotkeys</b> (work when minimised):</p>"
            "<ul>"
            "<li><b>Ctrl+Alt+R</b> — Toggle routing</li>"
            "<li><b>Ctrl+Alt+M</b> — Toggle mute</li>"
            "<li><b>Ctrl+Alt+↑/↓</b> — Volume up / down</li>"
            "</ul>"
            "<p><b>New features:</b> EQ, Waveform, Audio Ducking, Device Groups, "
            "Mini Mode, Timed Recording, Diagnostics, Profile Import/Export, "
            "and more — explore the tabs below!</p>"
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

        # Apply saved device order
        saved_order = self._settings.get_device_order()
        if saved_order:
            order_map = {name: i for i, name in enumerate(saved_order)}
            devices.sort(key=lambda d: order_map.get(d["name"], 9999))

        # Insert new cards (before the stretch)
        insert_idx = self._devices_layout.count() - 1
        for dev in devices:
            card = DeviceCard(dev, parent=self._devices_container)
            card.enabled_changed.connect(self._on_device_enabled_changed)
            card.volume_changed.connect(self._on_device_volume_changed)
            card.mute_changed.connect(self._on_device_mute_changed)
            card.delay_changed.connect(self._on_device_delay_changed)
            card.drop_received.connect(self._on_device_reordered)

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
        self._play_notification("device_error")

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
        self._play_notification("device_recovered")

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
                self._router.set_source_device(source_id)

        # Check for timed recording
        duration_min = self._spn_rec_minutes.value()
        if duration_min > 0:
            self._router.start_scheduled_recording(duration_min * 60)
        else:
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
            discard_path = os.path.join(tempfile.mkdtemp(), "discard.m4a")
            self._router.stop_recording(discard_path)
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

        # Mini window sync
        if self._mini_window is not None:
            self._mini_window.set_routing_active(active)

        # Notification sound
        self._play_notification("routing_start" if active else "routing_stop")

        # Start/stop diagnostics auto-refresh
        if active:
            self._diag_timer.start()
        else:
            self._diag_timer.stop()

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

    # ── Device drag-and-drop reorder ─────────────────────────────────────────

    @pyqtSlot(int, int)
    def _on_device_reordered(self, source_id: int, target_id: int) -> None:
        """Move source_id device card to the position of target_id."""
        if source_id not in self._device_cards or target_id not in self._device_cards:
            return

        source_card = self._device_cards[source_id]
        target_card = self._device_cards[target_id]

        # Find positions in layout
        source_idx = self._devices_layout.indexOf(source_card)
        target_idx = self._devices_layout.indexOf(target_card)

        if source_idx < 0 or target_idx < 0:
            return

        # Remove and re-insert at target position
        self._devices_layout.removeWidget(source_card)
        self._devices_layout.insertWidget(target_idx, source_card)

        # Persist the new order
        order = []
        for i in range(self._devices_layout.count()):
            widget = self._devices_layout.itemAt(i).widget()
            if isinstance(widget, DeviceCard):
                order.append(widget._device_name)
        self._settings.save_device_order(order)

        self.statusBar().showMessage("Device order updated.", 2000)

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

            # Update mini window if open
            if self._mini_window is not None:
                self._mini_window.set_levels(L, R)

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

    # ── Profile import / export ──────────────────────────────────────────────

    def _on_export_profiles(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Profiles", "audio_profiles.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            if self._profile_mgr.export_to_file(path):
                self.statusBar().showMessage(f"Profiles exported to {path}", 3000)
            else:
                self._show_error("Failed to export profiles.")

    def _on_import_profiles(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Profiles", "",
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            count = self._profile_mgr.import_from_file(path)
            if count > 0:
                self._refresh_profile_combo()
                self.statusBar().showMessage(
                    f"Imported {count} profile(s) from {path}", 3000
                )
            else:
                self._show_error("No valid profiles found in the file.")

    # ── Mini mode ────────────────────────────────────────────────────────────

    def _on_mini_mode(self) -> None:
        """Switch to the compact mini-mode window."""
        try:
            from ui.mini_window import MiniWindow
        except ImportError:
            self._show_error("Mini window module not available.")
            return

        if self._mini_window is None:
            self._mini_window = MiniWindow()
            self._mini_window.volume_changed.connect(self._sld_master.setValue)
            self._mini_window.mute_toggled.connect(self._btn_mute_all.setChecked)
            self._mini_window.routing_toggled.connect(self._toggle_routing)
            self._mini_window.expand_requested.connect(self._expand_from_mini)

        # Sync state to mini window
        self._mini_window.set_volume(self._sld_master.value())
        self._mini_window.set_muted(self._btn_mute_all.isChecked())
        self._mini_window.set_routing_active(self._router.is_routing)

        self.hide()
        self._mini_window.show()

    def _expand_from_mini(self) -> None:
        """Return from mini mode to the full window."""
        if self._mini_window is not None:
            self._mini_window.hide()
        self.showNormal()
        self.activateWindow()
        self.raise_()

    # ── EQ handlers ──────────────────────────────────────────────────────────

    def _on_eq_toggled(self, checked: bool) -> None:
        self._router.set_eq_enabled(checked)
        self._settings.save_eq_enabled(checked)

    def _on_eq_band_changed(self, band_idx: int, value: int) -> None:
        gain_db = value / 10.0
        self._eq_labels[band_idx].setText(f"{gain_db:+.1f}")
        eq = self._router.get_equalizer()
        if eq is not None:
            eq.set_gain(band_idx, gain_db)

    def _on_eq_preset_changed(self, preset_name: str) -> None:
        try:
            from equalizer import Equalizer
            if preset_name in Equalizer.PRESETS:
                gains = Equalizer.PRESETS[preset_name]
                eq = self._router.get_equalizer()
                if eq is not None:
                    eq.set_gains(gains)
                for i, gain in enumerate(gains):
                    if i < len(self._eq_sliders):
                        self._eq_sliders[i].blockSignals(True)
                        self._eq_sliders[i].setValue(int(gain * 10))
                        self._eq_labels[i].setText(f"{gain:+.1f}")
                        self._eq_sliders[i].blockSignals(False)
                self._settings.save_eq_preset(preset_name)
        except ImportError:
            pass

    def _on_eq_reset(self) -> None:
        for i, slider in enumerate(self._eq_sliders):
            slider.setValue(0)
            self._eq_labels[i].setText("0")
        eq = self._router.get_equalizer()
        if eq is not None:
            eq.set_gains([0.0] * len(self._eq_sliders))
        idx = self._cmb_eq_preset.findText("Flat")
        if idx >= 0:
            self._cmb_eq_preset.blockSignals(True)
            self._cmb_eq_preset.setCurrentIndex(idx)
            self._cmb_eq_preset.blockSignals(False)

    # ── Limiter handlers ─────────────────────────────────────────────────────

    def _on_limiter_toggled(self, checked: bool) -> None:
        self._router.set_limiter_enabled(checked)
        self._settings.save_limiter_enabled(checked)

    def _on_limiter_threshold_changed(self, value: int) -> None:
        self._lbl_limiter_thresh.setText(f"{value}%")
        self._router.set_limiter_threshold(value / 100.0)
        self._settings.save_limiter_threshold(value / 100.0)

    # ── Sample rate handler ──────────────────────────────────────────────────

    def _on_sample_rate_changed(self, index: int) -> None:
        sr_values = [44100, 48000, 96000]
        if 0 <= index < len(sr_values):
            self._router.set_sample_rate(sr_values[index])
            self._settings.save_sample_rate(sr_values[index])
            if self._router.is_routing:
                self.statusBar().showMessage(
                    "Sample rate changed — restart routing to apply.", 3000
                )

    # ── Ducking handlers ─────────────────────────────────────────────────────

    def _on_ducking_toggled(self, checked: bool) -> None:
        self._settings.save_ducking_enabled(checked)
        if not checked and self._ducking_active:
            self._restore_ducking_volume()

    def _check_ducking(self) -> None:
        """Periodically check if the priority app is producing audio."""
        if not self._chk_ducking.isChecked():
            return
        if not self._dev_mgr.available:
            return

        target_app = self._txt_ducking_app.text().strip().lower()
        if not target_app:
            return

        # Check if any audio session matches the target app and has peak > 0
        sessions = self._dev_mgr.get_sessions()
        app_active = False
        for session in sessions:
            if session.process_name.lower() == target_app:
                peak = session.get_peak()
                if peak > 0.01:
                    app_active = True
                    break

        if app_active and not self._ducking_active:
            # Start ducking
            self._ducking_original_volume = self._sld_master.value()
            reduction = self._sld_ducking_reduction.value() / 100.0
            new_vol = max(0, int(self._ducking_original_volume * (1.0 - reduction)))
            self._sld_master.setValue(new_vol)
            self._ducking_active = True
            self._lbl_ducking_status.setText(
                f"Ducking: Active (reduced to {new_vol}%)"
            )
            self._lbl_ducking_status.setStyleSheet(
                f"color: {self._colours.get('warn', '#f0a500')};"
            )
        elif not app_active and self._ducking_active:
            self._restore_ducking_volume()

    def _restore_ducking_volume(self) -> None:
        """Restore volume after ducking ends."""
        if self._ducking_original_volume is not None:
            self._sld_master.setValue(self._ducking_original_volume)
            self._ducking_original_volume = None
        self._ducking_active = False
        self._lbl_ducking_status.setText("Ducking: Inactive")
        self._lbl_ducking_status.setStyleSheet(
            f"color: {self._colours['text_secondary']};"
        )

    # ── Device groups handlers ───────────────────────────────────────────────

    def _refresh_groups_combo(self) -> None:
        self._cmb_groups.blockSignals(True)
        self._cmb_groups.clear()
        self._cmb_groups.addItem("— Select Group —")
        for name in sorted(self._device_groups.keys()):
            self._cmb_groups.addItem(name)
        self._cmb_groups.blockSignals(False)

    def _on_save_group(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Save Device Group", "Group name:"
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        enabled_names = [
            card._device_name
            for card in self._device_cards.values()
            if card.is_enabled()
        ]
        if not enabled_names:
            QMessageBox.information(
                self, "No Devices",
                "Enable at least one device before saving a group."
            )
            return

        self._device_groups[name] = enabled_names
        self._settings.save_device_groups(self._device_groups)
        self._refresh_groups_combo()
        self.statusBar().showMessage(f"Group '{name}' saved ({len(enabled_names)} devices).", 3000)

    def _on_delete_group(self) -> None:
        idx = self._cmb_groups.currentIndex()
        if idx <= 0:
            return
        name = self._cmb_groups.currentText()
        reply = QMessageBox.question(
            self, "Delete Group", f"Delete group '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._device_groups.pop(name, None)
            self._settings.save_device_groups(self._device_groups)
            self._refresh_groups_combo()

    def _on_apply_group(self) -> None:
        idx = self._cmb_groups.currentIndex()
        if idx <= 0:
            return
        name = self._cmb_groups.currentText()
        device_names = self._device_groups.get(name, [])
        if not device_names:
            return

        for card in self._device_cards.values():
            card.set_enabled(card._device_name in device_names)

        self._lbl_group_info.setText(
            f"Applied group '{name}': {', '.join(device_names)}"
        )
        self.statusBar().showMessage(f"Group '{name}' applied.", 3000)

    # ── Diagnostics / Health ─────────────────────────────────────────────────

    def _refresh_diagnostics(self) -> None:
        """Update the device health / diagnostics panel."""
        lines = []
        lines.append("═══ DEVICE HEALTH REPORT ═══")
        lines.append(f"  Routing: {'Active' if self._router.is_routing else 'Inactive'}")
        lines.append(f"  Sample Rate: {self._router.get_sample_rate()} Hz")
        lines.append(f"  Block Size: {self._router.BLOCK_SIZE} samples")
        lines.append(f"  Latency: {self._router.get_latency_ms():.1f} ms")
        lines.append(f"  Avg CB Duration: {self._router.get_avg_cb_duration_ms():.3f} ms")
        lines.append(f"  Buffer Underruns: {self._router.get_buffer_underruns()}")
        lines.append(f"  EQ: {'Enabled' if self._router.is_eq_enabled() else 'Disabled'}")
        lines.append(f"  Limiter: {'Enabled' if self._router.is_limiter_enabled() else 'Disabled'}")
        lines.append("")

        devices = self._router.get_output_devices()
        errors = self._router.get_device_errors()
        failed = self._router.failed_device_ids

        for dev in devices:
            dev_id = dev["id"]
            status = "✅ OK"
            if dev_id in failed:
                status = "❌ FAILED"
            elif dev_id in errors:
                status = f"⚠ ERROR: {errors[dev_id]}"
            elif dev_id in self._router.active_device_ids:
                status = "🟢 ACTIVE"

            lines.append(f"  [{dev_id}] {dev['name']}")
            lines.append(f"      API: {dev['hostapi']}  |  Channels: {dev['channels']}")
            lines.append(f"      Default SR: {dev['default_samplerate']} Hz")
            lines.append(f"      Latency: {dev['default_latency_ms']:.1f} ms")
            lines.append(f"      Status: {status}")
            lines.append("")

        self._diag_text.setPlainText("\n".join(lines))

    # ── Scheduled recording ──────────────────────────────────────────────────

    def _on_scheduled_recording_done(self) -> None:
        """Called from the audio engine when timed recording finishes."""
        QTimer.singleShot(0, self._finish_recording)
        self._play_notification("recording_done")

    # ── Notification sounds ──────────────────────────────────────────────────

    def _play_notification(self, event_name: str) -> None:
        """Play a system notification sound if enabled."""
        if not self._chk_notifications.isChecked():
            return
        if sys.platform != "win32":
            return
        try:
            import winsound
            sound_map = {
                "routing_start": winsound.MB_OK,
                "routing_stop": winsound.MB_ICONASTERISK,
                "recording_done": winsound.MB_ICONEXCLAMATION,
                "device_error": winsound.MB_ICONHAND,
                "device_recovered": winsound.MB_OK,
            }
            sound = sound_map.get(event_name, winsound.MB_OK)
            winsound.MessageBeep(sound)
        except Exception:
            pass

    # ── Auto-start with Windows ──────────────────────────────────────────────

    def _on_auto_start_windows_toggled(self, checked: bool) -> None:
        try:
            from autostart import set_auto_start
            success = set_auto_start(checked)
            if success:
                self._settings.save_auto_start_windows(checked)
                self.statusBar().showMessage(
                    f"Auto-start {'enabled' if checked else 'disabled'}.", 3000
                )
            else:
                self._chk_auto_start_win.blockSignals(True)
                self._chk_auto_start_win.setChecked(not checked)
                self._chk_auto_start_win.blockSignals(False)
                self._show_error("Failed to modify Windows startup settings.")
        except ImportError:
            self._show_error("Auto-start module not available on this platform.")

    # ── Multi-monitor support ────────────────────────────────────────────────

    def _get_monitor_config_str(self) -> str:
        """Build a string representing the current monitor layout."""
        try:
            screens = QApplication.screens()
            parts = []
            for s in screens:
                g = s.geometry()
                parts.append(f"{s.name()}:{g.width()}x{g.height()}@{g.x()},{g.y()}")
            return "|".join(sorted(parts))
        except Exception:
            return ""

    # ── Global hotkeys ───────────────────────────────────────────────────────

    def _setup_hotkeys(self) -> None:
        """Register system-wide hotkeys."""
        if not self._settings.get_hotkeys_enabled():
            return
        try:
            from hotkey_manager import HotkeyManager, DEFAULT_HOTKEYS
        except ImportError:
            logger.info("Global hotkeys not available (Windows only)")
            return

        self._hotkey_mgr = HotkeyManager()
        if not self._hotkey_mgr.available:
            return

        for name, (modifiers, vk) in DEFAULT_HOTKEYS.items():
            callback = self._get_hotkey_callback(name)
            if callback:
                self._hotkey_mgr.register(name, modifiers, vk, callback)

        logger.info("Global hotkeys registered")

    def _get_hotkey_callback(self, name: str):
        """Return a callback function for a named hotkey action."""
        callbacks = {
            "toggle_routing": lambda: QTimer.singleShot(0, self._toggle_routing),
            "toggle_mute": lambda: QTimer.singleShot(0, self._btn_mute_all.toggle),
            "volume_up": lambda: QTimer.singleShot(
                0, lambda: self._sld_master.setValue(min(100, self._sld_master.value() + 5))
            ),
            "volume_down": lambda: QTimer.singleShot(
                0, lambda: self._sld_master.setValue(max(0, self._sld_master.value() - 5))
            ),
            "toggle_recording": lambda: QTimer.singleShot(0, self._on_record_toggle),
        }
        return callbacks.get(name)

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
            self._ducking_timer.stop()
            self._diag_timer.stop()
            self._router.stop_routing()
            self._dev_mgr.shutdown()
            # Clean up hotkeys
            if self._hotkey_mgr is not None:
                self._hotkey_mgr.shutdown()
            # Close mini window
            if self._mini_window is not None:
                self._mini_window.close()
            # Clean up transcription
            if hasattr(self, '_transcription_widget'):
                self._transcription_widget.cleanup()
            self._tray_icon.hide()
            # Remove our log handler to prevent errors during shutdown
            logging.getLogger().removeHandler(self._log_handler)
            event.accept()
