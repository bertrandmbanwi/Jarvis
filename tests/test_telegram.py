"""Telegram bridge: allow-list, message routing, approval buttons."""

import pytest

from jarvis.channels import telegram
from jarvis.config import settings
from jarvis.core import pending_actions


class FakeBot:
    def __init__(self):
        self.calls = []

    async def call(self, method, **params):
        self.calls.append((method, params))
        return True


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_USER_IDS", "111,222")
    handled = []

    async def runner(text):
        handled.append(text)
        return "Done, sir."

    b = telegram.TelegramBridge("token", runner=runner)
    fake = FakeBot()
    monkeypatch.setattr(b, "_call", fake.call)
    return b, fake, handled


def msg(user_id, text, chat_id=5):
    return {"update_id": 1, "message": {"from": {"id": user_id}, "chat": {"id": chat_id}, "text": text}}


@pytest.mark.asyncio
async def test_allowed_user_gets_a_reply(bridge):
    b, fake, handled = bridge
    await b.handle_update(msg(111, "what's the weather?"))
    assert handled == ["what's the weather?"]
    assert ("sendMessage", {"chat_id": 5, "text": "Done, sir."}) in fake.calls


@pytest.mark.asyncio
async def test_other_users_are_ignored(bridge):
    b, fake, handled = bridge
    await b.handle_update(msg(999, "run rm -rf /"))
    assert handled == [] and fake.calls == []


@pytest.mark.asyncio
async def test_approval_buttons_resolve_pending_actions(bridge, monkeypatch):
    b, fake, _ = bridge
    resolved = []
    monkeypatch.setattr(pending_actions, "resolve", lambda action_id, approved: resolved.append((action_id, approved)) or True)
    # Build the payload the way pending_actions does, so field names can't drift.
    action = pending_actions.PendingAction(id="a1", tool_name="send_email", summary="Email Sam", risk="high", created_at=0.0)
    await b.confirmation_notifier({"type": "confirmation_required", "confirmation": action.public()})
    method, params = fake.calls[-1]
    assert method == "sendMessage" and params["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "approve:a1"

    assert params["chat_id"] == 111  # only the owner is asked
    for other in (999, 222):  # neither strangers nor other allowed users can approve
        await b.handle_update({"update_id": 2, "callback_query": {"id": "cb", "from": {"id": other}, "data": "approve:a1"}})
    assert resolved == []
    await b.handle_update({"update_id": 3, "callback_query": {"id": "cb", "from": {"id": 111}, "data": "approve:a1"}})
    assert resolved == [("a1", True)]


def test_long_replies_are_split():
    parts = telegram.split_message("line\n" * 2000)
    assert len(parts) > 1 and all(len(p) <= telegram.MAX_MESSAGE for p in parts)


def test_allowed_ids_parsing(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_ALLOWED_USER_IDS", "111, 222 ,abc,")
    assert telegram.allowed_user_ids() == [111, 222]
