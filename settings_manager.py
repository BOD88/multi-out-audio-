"""
settings_manager.py
===================
Persistent application settings using QSettings.

Stores and restores:
  • Window geometry (position, size)
  • Last-used device selections and volume levels
  • Master volume and mute state
  • Capture source device
  • Auto-start routing preference
  • Theme preference (dark / light)
  • Device order preferences
"""

import json
import logging
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QSettings

logger = logging.getLogger(__name__)

# QSettings keys
_K_GEOMETRY = "window/geometry"
_K_STATE = "window/state"
_K_MASTER_VOLUME = "audio/master_volume"
_K_MASTER_MUTED = "audio/master_muted"
_K_SOURCE_DEVICE = "audio/source_device_name"
_K_ENABLED_DEVICES = "audio/enabled_device_names"
_K_DEVICE_VOLUMES = "audio/device_volumes"
_K_AUTO_START = "audio/auto_start"
_K_THEME = "ui/theme"
_K_MINIMIZE_TO_TRAY = "ui/minimize_to_tray"
_K_FIRST_RUN = "ui/first_run_done"
_K_PROFILES = "profiles/data"
_K_DEVICE_DELAYS = "audio/device_delays"
_K_DEVICE_ORDER = "ui/device_order"
_K_AUTO_SYNC_DELAY = "audio/auto_sync_delay"
_K_SAMPLE_RATE = "audio/sample_rate"
_K_EQ_ENABLED = "audio/eq_enabled"
_K_EQ_GAINS = "audio/eq_gains"
_K_EQ_PRESET = "audio/eq_preset"
_K_LIMITER_ENABLED = "audio/limiter_enabled"
_K_LIMITER_THRESHOLD = "audio/limiter_threshold"
_K_HOTKEYS_ENABLED = "audio/hotkeys_enabled"
_K_HOTKEY_BINDINGS = "audio/hotkey_bindings"
_K_DUCKING_ENABLED = "audio/ducking_enabled"
_K_DUCKING_APP = "audio/ducking_app"
_K_DUCKING_REDUCTION = "audio/ducking_reduction"
_K_DEVICE_GROUPS = "ui/device_groups"
_K_NOTIFICATION_SOUNDS = "ui/notification_sounds"
_K_AUTO_START_WINDOWS = "ui/auto_start_windows"
_K_MONITOR_CONFIG = "ui/monitor_config"


class SettingsManager:
    """
    Centralised persistent settings backed by QSettings (registry on Windows,
    INI-like files on other platforms).
    """

    def __init__(self) -> None:
        self._settings = QSettings("BOD88", "MultiOutputAudioConsole")

    # ── helpers ──

    def _get(self, key: str, default: Any = None, type_: type = None) -> Any:
        if type_ is not None:
            return self._settings.value(key, default, type=type_)
        return self._settings.value(key, default)

    def _set(self, key: str, value: Any) -> None:
        self._settings.setValue(key, value)

    # ── window geometry ──

    def save_geometry(self, geometry: bytes, state: bytes) -> None:
        self._set(_K_GEOMETRY, geometry)
        self._set(_K_STATE, state)

    def restore_geometry(self) -> Optional[bytes]:
        return self._get(_K_GEOMETRY)

    def restore_state(self) -> Optional[bytes]:
        return self._get(_K_STATE)

    # ── master volume ──

    def save_master_volume(self, volume: float) -> None:
        self._set(_K_MASTER_VOLUME, volume)

    def get_master_volume(self) -> float:
        val = self._get(_K_MASTER_VOLUME, 1.0)
        try:
            return float(val)
        except (ValueError, TypeError):
            return 1.0

    def save_master_muted(self, muted: bool) -> None:
        self._set(_K_MASTER_MUTED, muted)

    def get_master_muted(self) -> bool:
        val = self._get(_K_MASTER_MUTED, False)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    # ── source device ──

    def save_source_device(self, device_name: str) -> None:
        self._set(_K_SOURCE_DEVICE, device_name)

    def get_source_device(self) -> Optional[str]:
        return self._get(_K_SOURCE_DEVICE)

    # ── enabled devices ──

    def save_enabled_devices(self, device_names: List[str]) -> None:
        self._set(_K_ENABLED_DEVICES, json.dumps(device_names))

    def get_enabled_devices(self) -> List[str]:
        raw = self._get(_K_ENABLED_DEVICES, "[]")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    # ── device volumes (name → volume float) ──

    def save_device_volumes(self, volumes: Dict[str, float]) -> None:
        self._set(_K_DEVICE_VOLUMES, json.dumps(volumes))

    def get_device_volumes(self) -> Dict[str, float]:
        raw = self._get(_K_DEVICE_VOLUMES, "{}")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    # ── device delays (name → delay_ms float) ──

    def save_device_delays(self, delays: Dict[str, float]) -> None:
        self._set(_K_DEVICE_DELAYS, json.dumps(delays))

    def get_device_delays(self) -> Dict[str, float]:
        raw = self._get(_K_DEVICE_DELAYS, "{}")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    # ── auto start ──

    def save_auto_start(self, enabled: bool) -> None:
        self._set(_K_AUTO_START, enabled)

    def get_auto_start(self) -> bool:
        val = self._get(_K_AUTO_START, False)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    # ── theme ──

    def save_theme(self, theme: str) -> None:
        self._set(_K_THEME, theme)

    def get_theme(self) -> str:
        return self._get(_K_THEME, "dark") or "dark"

    # ── minimize to tray ──

    def save_minimize_to_tray(self, enabled: bool) -> None:
        self._set(_K_MINIMIZE_TO_TRAY, enabled)

    def get_minimize_to_tray(self) -> bool:
        val = self._get(_K_MINIMIZE_TO_TRAY, True)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    # ── first run ──

    def is_first_run(self) -> bool:
        val = self._get(_K_FIRST_RUN, False)
        if isinstance(val, str):
            return val.lower() != "true"
        return not bool(val)

    def mark_first_run_done(self) -> None:
        self._set(_K_FIRST_RUN, True)

    # ── profiles ──

    def save_profiles(self, profiles: Dict[str, dict]) -> None:
        self._set(_K_PROFILES, json.dumps(profiles))

    def get_profiles(self) -> Dict[str, dict]:
        raw = self._get(_K_PROFILES, "{}")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    # ── device order ──

    def save_device_order(self, order: List[str]) -> None:
        self._set(_K_DEVICE_ORDER, json.dumps(order))

    def get_device_order(self) -> List[str]:
        raw = self._get(_K_DEVICE_ORDER, "[]")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    # ── auto-sync delay ──

    def save_auto_sync_delay(self, enabled: bool) -> None:
        self._set(_K_AUTO_SYNC_DELAY, enabled)

    def get_auto_sync_delay(self) -> bool:
        val = self._get(_K_AUTO_SYNC_DELAY, True)  # default ON
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    # ── sample rate ──

    def save_sample_rate(self, rate: int) -> None:
        self._set(_K_SAMPLE_RATE, rate)

    def get_sample_rate(self) -> int:
        val = self._get(_K_SAMPLE_RATE, 48000)
        try:
            return int(val)
        except (ValueError, TypeError):
            return 48000

    # ── equalizer ──

    def save_eq_enabled(self, enabled: bool) -> None:
        self._set(_K_EQ_ENABLED, enabled)

    def get_eq_enabled(self) -> bool:
        val = self._get(_K_EQ_ENABLED, False)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    def save_eq_gains(self, gains: List[float]) -> None:
        self._set(_K_EQ_GAINS, json.dumps(gains))

    def get_eq_gains(self) -> List[float]:
        raw = self._get(_K_EQ_GAINS, "[]")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    def save_eq_preset(self, preset: str) -> None:
        self._set(_K_EQ_PRESET, preset)

    def get_eq_preset(self) -> str:
        return self._get(_K_EQ_PRESET, "Flat") or "Flat"

    # ── limiter ──

    def save_limiter_enabled(self, enabled: bool) -> None:
        self._set(_K_LIMITER_ENABLED, enabled)

    def get_limiter_enabled(self) -> bool:
        val = self._get(_K_LIMITER_ENABLED, False)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    def save_limiter_threshold(self, threshold: float) -> None:
        self._set(_K_LIMITER_THRESHOLD, threshold)

    def get_limiter_threshold(self) -> float:
        val = self._get(_K_LIMITER_THRESHOLD, 0.95)
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.95

    # ── global hotkeys ──

    def save_hotkeys_enabled(self, enabled: bool) -> None:
        self._set(_K_HOTKEYS_ENABLED, enabled)

    def get_hotkeys_enabled(self) -> bool:
        val = self._get(_K_HOTKEYS_ENABLED, True)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    def save_hotkey_bindings(self, bindings: Dict[str, Any]) -> None:
        self._set(_K_HOTKEY_BINDINGS, json.dumps(bindings))

    def get_hotkey_bindings(self) -> Dict[str, Any]:
        raw = self._get(_K_HOTKEY_BINDINGS, "{}")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    # ── audio ducking ──

    def save_ducking_enabled(self, enabled: bool) -> None:
        self._set(_K_DUCKING_ENABLED, enabled)

    def get_ducking_enabled(self) -> bool:
        val = self._get(_K_DUCKING_ENABLED, False)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    def save_ducking_app(self, app_name: str) -> None:
        self._set(_K_DUCKING_APP, app_name)

    def get_ducking_app(self) -> str:
        return self._get(_K_DUCKING_APP, "") or ""

    def save_ducking_reduction(self, reduction: float) -> None:
        self._set(_K_DUCKING_REDUCTION, reduction)

    def get_ducking_reduction(self) -> float:
        val = self._get(_K_DUCKING_REDUCTION, 0.3)
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.3

    # ── device groups ──

    def save_device_groups(self, groups: Dict[str, List[str]]) -> None:
        self._set(_K_DEVICE_GROUPS, json.dumps(groups))

    def get_device_groups(self) -> Dict[str, List[str]]:
        raw = self._get(_K_DEVICE_GROUPS, "{}")
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    # ── notification sounds ──

    def save_notification_sounds(self, enabled: bool) -> None:
        self._set(_K_NOTIFICATION_SOUNDS, enabled)

    def get_notification_sounds(self) -> bool:
        val = self._get(_K_NOTIFICATION_SOUNDS, True)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    # ── auto-start with Windows ──

    def save_auto_start_windows(self, enabled: bool) -> None:
        self._set(_K_AUTO_START_WINDOWS, enabled)

    def get_auto_start_windows(self) -> bool:
        val = self._get(_K_AUTO_START_WINDOWS, False)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    # ── monitor configuration ──

    def save_monitor_config(self, config: str) -> None:
        self._set(_K_MONITOR_CONFIG, config)

    def get_monitor_config(self) -> str:
        return self._get(_K_MONITOR_CONFIG, "") or ""
