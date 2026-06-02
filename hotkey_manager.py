"""
hotkey_manager.py
=================
Global system hotkey registration for the Windows desktop app.

Uses the Win32 RegisterHotKey / UnregisterHotKey APIs directly via ctypes,
runs the message pump on a dedicated daemon thread, and dispatches callbacks
on a separate daemon thread so hotkey handlers remain thread-safe.

On non-Windows platforms the module degrades gracefully: HotkeyManager is
available but reports available=False and all registration methods become
safe no-ops.
"""

import ctypes
import logging
import queue
import sys
import threading
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_CODES: Dict[str, int] = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "RETURN": 0x0D,
    "ENTER": 0x0D,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "ALT": 0x12,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "PRINTSCREEN": 0x2C,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    "A": 0x41,
    "B": 0x42,
    "C": 0x43,
    "D": 0x44,
    "E": 0x45,
    "F": 0x46,
    "G": 0x47,
    "H": 0x48,
    "I": 0x49,
    "J": 0x4A,
    "K": 0x4B,
    "L": 0x4C,
    "M": 0x4D,
    "N": 0x4E,
    "O": 0x4F,
    "P": 0x50,
    "Q": 0x51,
    "R": 0x52,
    "S": 0x53,
    "T": 0x54,
    "U": 0x55,
    "V": 0x56,
    "W": 0x57,
    "X": 0x58,
    "Y": 0x59,
    "Z": 0x5A,
    "NUMPAD0": 0x60,
    "NUMPAD1": 0x61,
    "NUMPAD2": 0x62,
    "NUMPAD3": 0x63,
    "NUMPAD4": 0x64,
    "NUMPAD5": 0x65,
    "NUMPAD6": 0x66,
    "NUMPAD7": 0x67,
    "NUMPAD8": 0x68,
    "NUMPAD9": 0x69,
    "MULTIPLY": 0x6A,
    "ADD": 0x6B,
    "SUBTRACT": 0x6D,
    "DECIMAL": 0x6E,
    "DIVIDE": 0x6F,
    "F1": 0x70,
    "F2": 0x71,
    "F3": 0x72,
    "F4": 0x73,
    "F5": 0x74,
    "F6": 0x75,
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    "NUMLOCK": 0x90,
    "SCROLLLOCK": 0x91,
    "LWIN": 0x5B,
    "RWIN": 0x5C,
    "OEM_PLUS": 0xBB,
    "OEM_COMMA": 0xBC,
    "OEM_MINUS": 0xBD,
    "OEM_PERIOD": 0xBE,
}

DEFAULT_HOTKEYS: Dict[str, Tuple[int, int]] = {
    "toggle_routing": (MOD_CTRL | MOD_ALT, VK_CODES["R"]),
    "toggle_mute": (MOD_CTRL | MOD_ALT, VK_CODES["M"]),
    "volume_up": (MOD_CTRL | MOD_ALT, VK_CODES["UP"]),
    "volume_down": (MOD_CTRL | MOD_ALT, VK_CODES["DOWN"]),
    "toggle_recording": (MOD_CTRL | MOD_ALT, VK_CODES["P"]),
}

WIN32_HOTKEYS_AVAILABLE = False
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_APP = 0x8000
PM_NOREMOVE = 0x0000
_HOTKEYMGR_WAKEUP = WM_APP + 1

if sys.platform == "win32":
    try:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class MSG(ctypes.Structure):
            """Win32 MSG structure."""

            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt_x", ctypes.c_long),
                ("pt_y", ctypes.c_long),
            ]

        RegisterHotKey = user32.RegisterHotKey
        RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        RegisterHotKey.restype = wintypes.BOOL

        UnregisterHotKey = user32.UnregisterHotKey
        UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        UnregisterHotKey.restype = wintypes.BOOL

        GetMessageW = user32.GetMessageW
        GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        GetMessageW.restype = wintypes.BOOL

        PeekMessageW = user32.PeekMessageW
        PeekMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        PeekMessageW.restype = wintypes.BOOL

        TranslateMessage = user32.TranslateMessage
        TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
        TranslateMessage.restype = wintypes.BOOL

        DispatchMessageW = user32.DispatchMessageW
        DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
        DispatchMessageW.restype = wintypes.LPARAM

        PostThreadMessageW = user32.PostThreadMessageW
        PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        PostThreadMessageW.restype = wintypes.BOOL

        PostQuitMessage = user32.PostQuitMessage
        PostQuitMessage.argtypes = [ctypes.c_int]
        PostQuitMessage.restype = None

        GetCurrentThreadId = kernel32.GetCurrentThreadId
        GetCurrentThreadId.argtypes = []
        GetCurrentThreadId.restype = wintypes.DWORD

        WIN32_HOTKEYS_AVAILABLE = True
    except Exception as exc:  # pragma: no cover
        logger.warning("Win32 hotkey API import failed (%s). Global hotkeys disabled.", exc)


class HotkeyManager:
    """Register and manage global system hotkeys."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._callbacks: Dict[int, Callable[[], None]] = {}
        self._name_to_id: Dict[str, int] = {}
        self._next_id = 1
        self._request_queue: queue.Queue = queue.Queue()
        self._callback_queue: queue.Queue = queue.Queue()
        self._shutdown = threading.Event()
        self._loop_ready = threading.Event()
        self._thread_id: Optional[int] = None
        self._message_thread: Optional[threading.Thread] = None
        self._callback_thread: Optional[threading.Thread] = None
        self._available = WIN32_HOTKEYS_AVAILABLE

        if not self._available:
            return

        self._callback_thread = threading.Thread(
            target=self._callback_worker,
            name="HotkeyMgr-Dispatch",
            daemon=True,
        )
        self._callback_thread.start()

        self._message_thread = threading.Thread(
            target=self._message_loop,
            name="HotkeyMgr-Loop",
            daemon=True,
        )
        self._message_thread.start()

        if not self._loop_ready.wait(timeout=2.0):
            logger.error("Hotkey message loop failed to start.")
            self._available = False
            self._shutdown.set()
            self._callback_queue.put(None)

    def register(
        self,
        name: str,
        modifiers: int,
        vk: int,
        callback: Callable[[], None],
    ) -> bool:
        """Register or replace a named global hotkey."""
        if not self._available or self._shutdown.is_set():
            return False
        if not callable(callback):
            raise TypeError("callback must be callable")
        return bool(self._invoke("register", name, modifiers, vk, callback))

    def unregister(self, name: str) -> None:
        """Unregister a previously registered hotkey by name."""
        if not self._available or self._shutdown.is_set():
            return
        self._invoke("unregister", name)

    def unregister_all(self) -> None:
        """Unregister all active hotkeys."""
        if not self._available or self._shutdown.is_set():
            return
        self._invoke("unregister_all")

    def shutdown(self) -> None:
        """Stop the message loop and release all registered hotkeys."""
        if self._shutdown.is_set():
            return

        if self._available:
            try:
                self._invoke("shutdown")
            except Exception as exc:
                logger.debug("Hotkey shutdown request failed: %s", exc)
        else:
            self._shutdown.set()

        self._callback_queue.put(None)

        if self._message_thread is not None:
            self._message_thread.join(timeout=2.0)
        if self._callback_thread is not None:
            self._callback_thread.join(timeout=2.0)

    @property
    def available(self) -> bool:
        """Return True when global hotkeys are supported and initialised."""
        return self._available and not self._shutdown.is_set()

    def _invoke(self, action: str, *args: Any) -> Any:
        """Execute a hotkey operation on the message-loop thread."""
        if not self._loop_ready.wait(timeout=2.0):
            logger.error("Hotkey message loop is not ready.")
            return False

        event = threading.Event()
        holder: Dict[str, Any] = {}
        self._request_queue.put((action, args, event, holder))

        if self._thread_id is not None:
            PostThreadMessageW(self._thread_id, _HOTKEYMGR_WAKEUP, 0, 0)

        if not event.wait(timeout=2.0):
            logger.error("Timed out waiting for hotkey action '%s'.", action)
            return False

        if "error" in holder:
            raise holder["error"]
        return holder.get("result")

    def _message_loop(self) -> None:
        """Own the Win32 message queue and hotkey registrations."""
        if not WIN32_HOTKEYS_AVAILABLE:
            return

        msg = MSG()
        PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        self._thread_id = int(GetCurrentThreadId())
        self._loop_ready.set()

        try:
            while True:
                result = GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == -1:
                    err = ctypes.get_last_error()
                    logger.error("GetMessageW failed with error %s.", err)
                    break
                if result == 0:
                    break

                if msg.message == _HOTKEYMGR_WAKEUP:
                    self._drain_requests()
                    continue

                if msg.message == WM_HOTKEY:
                    self._dispatch_hotkey(int(msg.wParam))
                    continue

                TranslateMessage(ctypes.byref(msg))
                DispatchMessageW(ctypes.byref(msg))
        finally:
            self._shutdown.set()
            self._unregister_all_locked()
            self._loop_ready.set()

    def _drain_requests(self) -> None:
        """Process pending API requests on the message-loop thread."""
        while True:
            try:
                action, args, event, holder = self._request_queue.get_nowait()
            except queue.Empty:
                return

            try:
                if action == "register":
                    holder["result"] = self._register_impl(*args)
                elif action == "unregister":
                    self._unregister_impl(*args)
                    holder["result"] = None
                elif action == "unregister_all":
                    self._unregister_all_locked()
                    holder["result"] = None
                elif action == "shutdown":
                    self._shutdown.set()
                    self._unregister_all_locked()
                    holder["result"] = None
                    PostQuitMessage(0)
                else:
                    raise ValueError(f"Unknown hotkey action: {action}")
            except Exception as exc:
                holder["error"] = exc
            finally:
                event.set()

    def _register_impl(
        self,
        name: str,
        modifiers: int,
        vk: int,
        callback: Callable[[], None],
    ) -> bool:
        """Register a hotkey from inside the message-loop thread."""
        with self._lock:
            hotkey_id = self._name_to_id.get(name)
            if hotkey_id is None:
                hotkey_id = self._next_id
                self._next_id += 1
            else:
                UnregisterHotKey(None, hotkey_id)

            if not RegisterHotKey(None, hotkey_id, modifiers, vk):
                err = ctypes.get_last_error()
                logger.warning(
                    "RegisterHotKey failed for %s (modifiers=%s, vk=%s, error=%s).",
                    name,
                    modifiers,
                    vk,
                    err,
                )
                self._name_to_id.pop(name, None)
                self._callbacks.pop(hotkey_id, None)
                return False

            self._name_to_id[name] = hotkey_id
            self._callbacks[hotkey_id] = callback
            return True

    def _unregister_impl(self, name: str) -> None:
        """Unregister a named hotkey from inside the message-loop thread."""
        with self._lock:
            hotkey_id = self._name_to_id.pop(name, None)
            if hotkey_id is None:
                return
            self._callbacks.pop(hotkey_id, None)
            if not UnregisterHotKey(None, hotkey_id):
                err = ctypes.get_last_error()
                logger.debug("UnregisterHotKey failed for %s (error=%s).", name, err)

    def _unregister_all_locked(self) -> None:
        """Unregister every hotkey; must be called on the message-loop thread."""
        with self._lock:
            ids = list(self._name_to_id.items())
            self._name_to_id.clear()
            self._callbacks.clear()

        for name, hotkey_id in ids:
            if not UnregisterHotKey(None, hotkey_id):
                err = ctypes.get_last_error()
                logger.debug("UnregisterHotKey failed for %s (error=%s).", name, err)

    def _dispatch_hotkey(self, hotkey_id: int) -> None:
        """Queue the callback so Win32 message processing stays responsive."""
        with self._lock:
            callback = self._callbacks.get(hotkey_id)

        if callback is not None:
            self._callback_queue.put(callback)

    def _callback_worker(self) -> None:
        """Run hotkey callbacks sequentially on a daemon worker thread."""
        while True:
            try:
                callback = self._callback_queue.get(timeout=0.1)
            except queue.Empty:
                if self._shutdown.is_set():
                    return
                continue

            if callback is None:
                return

            try:
                callback()
            except Exception as exc:  # pragma: no cover
                logger.exception("Hotkey callback failed: %s", exc)

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass
