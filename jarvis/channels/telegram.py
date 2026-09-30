"""Talk to JARVIS from Telegram.

Setup:
1. Create a bot with @BotFather and copy its token.
2. Find your numeric user id (e.g. message @userinfobot).
3. Set TELEGRAM_BOT_TOKEN (saved to Keychain from Settings, or in .env) and
   TELEGRAM_ALLOWED_USER_IDS=123456789, then restart JARVIS.

Only allow-listed user ids are answered; everyone else is ignored. High-risk
tool calls ask the owner (the first allowed id) for approval with inline
Approve/Deny buttons, and scheduled
routine results are pushed to the allowed users. Uses the Bot API directly
(long polling), so no public URL or webhook is needed.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from jarvis.config import settings
from jarvis.core import notify, pending_actions

logger = logging.getLogger("jarvis.channels.telegram")

API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE = 4000  # Telegram's limit is 4096 characters
POLL_TIMEOUT_S = 30

Runner = Callable[[str], Awaitable[str]]


MAX_CONCURRENT_REQUESTS = 4


def allowed_user_ids() -> list[int]:
    """Allowed user ids in configured order; the first one is the owner."""
    ids: list[int] = []
    for part in settings.TELEGRAM_ALLOWED_USER_IDS.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit() and int(part) not in ids:
            ids.append(int(part))
    return ids


def split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    text = text.strip() or "(empty response)"
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        cut = cut if cut > limit // 2 else limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    chunks.append(text)
    return chunks


class TelegramBridge:
    """Long-polls the Bot API and routes allowed users' messages to the brain."""

    def __init__(self, token: str, runner: Runner, client: httpx.AsyncClient | None = None):
        self._token = token
        self._runner = runner
        self._client = client or httpx.AsyncClient(timeout=POLL_TIMEOUT_S + 10)
        self._offset = 0
        ordered = allowed_user_ids()
        self._allowed = set(ordered)
        # Only the owner (first allowed id) sees and answers approval prompts,
        # so another allowed user can't approve an action on the owner's behalf.
        self._owner = ordered[0] if ordered else None
        # Where to send routine results (private chats with allowed users).
        self._chat_ids: set[int] = set(ordered)
        self._tasks: set[asyncio.Task] = set()
        self._slots = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def _call(self, method: str, **params: Any) -> Any:
        resp = await self._client.post(API.format(token=self._token, method=method), json=params)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data.get('description', resp.status_code)}")
        return data.get("result")

    async def send(self, chat_id: int, text: str, **extra: Any) -> None:
        for chunk in split_message(text):
            await self._call("sendMessage", chat_id=chat_id, text=chunk, **extra)

    async def broadcast(self, text: str) -> None:
        for chat_id in self._chat_ids:
            await self.send(chat_id, text)

    async def confirmation_notifier(self, payload: dict[str, Any]) -> None:
        """pending_actions notifier: ask allowed users to approve a high-risk tool call."""
        if payload.get("type") != "confirmation_required":
            return
        action = payload["confirmation"]
        keyboard = {"inline_keyboard": [[
            {"text": "Approve", "callback_data": f"approve:{action['id']}"},
            {"text": "Deny", "callback_data": f"deny:{action['id']}"},
        ]]}
        text = f"JARVIS wants to run {action['tool']} ({action['risk']} risk):\n{action['summary']}"
        if self._owner is not None:
            await self.send(self._owner, text, reply_markup=keyboard)

    async def handle_update(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query")
        if callback:
            if int(callback.get("from", {}).get("id", 0)) != self._owner:
                return
            decision, _, action_id = str(callback.get("data", "")).partition(":")
            resolved = pending_actions.resolve(action_id, approved=decision == "approve")
            await self._call(
                "answerCallbackQuery",
                callback_query_id=callback["id"],
                text=("Approved" if decision == "approve" else "Denied") if resolved else "Already handled",
            )
            return

        message = update.get("message") or {}
        user_id = int(message.get("from", {}).get("id", 0))
        text = str(message.get("text", "")).strip()
        if user_id not in self._allowed:
            if text:
                logger.warning("Ignoring Telegram message from non-allowed user %s", user_id)
            return
        if not text:
            return
        chat_id = int(message["chat"]["id"])
        self._chat_ids.add(chat_id)
        if text == "/start":
            await self.send(chat_id, "JARVIS here. Ask me anything.")
            return
        async with self._slots:  # bound concurrent brain requests
            await self._call("sendChatAction", chat_id=chat_id, action="typing")
            try:
                reply = await self._runner(text)
            except Exception as exc:
                logger.error("Telegram request failed: %s", exc)
                reply = "Sorry, something went wrong handling that."
            await self.send(chat_id, reply)

    async def run(self) -> None:
        if not self._allowed:
            logger.warning("Telegram bridge not started: TELEGRAM_ALLOWED_USER_IDS is empty.")
            return
        pending_actions.add_notifier(self.confirmation_notifier)
        notify.add_channel(self.broadcast)
        logger.info("Telegram bridge running for %d allowed user(s).", len(self._allowed))
        try:
            while True:
                try:
                    updates = await self._call(
                        "getUpdates", offset=self._offset, timeout=POLL_TIMEOUT_S,
                        allowed_updates=["message", "callback_query"],
                    )
                except (httpx.HTTPError, RuntimeError) as exc:
                    logger.warning("Telegram polling error: %s", exc)
                    await asyncio.sleep(5)
                    continue
                for update in updates or []:
                    self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                    # Each message runs in its own task so a slow request doesn't block approvals.
                    task = asyncio.create_task(self.handle_update(update))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
        finally:
            pending_actions.remove_notifier(self.confirmation_notifier)
            notify.remove_channel(self.broadcast)
            await self._client.aclose()
