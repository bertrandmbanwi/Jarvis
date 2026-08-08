"""Tests for Phase 5 MayAss memory/persona quarantine.

MayAss must not consume legacy Jarvis profile, location, honorific, or memory
context. Old Jarvis data stays untouched for rollback; the MayAss path simply
must not use it by default.
"""

from pathlib import Path
from typing import Any

import pytest

LEGACY_LEAKAGE_TERMS = (
    "JARVIS",
    "Becs",
    "sir",
    "Forney",
    "Texas",
    "Becs' default local location",
)


class FakeBridgeResponse:
    text = "ตามบริบทตอนนี้ มายเรียกคุณว่าบอสค่ะ"
    backend = "hermes"
    mode = "realtime"
    ok = True
    error = ""


class FakeBridge:
    calls: list[Any] = []

    async def process(self, request):
        self.calls.append(request)
        return FakeBridgeResponse()


class LegacyBrainMustNotBeTouched:
    def __getattribute__(self, name):
        if name in {"process", "memory", "conversation", "llm", "profile", "proactive"}:
            raise AssertionError(f"legacy brain attribute touched in MayAss mode: {name}")
        return super().__getattribute__(name)


def test_mayass_prompt_excludes_legacy_identity_and_location_terms():
    from jarvis.core.mayass_bridge import MayAssBridgeRequest, build_prompt_envelope

    prompt = build_prompt_envelope(
        MayAssBridgeRequest(
            text="มาย จำได้ไหมว่าผมชื่ออะไร ตอบตามบริบทของมายเท่านั้น",
            source="chat",
        )
    )

    assert "Maymint" in prompt
    assert "มาย" in prompt
    assert "บอส" in prompt
    assert "Hermes runtime:" in prompt
    for term in LEGACY_LEAKAGE_TERMS:
        assert term not in prompt


def test_mayass_prompt_declares_memory_quarantine_policy():
    from jarvis.core.mayass_bridge import MayAssBridgeRequest, build_prompt_envelope

    prompt = build_prompt_envelope(MayAssBridgeRequest(text="จำอะไรเกี่ยวกับผมได้บ้าง"))

    assert "Memory quarantine:" in prompt
    assert "current conversation only" in prompt
    assert "legacy Jarvis profile" in prompt
    assert "old local memories" in prompt


def test_dashboard_activity_log_uses_mayass_labels():
    source = Path("jarvis/ui/jarvis-ui/src/components/dashboard/DashboardView.tsx").read_text(
        encoding="utf-8"
    )

    assert '{isUser ? "บอส" : "Maymint"}' in source
    assert '{isUser ? "Becs" : "JARVIS"}' not in source
    assert '{isUser ? "B" : "M"}' in source
    assert '{isUser ? "B" : "J"}' not in source


@pytest.mark.asyncio
async def test_mayass_chat_route_does_not_touch_legacy_brain_memory(monkeypatch):
    from jarvis.core import server

    FakeBridge.calls = []
    monkeypatch.setattr(server.settings, "MAYASS_ENABLED", True)
    monkeypatch.setattr(server, "brain", LegacyBrainMustNotBeTouched())
    monkeypatch.setattr(server, "MayAssBridge", FakeBridge, raising=False)
    monkeypatch.setattr(server.savings_tracker, "get_summary", lambda: {"saved": 0})

    result = await server.process_user_request(
        "มาย จำได้ไหมว่าผมชื่ออะไร ตอบตามบริบทของมายเท่านั้น",
        source="chat",
        mode="realtime",
    )

    assert result.response == "ตามบริบทตอนนี้ มายเรียกคุณว่าบอสค่ะ"
    assert result.tier_used == "mayass"
    assert result.backend == "hermes"
    assert len(FakeBridge.calls) == 1
    request = FakeBridge.calls[0]
    assert request.source == "chat"
    assert request.allow_tools is False
