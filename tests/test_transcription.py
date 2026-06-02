"""
tests/test_transcription.py
============================
Unit tests for transcription model_manager and transcriber modules.

These tests avoid network calls and heavy model loading by mocking
the external libraries (vosk, whisper).
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# ── ModelManager tests ─────────────────────────────────────────────────────────


class TestModelManager:
    """Tests for transcription.model_manager.ModelManager."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        # Patch MODELS_ROOT to temp dir
        self._patcher = mock.patch(
            "transcription.model_manager.MODELS_ROOT",
            Path(self._tmpdir),
        )
        self._patcher.start()
        # Also patch the function so new instances pick it up
        self._patcher2 = mock.patch(
            "transcription.model_manager._models_root",
            return_value=Path(self._tmpdir),
        )
        self._patcher2.start()

    def teardown_method(self):
        self._patcher.stop()
        self._patcher2.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_mgr(self):
        from transcription.model_manager import ModelManager
        return ModelManager()

    def test_models_root_returns_path(self):
        mgr = self._make_mgr()
        assert mgr.models_root() == Path(self._tmpdir)

    def test_vosk_not_ready_when_empty(self):
        mgr = self._make_mgr()
        assert not mgr.is_vosk_ready()

    def test_vosk_ready_with_conf_dir(self):
        vosk_dir = Path(self._tmpdir) / "vosk"
        vosk_dir.mkdir()
        (vosk_dir / "conf").mkdir()
        mgr = self._make_mgr()
        assert mgr.is_vosk_ready()

    def test_vosk_ready_with_am_dir(self):
        vosk_dir = Path(self._tmpdir) / "vosk"
        vosk_dir.mkdir()
        (vosk_dir / "am").mkdir()
        mgr = self._make_mgr()
        assert mgr.is_vosk_ready()

    def test_active_vosk_model_default(self):
        vosk_dir = Path(self._tmpdir) / "vosk"
        vosk_dir.mkdir()
        (vosk_dir / "graph").mkdir()
        mgr = self._make_mgr()
        assert mgr.active_vosk_model() == vosk_dir

    def test_set_custom_vosk_model(self):
        custom = Path(self._tmpdir) / "custom_vosk"
        custom.mkdir()
        (custom / "am").mkdir()
        mgr = self._make_mgr()
        mgr.set_custom_vosk_model(str(custom))
        assert mgr.custom_vosk_model_path() == custom
        assert mgr.active_vosk_model() == custom

    def test_set_custom_vosk_model_invalid_dir(self):
        mgr = self._make_mgr()
        with pytest.raises(ValueError, match="Not a valid directory"):
            mgr.set_custom_vosk_model("/nonexistent/path")

    def test_set_custom_vosk_model_missing_structure(self):
        bad = Path(self._tmpdir) / "bad_model"
        bad.mkdir()
        mgr = self._make_mgr()
        with pytest.raises(ValueError, match="does not look like a Vosk model"):
            mgr.set_custom_vosk_model(str(bad))

    def test_clear_custom_vosk_model(self):
        custom = Path(self._tmpdir) / "custom_vosk"
        custom.mkdir()
        (custom / "conf").mkdir()
        mgr = self._make_mgr()
        mgr.set_custom_vosk_model(str(custom))
        mgr.clear_custom_vosk_model()
        assert mgr.custom_vosk_model_path() is None

    def test_set_custom_whisper_model(self):
        mgr = self._make_mgr()
        mgr.set_custom_whisper_model("medium")
        assert mgr.active_whisper_model() == "medium"

    def test_clear_custom_whisper_model(self):
        mgr = self._make_mgr()
        mgr.set_custom_whisper_model("large-v3")
        mgr.clear_custom_whisper_model()
        assert mgr.active_whisper_model() == "small"  # default

    def test_manifest_persisted_on_first_run(self):
        mgr = self._make_mgr()
        manifest_path = Path(self._tmpdir) / "model_manifest.json"
        assert manifest_path.is_file()
        data = json.loads(manifest_path.read_text())
        assert "vosk_default" in data
        assert "whisper_default" in data

    def test_update_manifest_url(self):
        mgr = self._make_mgr()
        new_urls = ["https://example.com/model.zip"]
        mgr.update_manifest_url("vosk_default", new_urls)
        manifest = mgr.get_manifest()
        assert manifest["vosk_default"]["urls"] == new_urls

    def test_update_manifest_url_unknown_key(self):
        mgr = self._make_mgr()
        with pytest.raises(KeyError):
            mgr.update_manifest_url("nonexistent", [])

    def test_whisper_not_ready_when_empty(self):
        mgr = self._make_mgr()
        assert not mgr.is_whisper_ready()

    def test_whisper_ready_with_model_file(self):
        whisper_dir = Path(self._tmpdir) / "whisper"
        whisper_dir.mkdir()
        (whisper_dir / "small.pt").touch()
        mgr = self._make_mgr()
        assert mgr.is_whisper_ready()


# ── VoskTranscriber tests ──────────────────────────────────────────────────────


class TestVoskTranscriber:
    """Tests for transcription.transcriber.VoskTranscriber (mocked)."""

    @mock.patch("transcription.transcriber.VoskTranscriber.__init__", return_value=None)
    def test_is_live_default_false(self, mock_init):
        from transcription.transcriber import VoskTranscriber
        t = VoskTranscriber.__new__(VoskTranscriber)
        t._running = False
        assert not t.is_live

    @mock.patch("transcription.transcriber.VoskTranscriber.__init__", return_value=None)
    def test_is_live_true_when_running(self, mock_init):
        from transcription.transcriber import VoskTranscriber
        t = VoskTranscriber.__new__(VoskTranscriber)
        t._running = True
        assert t.is_live


# ── WhisperTranscriber tests ──────────────────────────────────────────────────


class TestWhisperTranscriber:
    """Tests for transcription.transcriber.WhisperTranscriber (mocked)."""

    @mock.patch.dict("sys.modules", {"whisper": mock.MagicMock()})
    def test_init_stores_model_name(self):
        from transcription.transcriber import WhisperTranscriber
        t = WhisperTranscriber(model_name="medium", model_dir="/tmp/models")
        assert t._model_name == "medium"
        assert t._model_dir == "/tmp/models"
        assert t._model is None  # Not loaded yet

    @mock.patch.dict("sys.modules", {"whisper": mock.MagicMock()})
    def test_transcribe_file_calls_whisper(self):
        import sys
        mock_whisper = sys.modules["whisper"]
        mock_model = mock.MagicMock()
        mock_model.transcribe.return_value = {"text": "hello world"}
        mock_whisper.load_model.return_value = mock_model

        from transcription.transcriber import WhisperTranscriber
        t = WhisperTranscriber(model_name="small")
        result = t.transcribe_file("/tmp/test.wav")
        assert result == "hello world"
        mock_model.transcribe.assert_called_once()
