"""Workflow definitions: constants, release policies, templates, and normalizers.

Extracted from workflows.py to keep that module focused. Pure data and
validation helpers with no persistence or execution dependencies.
"""
from __future__ import annotations

import copy
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

TRIGGER_TYPES = {"manual", "schedule", "calendar_event", "startup", "hotkey", "webhook"}
ACTION_TYPES = {
    "prompt",
    "routine",
    "notification",
    "calendar_brief",
    "email_digest",
    "create_calendar_event",
    "wait_for_approval",
}
OAUTH_CALENDAR_PROVIDERS = {"google", "outlook"}
CONDITION_TYPES = {"always", "previous_status", "previous_response_contains", "previous_response_not_contains"}
ON_ERROR_POLICIES = {"stop", "continue"}
VISIBILITY = {"private", "team"}
RELEASE_CHANNELS = {"stable", "production"}
EDIT_CONFLICT_STRATEGIES = {"reject", "force"}
EDIT_SESSION_TTL_SECONDS = 90
WORKFLOW_PACKAGE_SCHEMA = "jarvis.workflow.package"
WORKFLOW_PACKAGE_SCHEMA_VERSION = 1
ASSERTION_TYPES = {
    "run_status_equals",
    "no_failed_steps",
    "output_contains",
    "output_not_contains",
    "action_status_equals",
    "max_duration_ms",
    "no_approval_required",
    "no_live_tools_during_dry_run",
}
RELEASE_POLICIES: dict[str, dict[str, Any]] = {
    "stable": {
        "channel": "stable",
        "approval_required": True,
        "required_approvals": 1,
        "requires_successful_dry_run": True,
        "requires_passing_assertions": True,
        "requires_cost_budget": True,
        "dry_run_max_age_seconds": 7 * 24 * 60 * 60,
        "requires_note": False,
        "description": "Stable promotions require one recent successful dry run, passing assertions, budget compliance, and one explicit approval.",
    },
    "production": {
        "channel": "production",
        "approval_required": True,
        "required_approvals": 1,
        "requires_successful_dry_run": True,
        "requires_passing_assertions": True,
        "requires_cost_budget": True,
        "dry_run_max_age_seconds": 7 * 24 * 60 * 60,
        "requires_note": True,
        "description": "Production promotions require a recent successful dry run, passing assertions, budget compliance, approval, and a release note.",
    },
}

WorkflowRunner = Callable[[str], Awaitable[str]]

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "morning_brief",
        "name": "Morning Brief",
        "description": "Weather, calendar, unread mail, and top follow-ups before the day starts.",
        "trigger": {"type": "schedule", "rrule": "FREQ=DAILY;BYHOUR=8;BYMINUTE=0"},
        "actions": [
            {"type": "calendar_brief", "title": "Read today's calendar"},
            {"type": "email_digest", "title": "Check unread mail"},
            {
                "type": "prompt",
                "title": "Prepare the brief",
                "prompt": "Create a concise morning brief with weather, calendar, mail, and follow-up priorities.",
            },
        ],
        "permissions": ["calendar:read", "mail:read", "llm:chat"],
        "tags": ["daily", "brief"],
    },
    {
        "id": "meeting_prep",
        "name": "Meeting Prep",
        "description": "Prepare context, open decisions, and questions before calendar events.",
        "trigger": {"type": "calendar_event", "minutes_before": 15},
        "actions": [
            {"type": "calendar_brief", "title": "Load event context"},
            {
                "type": "prompt",
                "title": "Draft prep notes",
                "prompt": "Summarize the upcoming meeting context, likely decisions, and questions to ask.",
            },
        ],
        "permissions": ["calendar:read", "llm:chat"],
        "tags": ["calendar", "meeting"],
    },
    {
        "id": "focus_mode",
        "name": "Focus Mode",
        "description": "Set up a focused work block and ask before changing noisy apps or notifications.",
        "trigger": {"type": "manual"},
        "actions": [
            {"type": "wait_for_approval", "title": "Confirm focus setup"},
            {
                "type": "prompt",
                "title": "Start focus session",
                "prompt": "Help me start a focus session: ask what I am working on, capture the goal, and suggest a timer.",
            },
        ],
        "permissions": ["llm:chat", "system:notify"],
        "tags": ["focus", "work"],
    },
]


def _now() -> float:
    return time.time()


def _clean_text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _release_channel(channel: str) -> str:
    normalized = str(channel or "stable").strip().lower()
    return normalized if normalized in RELEASE_CHANNELS else "stable"


def _normalize_trigger(trigger: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(trigger or {})
    trigger_type = str(raw.get("type") or "manual").strip().lower()
    if trigger_type not in TRIGGER_TYPES:
        trigger_type = "manual"
    normalized: dict[str, Any] = {"type": trigger_type}
    for key in ("rrule", "timezone", "event_filter", "hotkey"):
        if key in raw and str(raw[key]).strip():
            normalized[key] = _clean_text(raw[key], 240)
    if "minutes_before" in raw:
        try:
            normalized["minutes_before"] = max(0, min(int(raw["minutes_before"]), 1440))
        except (TypeError, ValueError):
            normalized["minutes_before"] = 15
    return normalized


def _normalize_action(action: dict[str, Any], index: int) -> dict[str, Any]:
    raw = dict(action or {})
    action_type = str(raw.get("type") or "prompt").strip().lower()
    if action_type not in ACTION_TYPES:
        action_type = "prompt"
    normalized = {
        "id": str(raw.get("id") or uuid.uuid4().hex),
        "type": action_type,
        "title": _clean_text(raw.get("title") or f"Step {index + 1}", 120),
        "requires_approval": bool(
            raw.get("requires_approval", action_type in {"wait_for_approval", "create_calendar_event"})
        ),
    }
    for key in (
        "prompt",
        "routine_id",
        "routine_name",
        "message",
        "calendar_name",
        "calendar_id",
        "provider",
        "timezone",
        "location",
        "notes",
        "start",
        "start_date",
        "end",
        "end_date",
        "mailbox",
    ):
        if key in raw:
            normalized[key] = _clean_text(raw[key], 2000)
    if "attendees" in raw and isinstance(raw["attendees"], list):
        normalized["attendees"] = [
            _clean_text(attendee, 240) for attendee in raw["attendees"] if _clean_text(attendee, 240)
        ][:50]
    for key in ("days", "count"):
        if key not in raw:
            continue
        try:
            normalized[key] = int(raw[key])
        except (TypeError, ValueError):
            continue
    if "condition" in raw and isinstance(raw["condition"], dict):
        normalized["condition"] = _normalize_condition(raw["condition"])
    if "retry_count" in raw:
        try:
            normalized["retry_count"] = max(0, min(int(raw["retry_count"]), 3))
        except (TypeError, ValueError):
            normalized["retry_count"] = 0
    if "retry_delay_ms" in raw:
        try:
            normalized["retry_delay_ms"] = max(0, min(int(raw["retry_delay_ms"]), 30000))
        except (TypeError, ValueError):
            normalized["retry_delay_ms"] = 0
    on_error = str(raw.get("on_error") or "stop").strip().lower()
    normalized["on_error"] = on_error if on_error in ON_ERROR_POLICIES else "stop"
    if "all_day" in raw:
        normalized["all_day"] = bool(raw["all_day"])
    return normalized


def _normalize_condition(condition: dict[str, Any]) -> dict[str, Any]:
    mode = str(condition.get("type") or "always").strip().lower()
    if mode not in CONDITION_TYPES:
        mode = "always"
    normalized = {"type": mode}
    if "action_id" in condition:
        normalized["action_id"] = _clean_text(condition.get("action_id"), 120)
    if "value" in condition:
        normalized["value"] = _clean_text(condition.get("value"), 500)
    return normalized


def _normalize_actions(actions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = [_normalize_action(action, index) for index, action in enumerate(actions or [])]
    if not normalized:
        normalized.append(_normalize_action({"type": "prompt", "prompt": "Run this workflow."}, 0))
    return normalized[:20]


def _normalize_assertion(assertion: dict[str, Any], index: int) -> dict[str, Any]:
    raw = dict(assertion or {})
    assertion_type = str(raw.get("type") or "run_status_equals").strip().lower()
    if assertion_type not in ASSERTION_TYPES:
        assertion_type = "run_status_equals"
    title = _clean_text(raw.get("title") or assertion_type.replace("_", " ").title(), 140)
    normalized: dict[str, Any] = {
        "id": str(raw.get("id") or uuid.uuid4().hex),
        "type": assertion_type,
        "title": title or f"Assertion {index + 1}",
        "enabled": bool(raw.get("enabled", True)),
    }
    if "action_id" in raw:
        normalized["action_id"] = _clean_text(raw.get("action_id"), 120)
    if "value" in raw:
        normalized["value"] = _clean_text(raw.get("value"), 1000)
    if "expected_status" in raw:
        normalized["expected_status"] = _clean_text(raw.get("expected_status"), 80)
    if "max_duration_ms" in raw:
        try:
            normalized["max_duration_ms"] = max(0, min(int(raw["max_duration_ms"]), 24 * 60 * 60 * 1000))
        except (TypeError, ValueError):
            normalized["max_duration_ms"] = 0
    return normalized


def _normalize_assertions(assertions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [_normalize_assertion(assertion, index) for index, assertion in enumerate(assertions or [])][:20]


def _normalize_budget(budget: dict[str, Any] | None) -> dict[str, Any]:
    raw = budget if isinstance(budget, dict) else {}
    normalized: dict[str, Any] = {}
    for key in ("max_cost_per_run_usd", "max_cost_per_day_usd", "max_cost_per_month_usd"):
        if key not in raw:
            continue
        try:
            value = float(raw.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            normalized[key] = round(min(value, 10000.0), 6)
    if normalized:
        normalized["enforce_on_release"] = bool(raw.get("enforce_on_release", True))
    return normalized


def _system_assertions() -> list[dict[str, Any]]:
    return [
        {
            "id": "system-run-completed",
            "type": "run_status_equals",
            "title": "Run completes successfully",
            "expected_status": "completed",
            "enabled": True,
            "system": True,
        },
        {
            "id": "system-no-failed-steps",
            "type": "no_failed_steps",
            "title": "No failed steps",
            "enabled": True,
            "system": True,
        },
        {
            "id": "system-dry-run-stays-dry",
            "type": "no_live_tools_during_dry_run",
            "title": "Dry run stays dry",
            "enabled": True,
            "system": True,
        },
    ]


def _assertions_for_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    assertions_raw = workflow.get("assertions")
    assertions = assertions_raw if isinstance(assertions_raw, list) else []
    normalized = [_normalize_assertion(item, index) for index, item in enumerate(assertions) if isinstance(item, dict)]
    return [*copy.deepcopy(_system_assertions()), *normalized]
