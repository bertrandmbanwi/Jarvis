"""Tests for Phase 4 MayAss `/chat` route integration.

Phase 4 scope: switch the existing chat route to MayAssBridge only when
MAYASS_ENABLED=true, while preserving the response shape and Jarvis fallback.
"""

import pytest


class FakeConversationTurn:
    role = "assistant"
    tier_used = "brain"


class FakeLLM:
    active_backend = "fake-jarvis"


class FakeBrain:
    def __init__(self):
        self.calls: list[str] = []
        self.conversation = [FakeConversationTurn()]
        self.llm = FakeLLM()

    async def process(self, message: str) -> str:
        self.calls.append(message)
        return "jarvis fallback response"


class FakeBridgeResponse:
    text = "มายตอบจาก Hermes bridge แล้วค่ะ"
    backend = "hermes"
    mode = "realtime"
    ok = True
    error = ""


class FakeBridge:
    calls: list[object] = []

    async def process(self, request):
        self.calls.append(request)
        return FakeBridgeResponse()


@pytest.mark.asyncio
async def test_chat_route_uses_jarvis_brain_when_mayass_disabled(monkeypatch):
    from jarvis.core import server

    fake_brain = FakeBrain()
    monkeypatch.setattr(server.settings, "MAYASS_ENABLED", False)
    monkeypatch.setattr(server, "brain", fake_brain)
    monkeypatch.setattr(server.savings_tracker, "get_summary", lambda: {"saved": 0})

    result = await server.chat(server.ChatRequest(message="hello", mode="realtime"))

    assert result.response == "jarvis fallback response"
    assert result.backend == "fake-jarvis"
    assert result.tier_used == "brain"
    assert result.local_savings == {"saved": 0}
    assert fake_brain.calls == ["hello"]


@pytest.mark.asyncio
async def test_chat_route_uses_mayass_bridge_when_enabled(monkeypatch):
    from jarvis.core import server

    fake_brain = FakeBrain()
    FakeBridge.calls = []
    monkeypatch.setattr(server.settings, "MAYASS_ENABLED", True)
    monkeypatch.setattr(server, "brain", fake_brain)
    monkeypatch.setattr(server, "MayAssBridge", FakeBridge, raising=False)
    monkeypatch.setattr(server.savings_tracker, "get_summary", lambda: {"saved": 0})

    result = await server.chat(server.ChatRequest(message="มายตอบหน่อย", mode="realtime"))

    assert result.response == "มายตอบจาก Hermes bridge แล้วค่ะ"
    assert result.backend == "hermes"
    assert result.tier_used == "mayass"
    assert result.local_savings == {"saved": 0}
    assert fake_brain.calls == []
    assert len(FakeBridge.calls) == 1
    bridge_request = FakeBridge.calls[0]
    assert bridge_request.text == "มายตอบหน่อย"
    assert bridge_request.source == "chat"
    assert bridge_request.mode == "realtime"
    assert bridge_request.wants_voice is False
    assert bridge_request.allow_tools is False


@pytest.mark.asyncio
async def test_chat_route_preserves_hermes_error_without_ollama_fallback(monkeypatch):
    from jarvis.core import server

    class ErrorBridgeResponse:
        text = ""
        backend = "hermes"
        mode = "work"
        ok = False
        error = "bridge unavailable"

    class ErrorBridge:
        async def process(self, request):
            return ErrorBridgeResponse()

    fake_brain = FakeBrain()
    monkeypatch.setattr(server.settings, "MAYASS_ENABLED", True)
    monkeypatch.setattr(server, "brain", fake_brain)
    monkeypatch.setattr(server, "MayAssBridge", ErrorBridge, raising=False)
    monkeypatch.setattr(server.savings_tracker, "get_summary", lambda: {"saved": 0})

    result = await server.chat(server.ChatRequest(message="ping", mode="work"))

    assert result.response == "bridge unavailable"
    assert result.backend == "hermes"
    assert result.tier_used == "mayass-error"
    assert result.local_savings == {"saved": 0}
    assert fake_brain.calls == []
