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
