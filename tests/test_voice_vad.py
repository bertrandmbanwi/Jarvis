"""Silero VAD wrapper, barge-in, and streamed local playback."""

import asyncio

import numpy as np
import pytest

from jarvis.config import settings
from jarvis.voice.vad import SpeechDetector


def test_amplitude_fallback_without_model(monkeypatch):
    monkeypatch.setattr(settings, "VAD_ENABLED", False)
    detector = SpeechDetector()
    assert detector.is_speech(np.full(1280, 500, dtype=np.int16), amplitude_threshold=60)
    assert not detector.is_speech(np.zeros(1280, dtype=np.int16), amplitude_threshold=60)


def test_uses_model_probability_and_pads_to_window(monkeypatch):
    seen = {}

    def fake_model(audio):
        seen["len"] = audio.size
        return np.array([[0.1], [0.9], [0.2]])

    detector = SpeechDetector(threshold=0.5)
    detector._model = fake_model
    # Quiet chunk, but the model hears speech: the model wins over amplitude.
    assert detector.is_speech(np.full(1280, 5, dtype=np.int16), amplitude_threshold=60)
    assert seen["len"] == 1536  # 1280 padded up to 3 x 512


def test_real_silero_model_rejects_silence():
    detector = SpeechDetector()
    probability = detector.speech_probability(np.zeros(1280, dtype=np.int16))
    if probability is None:
        pytest.skip("faster-whisper / onnxruntime not installed")
    assert probability < 0.5


@pytest.mark.asyncio
async def test_barge_in_needs_sustained_speech_and_is_opt_in(monkeypatch):
    from jarvis.voice.listener import VoiceListener

    listener = VoiceListener()
    stopped = []
    listener.on_barge_in = lambda: stopped.append(True)
    listener._is_speaking = True
    listener._vad.is_speech = lambda chunk, threshold: True
    chunk = np.zeros(1280, dtype=np.int16)

    monkeypatch.setattr(settings, "BARGE_IN_ENABLED", False)
    assert not await listener._check_barge_in(chunk)

    monkeypatch.setattr(settings, "BARGE_IN_ENABLED", True)
    monkeypatch.setattr(settings, "BARGE_IN_FRAMES", 3)
    results = [await listener._check_barge_in(chunk) for _ in range(3)]
    assert results == [False, False, True]
    assert stopped == [True] and listener._is_speaking is False


@pytest.mark.asyncio
async def test_queued_chunks_are_dropped_after_stop(monkeypatch):
    from jarvis.voice.speaker import VoiceSpeaker

    speaker = VoiceSpeaker()
    played = []

    async def fake_play(path):
        played.append(path)
        speaker.stop_speaking()  # user interrupts during the first chunk

    monkeypatch.setattr(speaker, "_play_audio", fake_play)
    queue: asyncio.Queue = asyncio.Queue()
    for _ in range(3):
        queue.put_nowait(np.zeros(2400, dtype=np.float32))
    queue.put_nowait(None)
    await speaker._play_chunks(queue)
    assert len(played) == 1


def test_cloud_stt_fallback_is_opt_in(monkeypatch):
    from jarvis.voice.listener import VoiceListener

    listener = VoiceListener()
    monkeypatch.setattr(listener, "_transcribe_local", lambda audio: "")
    calls = []
    monkeypatch.setattr(listener, "_transcribe_cloud", lambda audio: calls.append(1) or "hello")
    audio = np.zeros(16000, dtype=np.int16)

    monkeypatch.setattr(settings, "STT_CLOUD_FALLBACK", False)
    assert listener._transcribe(audio) == ""
    monkeypatch.setattr(settings, "STT_CLOUD_FALLBACK", True)
    assert listener._transcribe(audio) == "hello"
    assert calls == [1]
