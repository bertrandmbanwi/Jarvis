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

from jarvis.core.mayass_policy import ALLOWED_DECISIONS, evaluate_confirmation_decision

logger = logging.getLogger("jarvis.pending_actions")

DEFAULT_TIMEOUT_S = 120.0

Notifier = Callable[[dict[str, Any]], Awaitable[Any]]

# Multiple channels can prompt for the same confirmation (the web modal and,
# in voice mode, a spoken question); whichever answers first wins via resolve().
_notifiers: list[Notifier] = []
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
    action_type: str = ""
    affected_targets: tuple[str, ...] = ()
    reversible: bool = False
    reason: str = ""
    consequence_if_denied: str = ""
    permanent_policy_key: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool_name,
            "summary": self.summary,
            "risk": self.risk,
            "created_at": self.created_at,
            "action_type": self.action_type or self.tool_name,
            "affected_targets": list(self.affected_targets),
            "reversible": self.reversible,
            "reason": self.reason,
            "consequence_if_denied": self.consequence_if_denied,
            "permanent_policy_key": self.permanent_policy_key,
            "allowed_decisions": ALLOWED_DECISIONS,
        }


def add_notifier(notifier: Notifier) -> None:
    """Register an async channel that pushes confirmation prompts (web, voice, ...)."""
    if notifier not in _notifiers:
        _notifiers.append(notifier)


def remove_notifier(notifier: Notifier) -> None:
    """Unregister a previously added confirmation channel."""
    _notifiers[:] = [n for n in _notifiers if n != notifier]


def confirmation_available() -> bool:
    """Whether there is a channel to ask a human for confirmation."""
    return bool(_notifiers)


def list_pending() -> list[dict[str, Any]]:
    """Return the currently pending actions (for a reconnecting client)."""
    return [action.public() for action in _pending.values()]


def create_pending_action(
    *,
    action_type: str,
    summary: str,
    risk: str,
    affected_targets: list[str] | tuple[str, ...] = (),
    reversible: bool = False,
    reason: str = "",
    consequence_if_denied: str = "",
    permanent_policy_key: str = "",
) -> PendingAction:
    """Create a rich pending action without executing anything."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    action = PendingAction(
        id=uuid.uuid4().hex,
        tool_name=action_type,
        action_type=action_type,
        summary=summary,
        risk=risk,
        affected_targets=tuple(affected_targets),
        reversible=reversible,
        reason=reason,
        consequence_if_denied=consequence_if_denied,
        permanent_policy_key=permanent_policy_key,
        created_at=time.time(),
    )
    _pending[action.id] = action
    _futures[action.id] = future
    return action


def resolve(action_id: str, approved: bool | str) -> bool:
    """Answer a pending confirmation. Returns False if it is unknown or settled."""
    action = _pending.get(action_id)
    future = _futures.get(action_id)
    if future is None or future.done():
        return False
    decision = evaluate_confirmation_decision(action.risk if action else "medium", approved)
    if decision.final_decision == "deny" and approved not in {False, "deny"}:
        return False

    future.set_result(decision.allowed)
    _pending.pop(action_id, None)
    _futures.pop(action_id, None)
    return True


async def request_confirmation(
    tool_name: str,
    *,
    summary: str,
    risk: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> bool:
    """Ask a human to approve a high-risk tool call; return True only if approved.

    Returns False (deny) when no channel is available or the request times out,
    so an unattended server never runs an unconfirmed high-risk tool.
    """
    if not _notifiers:
        return False

    action = create_pending_action(
        action_type=tool_name,
        summary=summary,
        risk=risk,
        reason="Tool call requires human confirmation.",
        consequence_if_denied="The tool call will not run.",
    )
    future = _futures[action.id]

    payload = {"type": "confirmation_required", "confirmation": action.public()}
    delivered = False
    for notifier in list(_notifiers):
        try:
            await notifier(payload)
            delivered = True
        except Exception as exc:  # one bad channel must not hang the tool call
            logger.warning("Confirmation notifier failed for %s: %s", tool_name, exc)
    if not delivered:
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
