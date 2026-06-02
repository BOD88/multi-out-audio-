"""
device_manager.py
=================
Windows audio session & device volume management via pycaw / Core Audio API.

Provides:
  • Enumeration of active audio sessions (running applications playing sound).
  • Per-application volume and mute control.
  • System device volume read / write.

All COM calls are confined to a single worker thread so the STA apartment
model requirement of the Core Audio APIs is satisfied regardless of which
Qt thread invokes the public methods.
"""

import logging
import queue
import sys
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful import — pycaw only works on Windows
# ---------------------------------------------------------------------------
PYCAW_AVAILABLE = False
if sys.platform == "win32":
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL

        PYCAW_AVAILABLE = True
    except Exception as exc:  # pragma: no cover
        logger.warning("pycaw import failed (%s). App-level mixing disabled.", exc)


class AudioSession:
    """Thin wrapper around a pycaw AudioSession object."""

    def __init__(self, raw_session) -> None:
        self._raw = raw_session

    # ---- identity ----

    @property
    def process_name(self) -> str:
        try:
            return self._raw.Process.name() if self._raw.Process else "System"
        except Exception:
            return "Unknown"

    @property
    def pid(self) -> int:
        try:
            return self._raw.Process.pid if self._raw.Process else 0
        except Exception:
            return 0

    # ---- volume ----

    def get_volume(self) -> float:
        try:
            return float(self._raw.SimpleAudioVolume.GetMasterVolume())
        except Exception:
            return 1.0

    def set_volume(self, volume: float) -> None:
        volume = max(0.0, min(1.0, volume))
        try:
            self._raw.SimpleAudioVolume.SetMasterVolume(volume, None)
        except Exception as exc:
            logger.debug("set_volume failed for %s: %s", self.process_name, exc)

    def get_mute(self) -> bool:
        try:
            return bool(self._raw.SimpleAudioVolume.GetMute())
        except Exception:
            return False

    def set_mute(self, muted: bool) -> None:
        try:
            self._raw.SimpleAudioVolume.SetMute(int(muted), None)
        except Exception as exc:
            logger.debug("set_mute failed for %s: %s", self.process_name, exc)

    # ---- peak ----

    def get_peak(self) -> float:
        """Return instantaneous peak level 0.0 – 1.0."""
        try:
            meter = self._raw.AudioMeterInformation
            if meter:
                return float(meter.GetPeakValue())
        except Exception:
            pass
        return 0.0


class DeviceManager:
    """
    Manages Windows audio sessions and provides per-application volume control.

    All pycaw / COM calls run on a dedicated STA thread to avoid COM
    apartment conflicts with Qt's main thread.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: List[AudioSession] = []
        self._com_thread: Optional[threading.Thread] = None
        self._com_queue: queue.Queue = queue.Queue()
        self._shutdown = threading.Event()

        if PYCAW_AVAILABLE:
            self._start_com_thread()

    # ------------------------------------------------------------------ COM thread --

    def _start_com_thread(self) -> None:
        """Start a STA worker thread for COM calls."""
        self._com_thread = threading.Thread(
            target=self._com_worker, daemon=True, name="DevMgr-COM"
        )
        self._com_thread.start()

    def _com_worker(self) -> None:
        """Worker loop: initialise COM, then drain _com_queue until shutdown."""
        try:
            import comtypes

            comtypes.CoInitialize()
        except Exception:
            pass
        try:
            while not self._shutdown.is_set():
                try:
                    fn, result_event, result_holder = self._com_queue.get(timeout=0.1)
                    try:
                        result_holder["value"] = fn()
                    except Exception as exc:
                        result_holder["error"] = exc
                    finally:
                        result_event.set()
                except queue.Empty:
                    continue
        finally:
            try:
                import comtypes

                comtypes.CoUninitialize()
            except Exception:
                pass

    def _call_com(self, fn, timeout: float = 3.0):
        """Execute *fn* on the COM thread and return its result (or raise)."""
        if not PYCAW_AVAILABLE:
            return None
        event = threading.Event()
        holder: Dict = {}
        self._com_queue.put((fn, event, holder))
        event.wait(timeout)
        if "error" in holder:
            raise holder["error"]
        return holder.get("value")

    # ------------------------------------------------------------------ public API --

    def get_sessions(self) -> List[AudioSession]:
        """Return a snapshot of active audio sessions (apps playing audio)."""
        if not PYCAW_AVAILABLE:
            return []

        def _fetch():
            raw_sessions = AudioUtilities.GetAllSessions()
            result = []
            for s in raw_sessions:
                # Skip sessions without a process (system sounds)
                if s.Process is None:
                    continue
                try:
                    name = s.Process.name()
                except Exception:
                    name = None
                if name:
                    result.append(AudioSession(s))
            return result

        try:
            sessions = self._call_com(_fetch)
            with self._lock:
                self._sessions = sessions or []
            return list(self._sessions)
        except Exception as exc:
            logger.error("get_sessions error: %s", exc)
            return []

    def refresh_sessions(self) -> List[AudioSession]:
        """Alias for get_sessions() — refreshes from OS."""
        return self.get_sessions()

    def set_session_volume(self, session: AudioSession, volume: float) -> None:
        if not PYCAW_AVAILABLE:
            return
        self._call_com(lambda: session.set_volume(volume))

    def set_session_mute(self, session: AudioSession, muted: bool) -> None:
        if not PYCAW_AVAILABLE:
            return
        self._call_com(lambda: session.set_mute(muted))

    def get_session_peak(self, session: AudioSession) -> float:
        if not PYCAW_AVAILABLE:
            return 0.0
        try:
            result = self._call_com(session.get_peak, timeout=0.2)
            return result if result is not None else 0.0
        except Exception:
            return 0.0

    def shutdown(self) -> None:
        """Signal the COM worker thread to exit."""
        self._shutdown.set()
        if self._com_thread and self._com_thread.is_alive():
            self._com_thread.join(timeout=2.0)

    @property
    def available(self) -> bool:
        """True if Windows Core Audio API is accessible."""
        return PYCAW_AVAILABLE
