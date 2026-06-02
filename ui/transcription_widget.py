"""
ui/transcription_widget.py
==========================
Tab widget providing live and file-based speech-to-text transcription.

Features
--------
• Live microphone transcription (Vosk engine, streaming)
• Drag-and-drop audio file transcription (Vosk or Whisper)
• One-click default model download for both engines
• Custom model selection (point to your own model directory/name)
• Copy / save transcript
"""

import logging
import os
import threading
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QMimeData, pyqtSignal, pyqtSlot, QThread, QMetaObject, Q_ARG
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QApplication,
)

from transcription.model_manager import ModelManager

logger = logging.getLogger(__name__)


# ── Background worker for model downloads ──────────────────────────────────────


class _DownloadWorker(QThread):
    """Downloads a model in a background thread."""

    progress = pyqtSignal(str)        # status text
    byte_progress = pyqtSignal(int, int)  # received, total
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, engine: str, model_mgr: ModelManager) -> None:
        super().__init__()
        self._engine = engine
        self._mgr = model_mgr

    def run(self) -> None:
        try:
            if self._engine == "vosk":
                self.progress.emit("Downloading Vosk model…")
                self._mgr.download_vosk_default(
                    progress_cb=lambda recv, total: self.byte_progress.emit(recv, total)
                )
                self.finished.emit(True, "Vosk model downloaded successfully!")
            elif self._engine == "whisper":
                self.progress.emit("Downloading Whisper model…")
                self._mgr.download_whisper_default(
                    progress_cb=lambda msg: self.progress.emit(msg)
                )
                self.finished.emit(True, "Whisper model downloaded successfully!")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class _FileTranscribeWorker(QThread):
    """Transcribes an audio file in a background thread."""

    progress = pyqtSignal(float)       # 0.0 → 1.0
    status = pyqtSignal(str)           # status message
    finished = pyqtSignal(bool, str)   # success, text_or_error

    def __init__(self, audio_path: str, engine: str, model_mgr: ModelManager) -> None:
        super().__init__()
        self._audio_path = audio_path
        self._engine = engine
        self._mgr = model_mgr

    def run(self) -> None:
        try:
            if self._engine == "vosk":
                from transcription.transcriber import VoskTranscriber

                model_path = self._mgr.active_vosk_model()
                if not model_path:
                    self.finished.emit(False, "No Vosk model available. Download one first.")
                    return
                t = VoskTranscriber(str(model_path))
                text = t.transcribe_file(
                    self._audio_path,
                    progress_cb=lambda p: self.progress.emit(p),
                )
            else:  # whisper
                from transcription.transcriber import WhisperTranscriber

                model_name = self._mgr.active_whisper_model()
                model_dir = str(self._mgr.whisper_model_dir())
                t = WhisperTranscriber(model_name, model_dir)
                text = t.transcribe_file(
                    self._audio_path,
                    progress_cb=lambda msg: self.status.emit(msg),
                )

            self.finished.emit(True, text)
        except Exception as exc:
            logger.exception("Transcription failed")
            self.finished.emit(False, str(exc))


# ── Main widget ────────────────────────────────────────────────────────────────

_SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".wma", ".aac", ".opus",
}


class TranscriptionWidget(QWidget):
    """
    Full-featured transcription tab.

    Sections
    --------
    1. Model management (download defaults / point to custom)
    2. Live transcription (start/stop, partial + final output)
    3. File transcription (drag-and-drop or browse, engine selector)
    """

    def __init__(self, colours: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._colours = colours
        self._model_mgr = ModelManager()
        self._vosk_transcriber: Optional[object] = None
        self._download_worker: Optional[_DownloadWorker] = None
        self._file_worker: Optional[_FileTranscribeWorker] = None
        self._build_ui()
        self._refresh_status()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Model management section ──
        model_group = QGroupBox("Models")
        mg_layout = QVBoxLayout(model_group)

        # Status row
        status_row = QHBoxLayout()
        self._lbl_vosk_status = QLabel("Vosk: checking…")
        self._lbl_whisper_status = QLabel("Whisper: checking…")
        status_row.addWidget(self._lbl_vosk_status)
        status_row.addWidget(self._lbl_whisper_status)
        status_row.addStretch()
        mg_layout.addLayout(status_row)

        # Download / custom buttons row
        btn_row = QHBoxLayout()

        self._btn_dl_vosk = QPushButton("⬇ Download Vosk Default (~128 MB)")
        self._btn_dl_vosk.clicked.connect(lambda: self._download_model("vosk"))
        btn_row.addWidget(self._btn_dl_vosk)

        self._btn_dl_whisper = QPushButton("⬇ Download Whisper Default (~488 MB)")
        self._btn_dl_whisper.clicked.connect(lambda: self._download_model("whisper"))
        btn_row.addWidget(self._btn_dl_whisper)

        btn_row.addStretch()

        self._btn_custom_vosk = QPushButton("📂 Use Own Vosk Model")
        self._btn_custom_vosk.clicked.connect(self._select_custom_vosk)
        btn_row.addWidget(self._btn_custom_vosk)

        self._btn_custom_whisper = QPushButton("📂 Use Own Whisper Model")
        self._btn_custom_whisper.clicked.connect(self._select_custom_whisper)
        btn_row.addWidget(self._btn_custom_whisper)

        mg_layout.addLayout(btn_row)

        # Download progress
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        mg_layout.addWidget(self._progress_bar)

        self._lbl_dl_status = QLabel("")
        self._lbl_dl_status.setVisible(False)
        mg_layout.addWidget(self._lbl_dl_status)

        layout.addWidget(model_group)

        # ── Live transcription section ──
        live_group = QGroupBox("Live Transcription (Vosk)")
        lg_layout = QVBoxLayout(live_group)

        live_btn_row = QHBoxLayout()
        self._btn_live_start = QPushButton("🎙 Start Live Transcription")
        self._btn_live_start.clicked.connect(self._toggle_live)
        live_btn_row.addWidget(self._btn_live_start)

        self._lbl_live_status = QLabel("Stopped")
        self._lbl_live_status.setObjectName("lbl_status_inactive")
        live_btn_row.addWidget(self._lbl_live_status)
        live_btn_row.addStretch()

        self._btn_clear_live = QPushButton("Clear")
        self._btn_clear_live.clicked.connect(lambda: self._txt_live.clear())
        live_btn_row.addWidget(self._btn_clear_live)

        self._btn_copy_live = QPushButton("📋 Copy")
        self._btn_copy_live.clicked.connect(
            lambda: QApplication.clipboard().setText(self._txt_live.toPlainText())
        )
        live_btn_row.addWidget(self._btn_copy_live)

        lg_layout.addLayout(live_btn_row)

        self._txt_live = QPlainTextEdit()
        self._txt_live.setReadOnly(True)
        self._txt_live.setPlaceholderText(
            "Live transcription output will appear here…"
        )
        self._txt_live.setObjectName("log_panel")
        lg_layout.addWidget(self._txt_live)

        layout.addWidget(live_group)

        # ── File transcription section ──
        file_group = QGroupBox("File Transcription (drag & drop or browse)")
        fg_layout = QVBoxLayout(file_group)

        file_ctrl_row = QHBoxLayout()

        self._btn_browse = QPushButton("📂 Browse Audio File")
        self._btn_browse.clicked.connect(self._browse_file)
        file_ctrl_row.addWidget(self._btn_browse)

        file_ctrl_row.addWidget(QLabel("Engine:"))
        self._cmb_engine = QComboBox()
        self._cmb_engine.addItems(["Vosk", "Whisper"])
        file_ctrl_row.addWidget(self._cmb_engine)

        file_ctrl_row.addStretch()

        self._btn_clear_file = QPushButton("Clear")
        self._btn_clear_file.clicked.connect(lambda: self._txt_file.clear())
        file_ctrl_row.addWidget(self._btn_clear_file)

        self._btn_copy_file = QPushButton("📋 Copy")
        self._btn_copy_file.clicked.connect(
            lambda: QApplication.clipboard().setText(self._txt_file.toPlainText())
        )
        file_ctrl_row.addWidget(self._btn_copy_file)

        self._btn_save_file = QPushButton("💾 Save")
        self._btn_save_file.clicked.connect(self._save_transcript)
        file_ctrl_row.addWidget(self._btn_save_file)

        fg_layout.addLayout(file_ctrl_row)

        # File progress
        self._file_progress = QProgressBar()
        self._file_progress.setVisible(False)
        fg_layout.addWidget(self._file_progress)

        # Drop zone / transcript output
        self._txt_file = QPlainTextEdit()
        self._txt_file.setReadOnly(True)
        self._txt_file.setPlaceholderText(
            "Drop an audio file here or click Browse to transcribe…\n\n"
            "Supported formats: WAV, MP3, FLAC, OGG, M4A, WMA, AAC, OPUS"
        )
        self._txt_file.setObjectName("log_panel")
        self._txt_file.setMinimumHeight(120)
        fg_layout.addWidget(self._txt_file)

        layout.addWidget(file_group)

    # ── Status refresh ─────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        if self._model_mgr.is_vosk_ready():
            active = self._model_mgr.active_vosk_model()
            self._lbl_vosk_status.setText(f"✅ Vosk: Ready ({active})")
            self._lbl_vosk_status.setStyleSheet(f"color: {self._colours.get('success', '#3fb950')};")
            self._btn_dl_vosk.setText("✅ Vosk Downloaded")
        else:
            self._lbl_vosk_status.setText("❌ Vosk: Not downloaded")
            self._lbl_vosk_status.setStyleSheet(f"color: {self._colours.get('danger', '#f85149')};")

        if self._model_mgr.is_whisper_ready():
            model = self._model_mgr.active_whisper_model()
            self._lbl_whisper_status.setText(f"✅ Whisper: Ready ({model})")
            self._lbl_whisper_status.setStyleSheet(f"color: {self._colours.get('success', '#3fb950')};")
            self._btn_dl_whisper.setText("✅ Whisper Downloaded")
        else:
            self._lbl_whisper_status.setText("❌ Whisper: Not downloaded")
            self._lbl_whisper_status.setStyleSheet(f"color: {self._colours.get('danger', '#f85149')};")

    # ── Model download ─────────────────────────────────────────────────────

    def _download_model(self, engine: str) -> None:
        if self._download_worker and self._download_worker.isRunning():
            QMessageBox.information(self, "Download in progress", "A download is already running.")
            return

        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_bar.setMaximum(0)  # Indeterminate initially
        self._lbl_dl_status.setVisible(True)
        self._lbl_dl_status.setText(f"Starting {engine} download…")

        self._download_worker = _DownloadWorker(engine, self._model_mgr)
        self._download_worker.progress.connect(self._on_dl_progress)
        self._download_worker.byte_progress.connect(self._on_dl_bytes)
        self._download_worker.finished.connect(self._on_dl_finished)
        self._download_worker.start()

    def _on_dl_progress(self, msg: str) -> None:
        self._lbl_dl_status.setText(msg)

    def _on_dl_bytes(self, received: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(received)
            mb_recv = received / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self._lbl_dl_status.setText(f"Downloading… {mb_recv:.1f} / {mb_total:.1f} MB")
        else:
            self._progress_bar.setMaximum(0)

    def _on_dl_finished(self, success: bool, message: str) -> None:
        self._progress_bar.setVisible(False)
        if success:
            self._lbl_dl_status.setText(f"✅ {message}")
            self._lbl_dl_status.setStyleSheet(f"color: {self._colours.get('success', '#3fb950')};")
        else:
            self._lbl_dl_status.setText(f"❌ {message}")
            self._lbl_dl_status.setStyleSheet(f"color: {self._colours.get('danger', '#f85149')};")
        self._refresh_status()

    # ── Custom model selection ─────────────────────────────────────────────

    def _select_custom_vosk(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Vosk Model Directory"
        )
        if not path:
            return
        try:
            self._model_mgr.set_custom_vosk_model(path)
            QMessageBox.information(self, "Custom Vosk Model", f"Model set to:\n{path}")
            self._refresh_status()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Model", str(exc))

    def _select_custom_whisper(self) -> None:
        # Allow entering a model name or selecting a .pt file
        name, ok = QFileDialog.getOpenFileName(
            self,
            "Select Whisper Model (.pt file) or Cancel to enter a name",
            "",
            "Whisper Models (*.pt);;All Files (*)",
        )
        if name:
            self._model_mgr.set_custom_whisper_model(name)
            QMessageBox.information(self, "Custom Whisper Model", f"Model set to:\n{name}")
            self._refresh_status()
            return

        # Fall back to text input for model name
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self,
            "Whisper Model Name",
            "Enter a Whisper model name (e.g. 'medium', 'large-v3'):",
        )
        if ok and name.strip():
            self._model_mgr.set_custom_whisper_model(name.strip())
            QMessageBox.information(
                self, "Custom Whisper Model", f"Model set to: {name.strip()}"
            )
            self._refresh_status()

    # ── Live transcription ─────────────────────────────────────────────────

    def _toggle_live(self) -> None:
        if self._vosk_transcriber and self._vosk_transcriber.is_live:
            self._stop_live()
        else:
            self._start_live()

    def _start_live(self) -> None:
        model_path = self._model_mgr.active_vosk_model()
        if not model_path:
            QMessageBox.warning(
                self,
                "No Vosk Model",
                "Please download the default Vosk model or select a custom one first.",
            )
            return

        try:
            from transcription.transcriber import VoskTranscriber

            self._vosk_transcriber = VoskTranscriber(str(model_path))
            self._vosk_transcriber.start_live(
                on_partial=self._on_live_partial,
                on_result=self._on_live_result,
            )

            self._btn_live_start.setText("⏹ Stop Live Transcription")
            self._lbl_live_status.setText("● Listening…")
            self._lbl_live_status.setObjectName("lbl_status_active")
            self._lbl_live_status.setStyleSheet(
                f"color: {self._colours.get('success', '#3fb950')}; font-weight: bold;"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not start live transcription:\n{exc}")

    def _stop_live(self) -> None:
        if self._vosk_transcriber:
            self._vosk_transcriber.stop_live()

        self._btn_live_start.setText("🎙 Start Live Transcription")
        self._lbl_live_status.setText("Stopped")
        self._lbl_live_status.setObjectName("lbl_status_inactive")
        self._lbl_live_status.setStyleSheet(
            f"color: {self._colours.get('text_secondary', '#8b949e')};"
        )

    def _on_live_partial(self, text: str) -> None:
        # Update the last line with partial text (shown in grey)
        from PyQt5.QtCore import QMetaObject, Qt as QtConst, Q_ARG
        QMetaObject.invokeMethod(
            self, "_append_partial", QtConst.QueuedConnection, Q_ARG(str, text)
        )

    def _on_live_result(self, text: str) -> None:
        from PyQt5.QtCore import QMetaObject, Qt as QtConst, Q_ARG
        QMetaObject.invokeMethod(
            self, "_append_result", QtConst.QueuedConnection, Q_ARG(str, text)
        )

    @pyqtSlot(str)
    def _append_partial(self, text: str) -> None:
        """Replace the last line with partial text (called on GUI thread)."""
        cursor = self._txt_live.textCursor()
        cursor.movePosition(cursor.End)
        # Move to start of last line
        cursor.movePosition(cursor.StartOfBlock, cursor.KeepAnchor)
        selected = cursor.selectedText()
        # Only replace if the last line looks like a partial (starts with …)
        if selected.startswith("…"):
            cursor.removeSelectedText()
        else:
            cursor.movePosition(cursor.End)
            if self._txt_live.toPlainText():
                cursor.insertText("\n")
        cursor.insertText(f"…{text}")
        self._txt_live.setTextCursor(cursor)
        self._txt_live.ensureCursorVisible()

    @pyqtSlot(str)
    def _append_result(self, text: str) -> None:
        """Append a finalized sentence (called on GUI thread)."""
        cursor = self._txt_live.textCursor()
        cursor.movePosition(cursor.End)
        # Remove partial line if present
        cursor.movePosition(cursor.StartOfBlock, cursor.KeepAnchor)
        if cursor.selectedText().startswith("…"):
            cursor.removeSelectedText()
        else:
            cursor.movePosition(cursor.End)
            if self._txt_live.toPlainText():
                cursor.insertText("\n")
        cursor.insertText(text)
        self._txt_live.setTextCursor(cursor)
        self._txt_live.ensureCursorVisible()

    # ── File transcription ─────────────────────────────────────────────────

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            "",
            "Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a *.wma *.aac *.opus);;All Files (*)",
        )
        if path:
            self._transcribe_file(path)

    def _transcribe_file(self, audio_path: str) -> None:
        if self._file_worker and self._file_worker.isRunning():
            QMessageBox.information(
                self, "In Progress", "A transcription is already in progress."
            )
            return

        engine = self._cmb_engine.currentText().lower()

        self._file_progress.setVisible(True)
        self._file_progress.setValue(0)
        self._file_progress.setMaximum(100)
        self._txt_file.setPlainText(f"Transcribing: {os.path.basename(audio_path)}…\n")

        self._file_worker = _FileTranscribeWorker(audio_path, engine, self._model_mgr)
        self._file_worker.progress.connect(
            lambda p: self._file_progress.setValue(int(p * 100))
        )
        self._file_worker.status.connect(
            lambda msg: self._txt_file.appendPlainText(msg)
        )
        self._file_worker.finished.connect(self._on_file_finished)
        self._file_worker.start()

    def _on_file_finished(self, success: bool, text: str) -> None:
        self._file_progress.setVisible(False)
        if success:
            self._txt_file.setPlainText(text)
        else:
            self._txt_file.appendPlainText(f"\n❌ Error: {text}")

    def _save_transcript(self) -> None:
        text = self._txt_file.toPlainText()
        if not text.strip():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Transcript", "transcript.txt", "Text Files (*.txt);;All Files (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    # ── Drag and drop ──────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = Path(url.toLocalFile()).suffix.lower()
                    if ext in _SUPPORTED_AUDIO_EXTENSIONS:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                ext = Path(path).suffix.lower()
                if ext in _SUPPORTED_AUDIO_EXTENSIONS:
                    self._transcribe_file(path)
                    return

    # ── Cleanup ────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Stop any running transcription (call on window close)."""
        if self._vosk_transcriber and self._vosk_transcriber.is_live:
            self._vosk_transcriber.stop_live()
