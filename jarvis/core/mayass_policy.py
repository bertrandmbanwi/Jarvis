"""MayAss confirmation policy.

Phase 6 only builds the brake: classify human decisions for pending actions.
It does not execute tools or grant MayAss tool ownership.
"""
from __future__ import annotations

from dataclasses import dataclass

CONFIRM_ONCE = "confirm_once"
CONFIRM_ALWAYS = "confirm_always"
DENY = "deny"
ALLOWED_DECISIONS = [CONFIRM_ONCE, CONFIRM_ALWAYS, DENY]


@dataclass(frozen=True)
class ConfirmationDecision:
    allowed: bool
    final_decision: str
    reason: str


def normalize_decision(decision: str | bool) -> str:
    if decision is True:
        return CONFIRM_ONCE
    if decision is False:
        return DENY
    value = (decision or DENY).strip().lower()
    return value if value in ALLOWED_DECISIONS else DENY


def evaluate_confirmation_decision(risk: str, decision: str | bool) -> ConfirmationDecision:
    """Evaluate a user confirmation decision without running the action."""
    final_decision = normalize_decision(decision)
    risk_value = (risk or "medium").strip().lower()

    if final_decision == DENY:
        return ConfirmationDecision(False, DENY, "User denied the action.")

    if final_decision == CONFIRM_ALWAYS and risk_value == "critical":
        return ConfirmationDecision(
            False,
            DENY,
            "Critical actions cannot be permanently approved.",
        )

    return ConfirmationDecision(True, final_decision, "User confirmed the action.")
