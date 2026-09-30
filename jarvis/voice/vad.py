"""Voice activity detection with Silero VAD, falling back to an amplitude threshold.

The Silero ONNX model ships with faster-whisper (already a dependency), so no
extra download is needed. Unlike a mean-amplitude threshold, it separates
speech from steady background noise (fans, music, keyboard) and quiet
speakers from loud rooms.
"""
from __future__ import annotations

import logging

import numpy as np

from jarvis.config import settings

logger = logging.getLogger("jarvis.voice.vad")

SILERO_WINDOW = 512  # samples per Silero window at 16 kHz


class SpeechDetector:
    """Decide whether a 16 kHz int16 audio chunk contains speech."""

    def __init__(self, threshold: float | None = None):
        self.threshold = settings.VAD_THRESHOLD if threshold is None else threshold
        self._model = None
        self._unavailable = not settings.VAD_ENABLED

    def _load(self):
        if self._model is None and not self._unavailable:
            try:
                from faster_whisper.vad import get_vad_model

                self._model = get_vad_model()
                logger.info("Silero VAD loaded (threshold %.2f).", self.threshold)
            except Exception as exc:
                logger.warning("Silero VAD unavailable (%s); using amplitude threshold.", exc)
                self._unavailable = True
        return self._model

    def speech_probability(self, chunk: np.ndarray) -> float | None:
        """Highest per-window speech probability in the chunk, or None without a model."""
        model = self._load()
        if model is None or chunk.size == 0:
            return None
        audio = chunk.astype(np.float32) / 32768.0
        remainder = audio.size % SILERO_WINDOW
        if remainder:
            audio = np.pad(audio, (0, SILERO_WINDOW - remainder))
        try:
            return float(np.max(model(audio)))
        except Exception as exc:
            logger.warning("Silero VAD failed (%s); using amplitude threshold.", exc)
            self._unavailable = True
            return None

    def is_speech(self, chunk: np.ndarray, amplitude_threshold: float) -> bool:
        probability = self.speech_probability(chunk)
        if probability is None:
            return float(np.abs(chunk).mean()) > amplitude_threshold
        return probability >= self.threshold
