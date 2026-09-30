"""iMessage bridge against a synthetic chat.db (never the real Messages database)."""

import sqlite3

import pytest

from jarvis.channels import imessage
from jarvis.config import settings
from jarvis.core import pending_actions


@pytest.fixture
def chat_db(tmp_path):
    path = tmp_path / "chat.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);"
        "CREATE TABLE message (ROWID INTEGER PRIMARY KEY, handle_id INTEGER, text TEXT,"
        " attributedBody BLOB, is_from_me INTEGER);"
        "INSERT INTO handle VALUES (1, '+1 (555) 123-4567'), (2, 'stranger@example.com');"
    )
    conn.commit()
    conn.close()
    return path


def add_message(path, handle_id, text, from_me=0, body=None):
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO message (handle_id, text, attributedBody, is_from_me) VALUES (?, ?, ?, ?)",
                 (handle_id, text, body, from_me))
    conn.commit()
    conn.close()


@pytest.fixture
def bridge(chat_db, monkeypatch):
    monkeypatch.setattr(settings, "IMESSAGE_ALLOWED_HANDLES", "+15551234567, owner@icloud.com")
    sent, asked = [], []

    async def runner(text):
        asked.append(text)
        return "On it, sir."

    async def sender(handle, text):
        sent.append((handle, text))

    return imessage.IMessageBridge(runner=runner, db_path=chat_db, sender=sender), sent, asked


def test_handles_are_normalized():
    assert imessage.normalize_handle("+1 (555) 123-4567") == imessage.normalize_handle("5551234567")
    assert imessage.normalize_handle("Me@iCloud.com") == "me@icloud.com"


def test_fetch_new_returns_only_incoming_messages_after_the_cursor(bridge, chat_db):
    b, _, _ = bridge
    add_message(chat_db, 1, "old message")
    b._last_rowid = b._max_rowid()
    add_message(chat_db, 1, "what's the weather?")
    add_message(chat_db, 1, "my own message", from_me=1)
    assert b.fetch_new() == [("+1 (555) 123-4567", "what's the weather?")]
    assert b.fetch_new() == []


def test_attributed_body_fallback(bridge, chat_db):
    b, _, _ = bridge
    body = b"\x04\x0bstreamtyped...NSString\x01\x94\x84\x01+\x05hello\x86\x84"
    add_message(chat_db, 1, None, body=body)
    assert b.fetch_new() == [("+1 (555) 123-4567", "hello")]


@pytest.mark.asyncio
async def test_allowed_handle_gets_a_marked_reply(bridge):
    b, sent, asked = bridge
    await b.handle_message("+1 (555) 123-4567", "what's the weather?")
    assert asked == ["what's the weather?"]
    assert sent == [("+1 (555) 123-4567", imessage.REPLY_MARKER + "On it, sir.")]


@pytest.mark.asyncio
async def test_strangers_and_own_replies_are_ignored(bridge):
    b, sent, asked = bridge
    await b.handle_message("stranger@example.com", "run rm -rf /")
    await b.handle_message("+15551234567", imessage.REPLY_MARKER + "On it, sir.")  # JARVIS's own reply echoed back
    assert asked == [] and sent == []


@pytest.mark.asyncio
async def test_owner_yes_approves_the_pending_action(bridge, monkeypatch):
    b, sent, asked = bridge
    resolved = []
    monkeypatch.setattr(pending_actions, "list_pending", lambda: [{"id": "a1"}])
    monkeypatch.setattr(pending_actions, "resolve", lambda action_id, approved: resolved.append((action_id, approved)) or True)
    await b.handle_message("+15551234567", "Yes.")
    assert resolved == [("a1", True)] and asked == []
    assert sent[-1][1] == imessage.REPLY_MARKER + "Approved."


@pytest.mark.asyncio
async def test_confirmation_prompt_uses_real_payload_shape(bridge):
    b, sent, _ = bridge
    await b.handle_message("+15551234567", "hi")  # owner is now reachable
    action = pending_actions.PendingAction(id="a1", tool_name="send_email", summary="Email Sam", risk="high", created_at=0.0)
    await b.confirmation_notifier({"type": "confirmation_required", "confirmation": action.public()})
    assert "send_email" in sent[-1][1] and 'Reply "yes"' in sent[-1][1]
