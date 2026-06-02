"""
transcription/model_manager.py
==============================
Manages downloading, verifying, and locating speech recognition models
for both Vosk and Whisper engines.

Default models chosen for best accuracy under 1 GB:
  • Vosk:    vosk-model-en-us-0.22-lgraph  (~128 MB)
  • Whisper: small                         (~488 MB)

Download URLs are resolved through a manifest so that if upstream links
change, only the manifest needs updating — not the application code.
"""

import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

_APP_VERSION = "2.0.0"


_APP_DIR_NAME = "multi-output-audio"


def _models_root() -> Path:
    """Return the root directory for all downloaded models."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / _APP_DIR_NAME / "models"


MODELS_ROOT = _models_root()

# ── Manifest (resilient URL registry) ──────────────────────────────────────────

# The manifest maps a model key to a list of candidate download URLs.
# The first URL that succeeds is used.  If upstream changes a link the user
# can edit manifest.json or we can ship an updated one.

_BUILTIN_MANIFEST: Dict[str, Any] = {
    "vosk_default": {
        "display_name": "Vosk English (US) — lgraph",
        "engine": "vosk",
        "size_mb": 128,
        "urls": [
            "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22-lgraph.zip",
            "https://github.com/alphacep/vosk-api/releases/download/v0.3.45/vosk-model-en-us-0.22-lgraph.zip",
        ],
        "strip_root": True,
        "sha256": None,  # Populated at build time if needed
    },
    "whisper_default": {
        "display_name": "Whisper small (multilingual)",
        "engine": "whisper",
        "model_name": "small",
        "size_mb": 488,
        "urls": [],  # Whisper downloads via its own API
    },
}

_MANIFEST_FILENAME = "model_manifest.json"


def _manifest_path() -> Path:
    return MODELS_ROOT / _MANIFEST_FILENAME


def _load_manifest() -> Dict[str, Any]:
    """Load the on-disk manifest, falling back to the built-in one."""
    p = _manifest_path()
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            logger.warning("Corrupt manifest — falling back to built-in.")
    return dict(_BUILTIN_MANIFEST)


def _save_manifest(manifest: Dict[str, Any]) -> None:
    MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    with open(_manifest_path(), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


# ── Download helpers ───────────────────────────────────────────────────────────


def _download_file(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Download *url* to *dest* with optional progress callback(received, total)."""
    req = Request(url, headers={"User-Agent": f"MultiOutputAudioConsole/{_APP_VERSION}"})
    with urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        dest.parent.mkdir(parents=True, exist_ok=True)
        received = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = resp.read(1 << 17)  # 128 KiB
                if not chunk:
                    break
                fh.write(chunk)
                received += len(chunk)
                if progress_cb:
                    progress_cb(received, total)
    logger.info("Downloaded %s → %s (%d bytes)", url, dest, received)


def _verify_sha256(path: Path, expected: Optional[str]) -> bool:
    if not expected:
        return True
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 17), b""):
            h.update(block)
    return h.hexdigest() == expected


def _extract_zip(zip_path: Path, dest_dir: Path, strip_root: bool = True) -> Path:
    """Extract a zip, optionally stripping the single top-level directory."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    if strip_root:
        entries = list(dest_dir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
    return dest_dir


# ── Public API ─────────────────────────────────────────────────────────────────


class ModelManager:
    """
    High-level interface for downloading, locating, and managing
    transcription models.
    """

    def __init__(self) -> None:
        self._manifest = _load_manifest()
        # Ensure manifest is persisted with defaults the first time
        if not _manifest_path().is_file():
            _save_manifest(self._manifest)

    # ── queries ──

    def models_root(self) -> Path:
        return MODELS_ROOT

    def vosk_model_dir(self) -> Path:
        return MODELS_ROOT / "vosk"

    def whisper_model_dir(self) -> Path:
        return MODELS_ROOT / "whisper"

    def is_vosk_ready(self) -> bool:
        """True when a usable Vosk model directory exists."""
        d = self.vosk_model_dir()
        # A valid Vosk model contains at least an 'am' or 'graph' sub-dir
        return d.is_dir() and any(
            (d / sub).exists() for sub in ("am", "graph", "conf")
        )

    def is_whisper_ready(self) -> bool:
        """True when the default Whisper model has been downloaded."""
        entry = self._manifest.get("whisper_default", {})
        model_name = entry.get("model_name", "small")
        # Whisper caches to ~/.cache/whisper by default;
        # check both custom dir and default cache
        custom = self.whisper_model_dir() / f"{model_name}.pt"
        default_cache = Path.home() / ".cache" / "whisper" / f"{model_name}.pt"
        return custom.is_file() or default_cache.is_file()

    def custom_vosk_model_path(self) -> Optional[Path]:
        """Return a custom Vosk model path if the user has configured one."""
        custom = self._manifest.get("vosk_custom", {}).get("path")
        if custom and Path(custom).is_dir():
            return Path(custom)
        return None

    def active_vosk_model(self) -> Optional[Path]:
        """Return the active Vosk model directory (custom or default)."""
        custom = self.custom_vosk_model_path()
        if custom:
            return custom
        if self.is_vosk_ready():
            return self.vosk_model_dir()
        return None

    def active_whisper_model(self) -> str:
        """Return the Whisper model name to use."""
        custom = self._manifest.get("whisper_custom", {}).get("model_name")
        if custom:
            return custom
        return self._manifest.get("whisper_default", {}).get("model_name", "small")

    # ── downloads ──

    def download_vosk_default(
        self,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """
        Download and extract the default Vosk model.
        Returns the model directory path on success.
        Raises RuntimeError on failure.
        """
        entry = self._manifest["vosk_default"]
        dest_dir = self.vosk_model_dir()

        # Try each URL in order
        last_error: Optional[Exception] = None
        for url in entry["urls"]:
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    zip_path = Path(tmp) / "vosk_model.zip"
                    _download_file(url, zip_path, progress_cb)

                    if not _verify_sha256(zip_path, entry.get("sha256")):
                        logger.warning("SHA-256 mismatch for %s — trying next URL", url)
                        continue

                    # Clean previous install
                    if dest_dir.exists():
                        shutil.rmtree(dest_dir)
                    dest_dir.mkdir(parents=True, exist_ok=True)

                    extracted = _extract_zip(
                        zip_path, dest_dir, entry.get("strip_root", True)
                    )

                    # If strip_root moved contents into a sub-dir, relocate
                    if extracted != dest_dir:
                        for item in extracted.iterdir():
                            shutil.move(str(item), str(dest_dir / item.name))
                        if extracted.exists():
                            shutil.rmtree(extracted)

                logger.info("Vosk model ready at %s", dest_dir)
                return dest_dir

            except Exception as exc:
                last_error = exc
                logger.warning("Failed to download from %s: %s", url, exc)

        raise RuntimeError(
            f"Could not download Vosk model from any URL. Last error: {last_error}"
        )

    def download_whisper_default(
        self,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Download the default Whisper model via the whisper library.
        Returns the model name on success.
        """
        try:
            import whisper  # noqa: F811
        except ImportError:
            raise RuntimeError(
                "The 'openai-whisper' package is not installed.\n"
                "Install it with:  pip install openai-whisper"
            )

        model_name = self._manifest.get("whisper_default", {}).get("model_name", "small")
        cache_dir = str(self.whisper_model_dir())
        os.makedirs(cache_dir, exist_ok=True)

        if progress_cb:
            progress_cb(f"Downloading Whisper '{model_name}' model…")

        # whisper._download handles caching and resumption internally
        whisper.load_model(model_name, download_root=cache_dir)

        logger.info("Whisper model '%s' ready in %s", model_name, cache_dir)
        return model_name

    # ── custom model support ──

    def set_custom_vosk_model(self, path: str) -> None:
        """Point to a user-supplied Vosk model directory."""
        p = Path(path)
        if not p.is_dir():
            raise ValueError(f"Not a valid directory: {path}")
        # Basic sanity check
        if not any((p / sub).exists() for sub in ("am", "graph", "conf")):
            raise ValueError(
                f"Directory does not look like a Vosk model (missing am/graph/conf): {path}"
            )
        self._manifest["vosk_custom"] = {"path": str(p.resolve())}
        _save_manifest(self._manifest)
        logger.info("Custom Vosk model set: %s", path)

    def clear_custom_vosk_model(self) -> None:
        self._manifest.pop("vosk_custom", None)
        _save_manifest(self._manifest)

    def set_custom_whisper_model(self, model_name_or_path: str) -> None:
        """
        Set a custom Whisper model.  Can be a model name (e.g. 'medium',
        'large-v3') or a filesystem path to a .pt file.
        """
        self._manifest["whisper_custom"] = {"model_name": model_name_or_path}
        _save_manifest(self._manifest)
        logger.info("Custom Whisper model set: %s", model_name_or_path)

    def clear_custom_whisper_model(self) -> None:
        self._manifest.pop("whisper_custom", None)
        _save_manifest(self._manifest)

    # ── manifest maintenance ──

    def update_manifest_url(self, model_key: str, urls: List[str]) -> None:
        """Replace download URLs for a model entry (resilient link update)."""
        if model_key not in self._manifest:
            raise KeyError(f"Unknown model key: {model_key}")
        self._manifest[model_key]["urls"] = urls
        _save_manifest(self._manifest)

    def reload_manifest(self) -> None:
        self._manifest = _load_manifest()

    def get_manifest(self) -> Dict[str, Any]:
        return dict(self._manifest)
