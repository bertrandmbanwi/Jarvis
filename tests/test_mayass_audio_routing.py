"""Tests for MayAss voice/audio routing policies.

Phase 8 scope: ensure audio ownership is deterministic and conservative:
- browser owner sends browser audio only
- macOS owner keeps audio local only
- none stays text-only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from jarvis.config import settings
from jarvis.core import server
from jarvis.voice.speaker import VoiceSpeaker


@dataclass
class FakeVoiceWsManager:
    active: list[object]
    sent_to: list[tuple[object, dict]] = field(default_factory=list)
    broadcasts: list[tuple[dict, object | None]] = field(default_factory=list)

    async def send_to(self, ws, data):
        self.sent_to.append((ws, data))

    async def broadcast_json(self, data, exclude=None):
        self.broadcasts.append((data, exclude))

    def get_audio_clients(self, exclude=None):
        return [ws for ws in self.active if ws is not exclude]


@pytest.mark.asyncio
async def test_browser_audio_owner_sends_voice_audio_to_target_only(monkeypatch):
    target = cast(Any, object())
    other = cast(Any, object())
    fake_manager = FakeVoiceWsManager(active=[target, other])
    monkeypatch.setattr(server, "ws_manager", fake_manager)
    monkeypatch.setattr(settings, "MAYASS_AUDIO_OWNER", "browser")

    await server.broadcast_voice_state(
        True,
        amplitude_envelope=[0.1, 0.2],
        audio_duration=1.5,
        audio_base64="QUJD",
        target_ws=target,
    )

    assert fake_manager.sent_to == [
        (target, {
            "voice_speaking": True,
            "amplitude_envelope": [0.1, 0.2],
            "audio_duration": 1.5,
            "voice_audio": "QUJD",
            "audio_format": "audio/wav",
        })
    ]
    assert fake_manager.broadcasts == [(
        {"voice_speaking": True, "amplitude_envelope": [0.1, 0.2], "audio_duration": 1.5},
        target,
    )]


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["macos", "none"])
async def test_non_browser_audio_owner_suppresses_browser_voice_audio(monkeypatch, owner):
    target = cast(Any, object())
    fake_manager = FakeVoiceWsManager(active=[target])
    monkeypatch.setattr(server, "ws_manager", fake_manager)
    monkeypatch.setattr(settings, "MAYASS_AUDIO_OWNER", owner)

    await server.broadcast_voice_state(
        True,
        amplitude_envelope=[0.3],
        audio_duration=0.8,
        audio_base64="SEVMTE8=",
        target_ws=target,
    )

    assert fake_manager.sent_to == []
    assert fake_manager.broadcasts == [(
        {"voice_speaking": True, "amplitude_envelope": [0.3], "audio_duration": 0.8},
        None,
    )]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner", "expected_skip"),
    [
        ("browser", True),
        ("macos", False),
        ("none", True),
    ],
)
async def test_voice_speaker_defaults_local_playback_from_audio_owner(monkeypatch, owner, expected_skip):
    monkeypatch.setattr(settings, "MAYASS_AUDIO_OWNER", owner)

    speaker = VoiceSpeaker()
    speaker._backend = "macos_say"

    observed = {}

    async def fake_speak_macos(self, text):
        observed["text"] = text
        observed["skip_local_playback"] = self._skip_local_playback

    monkeypatch.setattr(VoiceSpeaker, "_speak_macos", fake_speak_macos, raising=False)

    await speaker.speak("hello there")

    assert observed["text"] == "hello there"
    assert observed["skip_local_playback"] is expected_skip
