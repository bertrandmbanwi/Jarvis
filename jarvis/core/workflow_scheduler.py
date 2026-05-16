"""Opt-in scheduled workflow execution."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from jarvis.config import settings
from jarvis.core import workflows

WorkflowRunner = Callable[[str], Awaitable[str]]

WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def parse_rrule(rrule: str) -> dict[str, str]:
    """Parse the simple RRULE subset Jarvis emits for local schedules."""
    parts: dict[str, str] = {}
    for part in str(rrule or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parts[key.strip().upper()] = value.strip().upper()
    return parts


def _int_part(parts: dict[str, str], key: str, default: int) -> int:
    try:
        return int(parts.get(key, str(default)).split(",", 1)[0])
    except (TypeError, ValueError):
        return default


def _last_run_in_current_minute(workflow: dict[str, Any], now: datetime) -> bool:
    last_run_at = workflow.get("last_run_at")
    if not last_run_at:
        return False
    try:
        last = datetime.fromtimestamp(float(last_run_at))
    except (TypeError, ValueError, OSError):
        return False
    return (
        last.year == now.year
        and last.month == now.month
        and last.day == now.day
        and last.hour == now.hour
        and last.minute == now.minute
    )


def is_workflow_due(workflow: dict[str, Any], now: datetime | None = None) -> bool:
    """Return true when an enabled scheduled workflow is due this minute."""
    now = now or datetime.now()
    if not workflow.get("enabled", True):
        return False

    trigger = workflow.get("trigger", {})
    if not isinstance(trigger, dict) or trigger.get("type") != "schedule":
        return False
    if _last_run_in_current_minute(workflow, now):
        return False

    parts = parse_rrule(str(trigger.get("rrule", "")))
    frequency = parts.get("FREQ", "DAILY")
    interval = max(1, _int_part(parts, "INTERVAL", 1))
    minute = _int_part(parts, "BYMINUTE", 0)
    hour = _int_part(parts, "BYHOUR", 9)

    if now.minute != minute:
        return False
    if frequency == "HOURLY":
        return now.hour % interval == 0
    if frequency == "DAILY":
        return now.hour == hour
    if frequency == "WEEKLY":
        byday = parts.get("BYDAY", WEEKDAY_CODES[now.weekday()])
        allowed_days = {day.strip() for day in byday.split(",") if day.strip()}
        return WEEKDAY_CODES[now.weekday()] in allowed_days and now.hour == hour
    return False


def get_scheduler_status(now: datetime | None = None) -> dict[str, Any]:
    """Return schedule readiness without running anything."""
    now = now or datetime.now()
    scheduled = [
        workflow for workflow in workflows.list_workflows(include_disabled=False)
        if isinstance(workflow.get("trigger"), dict) and workflow["trigger"].get("type") == "schedule"
    ]
    due = [workflow for workflow in scheduled if is_workflow_due(workflow, now)]
    return {
        "enabled": settings.WORKFLOW_SCHEDULER_ENABLED,
        "scheduled_count": len(scheduled),
        "due_count": len(due),
        "due_workflows": [{"id": item.get("id"), "name": item.get("name")} for item in due],
        "checked_at": now.timestamp(),
    }


async def run_due_workflows(
    *,
    runner: WorkflowRunner | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run all workflows due this minute and return their run records."""
    now = now or datetime.now()
    due = [
        workflow for workflow in workflows.list_workflows(include_disabled=False)
        if is_workflow_due(workflow, now)
    ]
    runs: list[dict[str, Any]] = []
    for workflow in due:
        run = await workflows.run_workflow(
            str(workflow.get("id", "")),
            runner=runner if not dry_run else None,
            triggered_by="schedule",
            dry_run=dry_run,
            run_time=now.timestamp(),
        )
        if run is not None:
            runs.append(run)
    return runs
