"""In-process registry of tool calls awaiting human confirmation.

When the permission gate needs confirmation for a high-risk tool and no server
grant is active, the executor asks here: request_confirmation() registers a
pending action, notifies connected clients through a notifier hook the server
installs, and awaits an approve/deny decision with a timeout. A UI approval
endpoint (or, later, the voice loop) calls resolve() to answer.

State is in-memory only — confirmations are short-lived and interactive, so a
server restart simply times out any in-flight request, which is denied (fail
safe). The redacted summary is stored, never the raw tool arguments.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jarvis.pending_actions")

DEFAULT_TIMEOUT_S = 120.0

Notifier = Callable[[dict[str, Any]], Awaitable[Any]]

_notifier: Notifier | None = None
_pending: dict[str, PendingAction] = {}
_futures: dict[str, asyncio.Future[bool]] = {}


@dataclass(frozen=True)
class PendingAction:
    """A tool call awaiting human approval (redacted for display)."""

    id: str
    tool_name: str
    summary: str
    risk: str
    created_at: float

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool_name,
            "summary": self.summary,
            "risk": self.risk,
            "created_at": self.created_at,
        }


def set_notifier(notifier: Notifier | None) -> None:
    """Install (or clear) the async callback used to push confirmation prompts."""
    global _notifier
    _notifier = notifier


def confirmation_available() -> bool:
    """Whether there is a channel to ask a human for confirmation."""
    return _notifier is not None


def list_pending() -> list[dict[str, Any]]:
    """Return the currently pending actions (for a reconnecting client)."""
    return [action.public() for action in _pending.values()]


def resolve(action_id: str, approved: bool) -> bool:
    """Answer a pending confirmation. Returns False if it is unknown or settled."""
    future = _futures.get(action_id)
    if future is None or future.done():
        return False
    future.set_result(approved)
    return True


async def request_confirmation(
    tool_name: str,
    *,
    summary: str,
    risk: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> bool:
    """Ask a human to approve a high-risk tool call; return True only if approved.

    Returns False (deny) when there is no notifier installed or the request times
    out, so an unattended server never runs an unconfirmed high-risk tool.
    """
    if _notifier is None:
        return False

    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    action = PendingAction(
        id=uuid.uuid4().hex,
        tool_name=tool_name,
        summary=summary,
        risk=risk,
        created_at=time.time(),
    )
    _pending[action.id] = action
    _futures[action.id] = future

    try:
        await _notifier({"type": "confirmation_required", "confirmation": action.public()})
    except Exception as exc:  # notifier failure must not hang the tool call
        logger.warning("Confirmation notifier failed for %s: %s", tool_name, exc)
        _pending.pop(action.id, None)
        _futures.pop(action.id, None)
        return False

    try:
        return await asyncio.wait_for(future, timeout=timeout_s)
    except TimeoutError:
        logger.info("Confirmation for %s timed out after %.0fs.", tool_name, timeout_s)
        return False
    finally:
        _pending.pop(action.id, None)
        _futures.pop(action.id, None)
