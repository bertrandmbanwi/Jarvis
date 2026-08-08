"""Tests for Phase 6 MayAss confirmation policy.

Phase 6 builds the brake before MayAss gets hands: rich pending actions,
three user decisions, and a hard rule that critical actions cannot be
permanently approved.
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


def test_policy_blocks_permanent_approval_for_critical_actions():
    from jarvis.core.mayass_policy import evaluate_confirmation_decision

    result = evaluate_confirmation_decision(risk="critical", decision="confirm_always")

    assert result.allowed is False
    assert result.final_decision == "deny"
    assert "critical" in result.reason.lower()


def test_policy_allows_once_and_denial_decisions():
    from jarvis.core.mayass_policy import evaluate_confirmation_decision

    approve_once = evaluate_confirmation_decision(risk="critical", decision="confirm_once")
    deny = evaluate_confirmation_decision(risk="high", decision="deny")

    assert approve_once.allowed is True
    assert approve_once.final_decision == "confirm_once"
    assert deny.allowed is False
    assert deny.final_decision == "deny"


async def test_pending_action_exposes_rich_payload_and_three_decisions():
    action = pending_actions.create_pending_action(
        action_type="delete_file",
        summary="มายกำลังจะลบไฟล์ทดสอบ",
        risk="high",
        affected_targets=["/tmp/mayass-demo.txt"],
        reversible=False,
        reason="บอสขอให้ลบไฟล์นี้",
        consequence_if_denied="ไฟล์จะยังอยู่เหมือนเดิม",
        permanent_policy_key="delete_file:/tmp/mayass-demo.txt",
    )

    public = action.public()

    assert public["id"]
    assert public["action_type"] == "delete_file"
    assert public["tool"] == "delete_file"  # backward-compatible UI field
    assert public["affected_targets"] == ["/tmp/mayass-demo.txt"]
    assert public["reversible"] is False
    assert public["reason"] == "บอสขอให้ลบไฟล์นี้"
    assert public["consequence_if_denied"] == "ไฟล์จะยังอยู่เหมือนเดิม"
    assert public["permanent_policy_key"] == "delete_file:/tmp/mayass-demo.txt"
    assert public["allowed_decisions"] == ["confirm_once", "confirm_always", "deny"]
    assert pending_actions.list_pending() == [public]


async def test_resolve_rejects_critical_confirm_always_but_accepts_once():
    critical = pending_actions.create_pending_action(
        action_type="run_shell",
        summary="มายกำลังจะรันคำสั่งเสี่ยงสูง",
        risk="critical",
        affected_targets=["local shell"],
        reversible=False,
        reason="ทดสอบ policy",
        consequence_if_denied="คำสั่งจะไม่ถูกรัน",
        permanent_policy_key="run_shell:*",
    )

    assert pending_actions.resolve(critical.id, "confirm_always") is False
    assert pending_actions.list_pending()[0]["id"] == critical.id
    assert pending_actions.resolve(critical.id, "confirm_once") is True
    assert pending_actions.list_pending() == []


async def test_fake_pending_action_endpoint_creates_modal_payload(monkeypatch):
    from jarvis.core import server

    delivered = []

    async def fake_broadcast(payload):
        delivered.append(payload)

    monkeypatch.setattr(server.ws_manager, "broadcast_json", fake_broadcast)

    result = await server.create_fake_pending_action(
        server.FakePendingActionRequest(
            action_type="delete_file",
            affected_targets=["/tmp/mayass-demo.txt"],
            reversible=False,
            reason="Smoke test only",
            consequence_if_denied="No file will be touched",
            permanent_policy_key="delete_file:/tmp/mayass-demo.txt",
            risk="high",
        )
    )

    assert result["pending"]["action_type"] == "delete_file"
    assert result["pending"]["risk"] == "high"
    assert result["pending"]["allowed_decisions"] == ["confirm_once", "confirm_always", "deny"]
    assert delivered[0]["type"] == "confirmation_required"
    assert delivered[0]["confirmation"]["id"] == result["pending"]["id"]
