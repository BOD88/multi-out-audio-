"""
transcription/transcriber.py
============================
Speech-to-text engines wrapping Vosk (live + file) and Whisper (file).

VoskTranscriber
    • Live microphone streaming with partial/final results
    • Audio file transcription (WAV, FLAC, MP3, OGG, etc.)

WhisperTranscriber
    • Offline file transcription with high accuracy
"""

import json
import logging
import os
import queue
import threading
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Vosk ───────────────────────────────────────────────────────────────────────


class VoskTranscriber:
    """
    Real-time and batch speech-to-text using Vosk.

    Parameters
    ----------
    model_path : str or Path
        Directory containing the Vosk model.
    sample_rate : int
        Audio sample rate (default 16000).
    """

    def __init__(self, model_path: str, sample_rate: int = 16_000) -> None:
        try:
            from vosk import Model, KaldiRecognizer, SetLogLevel  # noqa: F811
        except ImportError:
            raise RuntimeError(
                "The 'vosk' package is not installed.\n"
                "Install it with:  pip install vosk"
            )

        SetLogLevel(-1)  # Suppress Vosk's own logging
        self._sample_rate = sample_rate
        self._model = Model(str(model_path))
        self._recognizer: Optional[object] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stream = None

    # ── live transcription ──

    def start_live(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_result: Optional[Callable[[str], None]] = None,
        device_index: Optional[int] = None,
    ) -> None:
        """
        Begin live microphone transcription.

        Callbacks
        ---------
        on_partial : called with partial (interim) text
        on_result  : called with finalised sentence text
        """
        if self._running:
            return

        import sounddevice as sd
        from vosk import KaldiRecognizer

        self._recognizer = KaldiRecognizer(self._model, self._sample_rate)
        self._running = True

        def _audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug("Sounddevice status: %s", status)
            self._audio_queue.put(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=self._sample_rate,
            blocksize=4096,
            dtype="int16",
            channels=1,
            device=device_index,
            callback=_audio_callback,
        )
        self._stream.start()

        def _process():
            while self._running:
                try:
                    data = self._audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if self._recognizer.AcceptWaveform(data):
                    result = json.loads(self._recognizer.Result())
                    text = result.get("text", "").strip()
                    if text and on_result:
                        on_result(text)
                else:
                    partial = json.loads(self._recognizer.PartialResult())
                    text = partial.get("partial", "").strip()
                    if text and on_partial:
                        on_partial(text)

            # Flush final
            if self._recognizer:
                final = json.loads(self._recognizer.FinalResult())
                text = final.get("text", "").strip()
                if text and on_result:
                    on_result(text)

        self._thread = threading.Thread(target=_process, daemon=True)
        self._thread.start()
        logger.info("Vosk live transcription started")

    def stop_live(self) -> None:
        """Stop live microphone transcription."""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        # Drain the queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        logger.info("Vosk live transcription stopped")

    @property
    def is_live(self) -> bool:
        return self._running

    # ── file transcription ──

    def transcribe_file(
        self,
        audio_path: str,
        progress_cb: Optional[Callable[[float], None]] = None,
    ) -> str:
        """
        Transcribe an audio file and return the full text.

        Supports WAV, FLAC, MP3, OGG, etc. (via soundfile).
        progress_cb receives values 0.0 → 1.0.
        """
        import soundfile as sf
        from vosk import KaldiRecognizer

        info = sf.info(audio_path)
        total_frames = info.frames
        recognizer = KaldiRecognizer(self._model, self._sample_rate)

        results: list = []
        processed = 0
        block = 4096

        with sf.SoundFile(audio_path) as f:
            # Resample to mono 16kHz int16 if needed
            while True:
                data = f.read(block, dtype="int16")
                if len(data) == 0:
                    break

                # Convert to mono if stereo
                if data.ndim > 1:
                    data = data.mean(axis=1).astype(np.int16)

                # Resample if needed
                if int(info.samplerate) != self._sample_rate:
                    ratio = self._sample_rate / info.samplerate
                    indices = np.round(
                        np.arange(0, len(data), 1.0 / ratio)
                    ).astype(int)
                    indices = indices[indices < len(data)]
                    data = data[indices]

                if recognizer.AcceptWaveform(data.tobytes()):
                    r = json.loads(recognizer.Result())
                    text = r.get("text", "").strip()
                    if text:
                        results.append(text)

                processed += block
                if progress_cb and total_frames > 0:
                    progress_cb(min(processed / total_frames, 1.0))

        # Final flush
        final = json.loads(recognizer.FinalResult())
        text = final.get("text", "").strip()
        if text:
            results.append(text)

        if progress_cb:
            progress_cb(1.0)

        return " ".join(results)


# ── Whisper ────────────────────────────────────────────────────────────────────


class WhisperTranscriber:
    """
    Batch audio file transcription using OpenAI Whisper.

    Parameters
    ----------
    model_name : str
        Whisper model name or path (e.g. 'small', 'medium', '/path/to/model.pt').
    model_dir : str or None
        Custom download/cache directory for Whisper weights.
    """

    def __init__(self, model_name: str = "small", model_dir: Optional[str] = None) -> None:
        try:
            import whisper  # noqa: F811
        except ImportError:
            raise RuntimeError(
                "The 'openai-whisper' package is not installed.\n"
                "Install it with:  pip install openai-whisper"
            )
        self._model_name = model_name
        self._model_dir = model_dir
        self._model = None  # Lazy-loaded

    def _ensure_model(self) -> None:
        if self._model is None:
            import whisper
            kwargs = {}
            if self._model_dir:
                kwargs["download_root"] = self._model_dir
            self._model = whisper.load_model(self._model_name, **kwargs)

    def transcribe_file(
        self,
        audio_path: str,
        language: Optional[str] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Transcribe an audio file and return the full text.

        Parameters
        ----------
        audio_path : str
            Path to audio file (WAV, MP3, FLAC, OGG, etc.)
        language : str, optional
            Language code (e.g. 'en'). Auto-detected if None.
        progress_cb : callable, optional
            Status message callback.
        """
        if progress_cb:
            progress_cb("Loading Whisper model…")
        self._ensure_model()

        if progress_cb:
            progress_cb("Transcribing…")

        options = {}
        if language:
            options["language"] = language

        result = self._model.transcribe(str(audio_path), **options)

        if progress_cb:
            progress_cb("Done.")

        return result.get("text", "").strip()
