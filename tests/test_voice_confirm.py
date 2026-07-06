"""Tests for spoken confirmation of high-risk tool calls."""
import asyncio

import pytest

from jarvis.core import pending_actions
from jarvis.voice.confirm import parse_affirmative, run_voice_confirmation
from jarvis.voice.listener import VoiceListener


@pytest.fixture(autouse=True)
def _clear_pending():
    pending_actions._notifiers.clear()
    pending_actions._pending.clear()
    pending_actions._futures.clear()
    yield
    pending_actions._notifiers.clear()
    pending_actions._pending.clear()
    pending_actions._futures.clear()


@pytest.mark.parametrize("text", ["yes", "Yes please", "yeah go ahead", "sure, do it", "confirm", "send it"])
def test_parse_affirmative_true(text):
    assert parse_affirmative(text) is True


@pytest.mark.parametrize("text", ["no", "no thanks", "don't", "cancel that", "stop", "hold off", "", "maybe later", "yesterday"])
def test_parse_affirmative_false(text):
    assert parse_affirmative(text) is False


class _FakeSpeaker:
    def __init__(self):
        self.said: list[str] = []

    async def speak(self, text: str, **_kwargs):
        self.said.append(text)


class _FakeListener:
    def __init__(self, reply: str):
        self._reply = reply

    async def capture_reply(self, timeout: float = 10.0) -> str:
        return self._reply


async def _run_with_voice(reply: str, *, timeout_s: float = 5.0) -> tuple[bool, _FakeSpeaker]:
    speaker = _FakeSpeaker()
    listener = _FakeListener(reply)

    async def notifier(payload):
        conf = payload["confirmation"]
        asyncio.ensure_future(run_voice_confirmation(speaker, listener, conf["id"], conf["summary"]))

    pending_actions.add_notifier(notifier)
    result = await pending_actions.request_confirmation(
        "send_email", summary="Email Bob about the meeting", risk="high", timeout_s=timeout_s
    )
    return result, speaker


async def test_voice_confirmation_approves():
    result, speaker = await _run_with_voice("yes, go ahead")
    assert result is True
    assert "Shall I proceed" in speaker.said[0]
    assert "Email Bob about the meeting" in speaker.said[0]


async def test_voice_confirmation_denies():
    result, _ = await _run_with_voice("no, cancel that")
    assert result is False


async def test_voice_confirmation_empty_reply_leaves_it_to_timeout():
    # No intelligible reply -> not resolved by voice -> request times out (deny).
    result, _ = await _run_with_voice("", timeout_s=0.1)
    assert result is False


async def test_capture_reply_transcribes_and_clears_flag(monkeypatch):
    listener = VoiceListener()
    listener._stream = object()  # non-None so capture proceeds

    async def fake_record():
        return object()  # stand-in for the recorded audio array

    monkeypatch.setattr(listener, "_record_speech", fake_record)
    monkeypatch.setattr(listener, "_transcribe", lambda _audio: "  yes  ")

    reply = await listener.capture_reply(timeout=1.0)
    assert reply == "yes"
    assert listener._capturing is False


async def test_capture_reply_returns_empty_without_stream():
    listener = VoiceListener()
    assert listener._stream is None
    assert await listener.capture_reply(timeout=0.1) == ""


async def test_record_speech_serializes_stream_access(monkeypatch):
    # The wake-word loop and a confirmation capture must never record concurrently.
    listener = VoiceListener()
    listener._stream = object()
    active = 0
    max_active = 0

    async def fake_locked():
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return None

    monkeypatch.setattr(listener, "_record_speech_locked", fake_locked)
    await asyncio.gather(listener._record_speech(), listener._record_speech())
    assert max_active == 1
