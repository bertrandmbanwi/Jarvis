"""Tests for Phase 7A MayAss/Hermes tool ownership boundary.

Phase 7A is deliberately conservative: MayAss can classify planned actions and
surface action cards/pending confirmations, but it must not execute real tools
or fall back to the legacy Jarvis AgentExecutor as decision maker.
"""

import pytest

from jarvis.core import pending_actions


@pytest.fixture(autouse=True)
def _clear_pending():
    pending_actions._notifiers.clear()
    pending_actions._pending.clear()
    pending_actions._futures.clear()
    yield
    pending_actions._notifiers.clear()
    pending_actions._pending.clear()
    pending_actions._futures.clear()


def test_read_only_system_status_intent_becomes_safe_action_card():
    from jarvis.core.mayass_bridge import classify_mayass_action_intent

    intent = classify_mayass_action_intent("มาย ช่วยบอกสถานะระบบแบบอ่านอย่างเดียว")

    assert intent is not None
    assert intent.action_type == "system_status"
    assert intent.risk == "low"
    assert intent.requires_confirmation is False
    assert intent.execution_supported is False
    assert intent.affected_targets == ("local system",)


@pytest.mark.asyncio
async def test_risky_delete_intent_creates_pending_action_without_running_hermes_or_tools():
    from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

    async def forbidden_runner(prompt: str, timeout: float) -> str:
        raise AssertionError("risky planned actions must not call Hermes runner in Phase 7A")

    bridge = MayAssBridge(runner=forbidden_runner)
    response = await bridge.process(
        MayAssBridgeRequest(
            text="มาย ลบไฟล์ /tmp/mayass-phase7-test.txt ให้หน่อย",
            mode="work",
            allow_tools=True,
        )
    )

    assert response.ok is True
    assert response.backend == "hermes"
    assert "รอให้บอสยืนยัน" in response.text
    assert len(response.action_cards) == 1
    card = response.action_cards[0]
    assert card["action_type"] == "delete_file"
    assert card["risk"] == "high"
    assert card["requires_confirmation"] is True
    assert card["execution_supported"] is False
    assert card["affected_targets"] == ["/tmp/mayass-phase7-test.txt"]

    pending = pending_actions.list_pending()
    assert len(pending) == 1
    assert pending[0]["action_type"] == "delete_file"
    assert pending[0]["affected_targets"] == ["/tmp/mayass-phase7-test.txt"]
    assert pending[0]["risk"] == "high"


@pytest.mark.asyncio
async def test_thai_delete_file_variant_creates_pending_action_without_running_hermes():
    from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

    async def forbidden_runner(prompt: str, timeout: float) -> str:
        raise AssertionError("Thai risky delete variants must not call Hermes runner in Phase 7A")

    response = await MayAssBridge(runner=forbidden_runner).process(
        MayAssBridgeRequest(
            text="มาย ช่วยลบไฟล์สมมติชื่อ demo-note.txt แต่ต้องรออนุญาตก่อน",
            mode="work",
            allow_tools=True,
        )
    )

    assert response.ok is True
    assert response.action_cards[0]["action_type"] == "delete_file"
    assert response.action_cards[0]["affected_targets"] == ["demo-note.txt"]
    assert pending_actions.list_pending()[0]["affected_targets"] == ["demo-note.txt"]


@pytest.mark.asyncio
async def test_mayass_chat_route_broadcasts_phase7_pending_action_and_bypasses_legacy_brain(monkeypatch):
    from jarvis.core import server

    class ExplodingBrain:
        conversation = []

        class LLM:
            active_backend = "legacy"

        llm = LLM()

        async def process(self, message: str) -> str:
            raise AssertionError("MayAss mode must not call legacy brain.process")

    delivered = []

    async def fake_broadcast(payload):
        delivered.append(payload)

    monkeypatch.setattr(server.settings, "MAYASS_ENABLED", True)
    monkeypatch.setattr(server, "brain", ExplodingBrain())
    monkeypatch.setattr(server.ws_manager, "broadcast_json", fake_broadcast)
    monkeypatch.setattr(server.savings_tracker, "get_summary", lambda: {"saved": 0})

    result = await server.chat(
        server.ChatRequest(
            message="มาย ลบไฟล์ /tmp/mayass-phase7-route.txt ให้หน่อย",
            mode="work",
        )
    )

    assert result.tier_used == "mayass"
    assert result.backend == "hermes"
    assert result.action_cards[0]["action_type"] == "delete_file"
    assert pending_actions.list_pending()[0]["affected_targets"] == ["/tmp/mayass-phase7-route.txt"]
    assert delivered[0]["type"] == "confirmation_required"
    assert delivered[0]["confirmation"]["action_type"] == "delete_file"


@pytest.mark.asyncio
async def test_critical_shell_intent_creates_critical_pending_action():
    from jarvis.core.mayass_bridge import MayAssBridge, MayAssBridgeRequest

    async def forbidden_runner(prompt: str, timeout: float) -> str:
        raise AssertionError("critical planned actions must not call Hermes runner in Phase 7A")

    response = await MayAssBridge(runner=forbidden_runner).process(
        MayAssBridgeRequest(
            text="มาย รันคำสั่ง rm -rf /tmp/mayass-danger-test ให้หน่อย",
            mode="work",
            allow_tools=True,
        )
    )

    assert response.ok is True
    assert response.action_cards[0]["action_type"] == "run_shell"
    assert response.action_cards[0]["risk"] == "critical"
    pending = pending_actions.list_pending()
    assert pending[0]["action_type"] == "run_shell"
    assert pending[0]["risk"] == "critical"
    assert "confirm_always" in pending[0]["allowed_decisions"]
