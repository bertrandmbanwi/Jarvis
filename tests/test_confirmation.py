"""Tests for server-side high-risk tool confirmation."""
import asyncio

import pytest

from jarvis.core import pending_actions
from jarvis.core.confirmation import confirmed_scope, is_confirmed
from jarvis.core.permissions import assess_tool_call, describe_tool_call


@pytest.fixture(autouse=True)
def _clear_pending():
    pending_actions.set_notifier(None)
    pending_actions._pending.clear()
    pending_actions._futures.clear()
    yield
    pending_actions.set_notifier(None)
    pending_actions._pending.clear()
    pending_actions._futures.clear()


def test_describe_tool_call_redacts_sensitive_fields():
    desc = describe_tool_call("send_email", {"to": "x@y.com", "body": "secret plans", "confirmed": True})
    assert "x@y.com" in desc
    assert "secret plans" not in desc
    assert "[redacted]" in desc
    assert "confirmed" not in desc  # the flag is not shown to the user


async def test_request_confirmation_denies_when_no_notifier():
    # No channel to ask -> unattended server must not run the tool.
    assert pending_actions.confirmation_available() is False
    assert await pending_actions.request_confirmation("send_email", summary="s", risk="high") is False


async def test_request_confirmation_approved():
    async def approve(payload):
        assert payload["type"] == "confirmation_required"
        conf = payload["confirmation"]
        # The action is visible to a reconnecting client while in-flight.
        assert any(a["id"] == conf["id"] for a in pending_actions.list_pending())
        pending_actions.resolve(conf["id"], True)

    pending_actions.set_notifier(approve)
    assert await pending_actions.request_confirmation("send_email", summary="s", risk="high") is True
    assert pending_actions.list_pending() == []  # cleaned up


async def test_request_confirmation_denied():
    async def deny(payload):
        pending_actions.resolve(payload["confirmation"]["id"], False)

    pending_actions.set_notifier(deny)
    assert await pending_actions.request_confirmation("run_command", summary="rm -rf", risk="critical") is False


async def test_request_confirmation_times_out():
    async def ignore(_payload):
        return None

    pending_actions.set_notifier(ignore)
    result = await pending_actions.request_confirmation(
        "send_email", summary="s", risk="high", timeout_s=0.05
    )
    assert result is False
    assert pending_actions.list_pending() == []


def test_resolve_unknown_action_returns_false():
    assert pending_actions.resolve("does-not-exist", True) is False


async def test_out_of_band_approval_resolves_in_flight_request():
    seen: dict[str, str] = {}

    async def capture(payload):
        seen["id"] = payload["confirmation"]["id"]

    pending_actions.set_notifier(capture)
    task = asyncio.create_task(
        pending_actions.request_confirmation("send_email", summary="s", risk="high", timeout_s=5)
    )
    await asyncio.sleep(0.01)  # let the notifier record the id
    assert pending_actions.resolve(seen["id"], True) is True
    assert await task is True


def test_confirmed_scope_authorizes_gate(monkeypatch):
    monkeypatch.setenv("JARVIS_TOOL_PERMISSION_MODE", "enforce")
    monkeypatch.delenv("JARVIS_TRUST_MODEL_CONFIRMATION", raising=False)
    assert is_confirmed() is False
    assert assess_tool_call("send_email", {"to": "x@y.com"}).allowed is False
    with confirmed_scope():
        assert is_confirmed() is True
        assert assess_tool_call("send_email", {"to": "x@y.com"}).allowed is True
    assert is_confirmed() is False
