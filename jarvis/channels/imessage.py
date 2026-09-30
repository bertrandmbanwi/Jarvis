"""Talk to JARVIS over iMessage (macOS only).

Incoming messages are read from the local Messages database
(~/Library/Messages/chat.db) and replies are sent through the Messages app.

Setup:
1. Give the app that runs JARVIS (Terminal, iTerm, or the JARVIS app) Full
   Disk Access in System Settings > Privacy & Security, so it can read chat.db.
2. Set IMESSAGE_ALLOWED_HANDLES to the phone numbers or emails that may talk
   to JARVIS, e.g. "+15551234567,me@icloud.com". The first one is the owner.
3. Restart JARVIS. macOS asks once for permission to control Messages.

Only allow-listed handles are answered. High-risk tool calls ask the owner
for approval: reply "yes" or "no". Replies start with a marker so JARVIS
never answers its own messages (which matters when you text yourself).
"""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from jarvis.config import settings
from jarvis.core import notify, pending_actions

logger = logging.getLogger("jarvis.channels.imessage")

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"
REPLY_MARKER = "🤖 "
POLL_SECONDS = 3.0
MAX_MESSAGE = 3000
_YES = {"yes", "y", "approve", "approved", "ok", "do it", "go ahead"}
_NO = {"no", "n", "deny", "denied", "cancel", "stop"}

SEND_SCRIPT = (
    "on run {targetHandle, messageText}\n"
    '  tell application "Messages"\n'
    "    set targetService to 1st account whose service type = iMessage\n"
    "    send messageText to participant targetHandle of targetService\n"
    "  end tell\n"
    "end run"
)

Runner = Callable[[str], Awaitable[str]]
Sender = Callable[[str, str], Awaitable[None]]


def normalize_handle(handle: str) -> str:
    """Compare handles loosely: emails case-insensitively, phone numbers by digits."""
    handle = handle.strip().lower()
    if "@" in handle:
        return handle
    digits = re.sub(r"\D", "", handle)
    return digits[-10:] if len(digits) >= 10 else digits


def allowed_handles() -> list[str]:
    """Allowed handles in configured order; the first one is the owner."""
    handles: list[str] = []
    for part in settings.IMESSAGE_ALLOWED_HANDLES.split(","):
        normalized = normalize_handle(part)
        if normalized and normalized not in handles:
            handles.append(normalized)
    return handles


def text_from_attributed_body(blob: bytes | None) -> str:
    """Best-effort text from the attributedBody blob newer macOS uses instead of `text`."""
    if not blob:
        return ""
    marker = blob.find(b"NSString")
    if marker == -1:
        return ""
    start = blob.find(b"+", marker)
    if start == -1:
        return ""
    start += 1
    length = blob[start]
    start += 1
    if length == 0x81:  # two-byte little-endian length follows
        length = int.from_bytes(blob[start:start + 2], "little")
        start += 2
    return blob[start:start + length].decode("utf-8", errors="replace")


async def send_with_messages_app(handle: str, text: str) -> None:
    # Handle and text are passed as arguments, never interpolated into the script.
    process = await asyncio.create_subprocess_exec(
        "osascript", "-e", SEND_SCRIPT, handle, text,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"Messages send failed: {stderr.decode(errors='replace')[:200]}")


class IMessageBridge:
    """Polls chat.db for new messages from allowed handles and answers them."""

    def __init__(self, runner: Runner, db_path: Path = CHAT_DB, sender: Sender = send_with_messages_app):
        self._runner = runner
        self._db_path = db_path
        self._send = sender
        self._handles = allowed_handles()
        self._owner = self._handles[0] if self._handles else None
        # Original (un-normalized) handle to reply to, learned from incoming messages.
        self._reply_to: dict[str, str] = {}
        self._last_rowid = 0
        self._recent_sent: deque[str] = deque(maxlen=20)
        self._tasks: set[asyncio.Task] = set()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True, timeout=5)

    def _max_rowid(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(ROWID), 0) FROM message").fetchone()
        return int(row[0])

    def fetch_new(self) -> list[tuple[str, str]]:
        """New (handle, text) pairs since the last poll, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT message.ROWID, handle.id, message.text, message.attributedBody "
                "FROM message JOIN handle ON message.handle_id = handle.ROWID "
                "WHERE message.ROWID > ? AND message.is_from_me = 0 ORDER BY message.ROWID",
                (self._last_rowid,),
            ).fetchall()
        messages = []
        for rowid, handle, text, body in rows:
            self._last_rowid = max(self._last_rowid, int(rowid))
            content = (text or text_from_attributed_body(body)).strip()
            if content:
                messages.append((str(handle), content))
        return messages

    async def reply(self, handle: str, text: str) -> None:
        text = (text.strip() or "(empty response)")[:MAX_MESSAGE]
        self._recent_sent.append(text)
        await self._send(handle, REPLY_MARKER + text)

    async def broadcast(self, text: str) -> None:
        if self._owner and self._owner in self._reply_to:
            await self.reply(self._reply_to[self._owner], text)

    async def confirmation_notifier(self, payload: dict[str, Any]) -> None:
        if payload.get("type") != "confirmation_required":
            return
        if not (self._owner and self._owner in self._reply_to):
            raise RuntimeError("iMessage owner has not messaged JARVIS yet")
        action = payload["confirmation"]
        await self.reply(
            self._reply_to[self._owner],
            f"JARVIS wants to run {action['tool']} ({action['risk']} risk): {action['summary']}\n"
            'Reply "yes" to approve or "no" to deny.',
        )

    def _is_own_message(self, text: str) -> bool:
        return text.startswith(REPLY_MARKER.strip()) or text in self._recent_sent

    async def handle_message(self, handle: str, text: str) -> None:
        normalized = normalize_handle(handle)
        if normalized not in self._handles or self._is_own_message(text):
            return
        self._reply_to[normalized] = handle

        # The owner's yes/no answers the oldest pending approval.
        answer = text.strip().lower().rstrip(".!")
        if normalized == self._owner and answer in _YES | _NO:
            pending = pending_actions.list_pending()
            if pending:
                pending_actions.resolve(pending[0]["id"], approved=answer in _YES)
                await self.reply(handle, "Approved." if answer in _YES else "Denied.")
                return

        try:
            response = await self._runner(text)
        except Exception as exc:
            logger.error("iMessage request failed: %s", exc)
            response = "Sorry, something went wrong handling that."
        await self.reply(handle, response)

    async def run(self) -> None:
        if not self._handles:
            logger.warning("iMessage bridge not started: IMESSAGE_ALLOWED_HANDLES is empty.")
            return
        try:
            # Start from now: never answer messages that arrived before JARVIS started.
            self._last_rowid = await asyncio.to_thread(self._max_rowid)
        except sqlite3.Error as exc:
            logger.error(
                "iMessage bridge can't read %s (%s). Grant Full Disk Access to the app running JARVIS.",
                self._db_path, exc,
            )
            return
        pending_actions.add_notifier(self.confirmation_notifier)
        notify.add_channel(self.broadcast)
        logger.info("iMessage bridge running for %d allowed handle(s).", len(self._handles))
        try:
            while True:
                try:
                    messages = await asyncio.to_thread(self.fetch_new)
                except sqlite3.Error as exc:
                    logger.warning("iMessage poll failed: %s", exc)
                    messages = []
                for handle, text in messages:
                    task = asyncio.create_task(self.handle_message(handle, text))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                await asyncio.sleep(POLL_SECONDS)
        finally:
            pending_actions.remove_notifier(self.confirmation_notifier)
            notify.remove_channel(self.broadcast)
