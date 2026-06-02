"""
profile_manager.py
==================
Audio profile (preset) management for Multi-Output Audio Console.

Profiles store:
  • Which output devices are enabled (by name for portability)
  • Per-device volume levels
  • Per-device mute states
  • Per-device delay offsets
  • Master volume and mute state
  • Capture source device name
"""

import json
import logging
from typing import Dict, List, Optional

from settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class AudioProfile:
    """Data class for a single audio profile."""

    def __init__(
        self,
        name: str,
        enabled_devices: Optional[List[str]] = None,
        device_volumes: Optional[Dict[str, float]] = None,
        device_delays: Optional[Dict[str, float]] = None,
        master_volume: float = 1.0,
        master_muted: bool = False,
        source_device: Optional[str] = None,
    ) -> None:
        self.name = name
        self.enabled_devices = enabled_devices or []
        self.device_volumes = device_volumes or {}
        self.device_delays = device_delays or {}
        self.master_volume = master_volume
        self.master_muted = master_muted
        self.source_device = source_device

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled_devices": self.enabled_devices,
            "device_volumes": self.device_volumes,
            "device_delays": self.device_delays,
            "master_volume": self.master_volume,
            "master_muted": self.master_muted,
            "source_device": self.source_device,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AudioProfile":
        return cls(
            name=data.get("name", "Unnamed"),
            enabled_devices=data.get("enabled_devices", []),
            device_volumes=data.get("device_volumes", {}),
            device_delays=data.get("device_delays", {}),
            master_volume=data.get("master_volume", 1.0),
            master_muted=data.get("master_muted", False),
            source_device=data.get("source_device"),
        )


class ProfileManager:
    """
    Manages named audio profiles backed by SettingsManager.
    """

    def __init__(self, settings: SettingsManager) -> None:
        self._settings = settings
        self._profiles: Dict[str, AudioProfile] = {}
        self._load()

    def _load(self) -> None:
        raw = self._settings.get_profiles()
        self._profiles = {}
        for name, data in raw.items():
            try:
                self._profiles[name] = AudioProfile.from_dict(data)
            except Exception as exc:
                logger.warning("Skipping corrupt profile '%s': %s", name, exc)

    def _save(self) -> None:
        data = {name: p.to_dict() for name, p in self._profiles.items()}
        self._settings.save_profiles(data)

    def list_profiles(self) -> List[str]:
        return sorted(self._profiles.keys())

    def get_profile(self, name: str) -> Optional[AudioProfile]:
        return self._profiles.get(name)

    def save_profile(self, profile: AudioProfile) -> None:
        self._profiles[profile.name] = profile
        self._save()
        logger.info("Profile saved: %s", profile.name)

    def delete_profile(self, name: str) -> bool:
        if name in self._profiles:
            del self._profiles[name]
            self._save()
            logger.info("Profile deleted: %s", name)
            return True
        return False

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        if old_name not in self._profiles or new_name in self._profiles:
            return False
        profile = self._profiles.pop(old_name)
        profile.name = new_name
        self._profiles[new_name] = profile
        self._save()
        return True

    def export_to_file(self, file_path: str) -> bool:
        """Export all profiles to a JSON file."""
        try:
            data = {name: p.to_dict() for name, p in self._profiles.items()}
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info("Profiles exported to %s", file_path)
            return True
        except Exception as exc:
            logger.error("Failed to export profiles: %s", exc)
            return False

    def import_from_file(self, file_path: str) -> int:
        """
        Import profiles from a JSON file.
        Returns the number of profiles successfully imported.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error("Failed to read profile file: %s", exc)
            return 0

        count = 0
        for name, profile_data in data.items():
            try:
                profile = AudioProfile.from_dict(profile_data)
                profile.name = name
                self._profiles[name] = profile
                count += 1
            except Exception as exc:
                logger.warning("Skipping invalid profile '%s': %s", name, exc)

        if count > 0:
            self._save()
            logger.info("Imported %d profile(s) from %s", count, file_path)
        return count
