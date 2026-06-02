"""
transcription
=============
Speech-to-text transcription subsystem for Multi-Output Audio Console.

Provides live microphone transcription and drag-and-drop audio file
transcription using Vosk (real-time) and Whisper (batch) engines.
"""

from transcription.model_manager import ModelManager
from transcription.transcriber import VoskTranscriber, WhisperTranscriber

__all__ = ["ModelManager", "VoskTranscriber", "WhisperTranscriber"]
