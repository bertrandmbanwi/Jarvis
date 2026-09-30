"""GPT-Live relay: session setup, audio relay, and delegation to the brain."""

import asyncio
import json

import pytest

from jarvis.config import settings
from jarvis.voice.live_session import MAX_APPEND_CHARS, LiveSession, split_for_append


class FakeLiveSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def close(self):
        self.closed = True


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    socket = FakeLiveSocket()
    client_events = []
    requests = []

    async def runner(text):
        requests.append(text)
        return "Your meeting is at 3pm."

    async def sink(event):
        client_events.append(event)

    async def connect(url, additional_headers):
        assert url == "wss://api.openai.com/v1/live/sessions"
        assert additional_headers["Authorization"] == "Bearer sk-test"
        return socket

    session = LiveSession(runner=runner, client_sink=sink, connect=connect)
    return session, socket, client_events, requests


@pytest.mark.asyncio
async def test_open_starts_client_delegation_session(live):
    session, socket, _, _ = live
    await session.open()
    start = socket.sent[0]
    assert start["type"] == "session.start"
    assert start["session"]["model"] == "gpt-live-1"
    assert start["session"]["delegation"] == {"type": "client"}
    assert start["session"]["audio"]["format"] == {"type": "audio/pcm", "rate": 24000}


@pytest.mark.asyncio
async def test_audio_relays_both_ways(live):
    session, socket, client_events, _ = live
    await session.open()
    await session.send_audio("AAAA")
    assert socket.sent[-1] == {"type": "session.input_audio.append", "audio": "AAAA", "event_id": socket.sent[-1]["event_id"]}
    await session.handle_event({"type": "session.output_audio.delta", "delta": "BBBB"})
    assert client_events[-1] == {"type": "audio", "audio": "BBBB"}


@pytest.mark.asyncio
async def test_delegation_runs_transcript_through_brain(live):
    session, socket, client_events, requests = live
    await session.open()
    for delta in ("When is ", "my meeting?"):
        await session.handle_event({"type": "session.input_transcript.delta", "delta": delta})
    await session.handle_event({"type": "session.delegation.created", "delegation": {"id": "del_1", "type": "delegation"}})
    await asyncio.gather(*session._tasks)

    assert requests == ["When is my meeting?"]
    commentary = [e for e in socket.sent if e["type"] == "session.commentary.append"]
    assert commentary == [{"type": "session.commentary.append", "delegation_id": "del_1",
                           "content": "Your meeting is at 3pm.", "event_id": commentary[0]["event_id"]}]
    assert any(e["type"] == "session.thinking.append" for e in socket.sent)
    assert client_events[-1] == {"type": "result", "text": "Your meeting is at 3pm."}


def test_long_results_are_split_under_the_append_limit():
    text = ("This is a sentence. " * 300).strip()
    pieces = split_for_append(text)
    assert len(pieces) > 1
    assert all(len(p) <= MAX_APPEND_CHARS for p in pieces)
    assert " ".join(pieces).replace("  ", " ") == text


@pytest.mark.asyncio
async def test_open_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    async def sink(event):
        pass

    with pytest.raises(RuntimeError):
        await LiveSession(runner=None, client_sink=sink).open()
