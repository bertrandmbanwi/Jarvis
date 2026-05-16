"""Tests for desktop hotkey voice activation."""
import numpy as np
import pytest

from jarvis.voice.listener import VoiceListener


class FakeOverlayWebSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


def test_request_activation_requires_ready_listener():
    listener = VoiceListener()

    assert listener.request_activation() is False
    assert listener._consume_activation_request() is False


def test_request_activation_sets_single_pending_capture():
    listener = VoiceListener()
    listener._is_listening = True
    listener._in_followup_window = True
    listener._followup_sustained_frames = 3
    listener._followup_max_amplitude = 42.0

    assert listener.request_activation() is True
    assert listener._in_followup_window is False
    assert listener._followup_sustained_frames == 0
    assert listener._followup_max_amplitude == 0.0
    assert listener._consume_activation_request() is True
    assert listener._consume_activation_request() is False


@pytest.mark.asyncio
async def test_capture_and_dispatch_speech_invokes_callbacks(monkeypatch):
    listener = VoiceListener()
    wake_events = []
    utterances = []
    capture_events = []

    listener.on_wake(lambda: wake_events.append("wake"))

    async def on_speech(text: str):
        utterances.append(text)

    async def on_capture_complete(source: str, dispatched: bool):
        capture_events.append((source, dispatched))

    listener.on_speech(on_speech)
    listener.on_capture_complete(on_capture_complete)

    async def fake_record_speech():
        return np.array([1, 2, 3], dtype=np.int16)

    monkeypatch.setattr(listener, "_record_speech", fake_record_speech)
    monkeypatch.setattr(listener, "_transcribe", lambda audio: "open the dashboard")

    assert await listener._capture_and_dispatch_speech("hotkey") is True
    assert wake_events == ["wake"]
    assert utterances == ["open the dashboard"]
    assert capture_events == [("hotkey", True)]


@pytest.mark.asyncio
async def test_capture_completion_callback_runs_when_no_speech(monkeypatch):
    listener = VoiceListener()
    wake_events = []
    capture_events = []

    listener.on_wake(lambda: wake_events.append("wake"))
    listener.on_capture_complete(lambda source, dispatched: capture_events.append((source, dispatched)))

    async def fake_record_speech():
        return None

    monkeypatch.setattr(listener, "_record_speech", fake_record_speech)

    assert await listener._capture_and_dispatch_speech("hotkey") is False
    assert wake_events == ["wake"]
    assert capture_events == [("hotkey", False)]


@pytest.mark.asyncio
async def test_overlay_activation_requests_listener(monkeypatch):
    from jarvis.core import server

    class FakeSpeaker:
        def __init__(self):
            self.stopped = False

        def stop_speaking(self):
            self.stopped = True

    class FakeListener:
        def __init__(self):
            self.speaking_state = None
            self.activation_requested = False

        def set_speaking(self, speaking: bool, open_followup: bool = True):
            self.speaking_state = (speaking, open_followup)

        def request_activation(self) -> bool:
            self.activation_requested = True
            return True

    speaker = FakeSpeaker()
    listener = FakeListener()
    websocket = FakeOverlayWebSocket()
    monkeypatch.setattr(server, "_speaker", speaker)
    monkeypatch.setattr(server, "_listener", listener)
    monkeypatch.setattr(server, "_overlay_clients", [])
    monkeypatch.setattr(server, "_overlay_state", "idle")
    monkeypatch.setattr(server, "_overlay_text", "old response")
    monkeypatch.setattr(server, "_overlay_user_text", "old user text")

    await server._activate_voice_from_overlay(websocket)

    assert speaker.stopped is True
    assert listener.speaking_state == (False, False)
    assert listener.activation_requested is True
    assert websocket.messages == [{"activationAccepted": True}]
    assert server._overlay_state == "listening"
    assert server._overlay_text == ""
    assert server._overlay_user_text == ""


@pytest.mark.asyncio
async def test_voice_state_clear_removes_overlay_text(monkeypatch):
    from jarvis.core import server

    monkeypatch.setattr(server, "_overlay_clients", [])
    monkeypatch.setattr(server, "_overlay_state", "speaking")
    monkeypatch.setattr(server, "_overlay_text", "old response")
    monkeypatch.setattr(server, "_overlay_user_text", "old user text")

    await server.broadcast_voice_state(False)

    assert server._overlay_state == "idle"
    assert server._overlay_text == ""
    assert server._overlay_user_text == ""
