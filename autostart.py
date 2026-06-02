"""
autostart.py
============
Manage Windows startup registry entry for Multi-Output Audio Console.

Adds or removes a registry key under:
    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

This allows the application to launch automatically when the user logs in.
"""

import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful import — winreg only works on Windows
# ---------------------------------------------------------------------------
WINREG_AVAILABLE = False
if sys.platform == "win32":
    try:
        import winreg

        WINREG_AVAILABLE = True
    except ImportError:
        pass

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "MultiOutputAudioConsole"


def _get_app_path() -> str:
    """Return the path to the current executable or script."""
    if getattr(sys, "frozen", False):
        # Running as a compiled executable (PyInstaller)
        return sys.executable
    else:
        # Running as a Python script
        main_script = os.path.abspath(sys.argv[0])
        return f'"{sys.executable}" "{main_script}"'


def is_auto_start_enabled() -> bool:
    """Check if the application is set to start with Windows."""
    if not WINREG_AVAILABLE:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_auto_start(enabled: bool) -> bool:
    """
    Enable or disable auto-start with Windows.

    Returns True on success, False on failure.
    """
    if not WINREG_AVAILABLE:
        logger.warning("Windows registry not available — cannot set auto-start")
        return False

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE
        )
        try:
            if enabled:
                app_path = _get_app_path()
                winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, app_path)
                logger.info("Auto-start enabled: %s", app_path)
            else:
                try:
                    winreg.DeleteValue(key, _APP_NAME)
                    logger.info("Auto-start disabled")
                except FileNotFoundError:
                    pass  # Already removed
        finally:
            winreg.CloseKey(key)
        return True
    except Exception as exc:
        logger.error("Failed to modify auto-start registry: %s", exc)
        return False
