"""Outbound notification channels (e.g. Telegram) for proactive messages.

Channels register an async sender; scheduled routines and other proactive
features call notify() without knowing which channels are configured.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger("jarvis.notify")

Sender = Callable[[str], Awaitable[None]]
_senders: list[Sender] = []


def add_channel(sender: Sender) -> None:
    if sender not in _senders:
        _senders.append(sender)


def remove_channel(sender: Sender) -> None:
    if sender in _senders:
        _senders.remove(sender)


async def notify(text: str) -> None:
    for sender in list(_senders):
        try:
            await sender(text)
        except Exception as exc:
            logger.warning("Notification channel failed: %s", exc)
