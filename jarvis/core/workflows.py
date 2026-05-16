"""Team-ready workflow definitions and execution history.

This is the foundation for a future visual workflow builder. Workflows are
stored as plain JSON for now so the local app remains easy to inspect, backup,
and migrate to SQLite/Postgres later.
"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from jarvis.config import settings
from jarvis.core import routines

WORKFLOWS_FILE = settings.DATA_DIR / "workflows.json"
WORKFLOW_RUNS_FILE = settings.DATA_DIR / "workflow_runs.json"

TRIGGER_TYPES = {"manual", "schedule", "calendar_event", "startup", "hotkey", "webhook"}
ACTION_TYPES = {"prompt", "routine", "notification", "calendar_brief", "email_digest", "wait_for_approval"}
VISIBILITY = {"private", "team"}

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


def _load_json(path: Path, default: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not path.exists():
        _save_json(path, default)
        return default
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return default
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _clean_text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


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
        "requires_approval": bool(raw.get("requires_approval", action_type == "wait_for_approval")),
    }
    for key in ("prompt", "routine_id", "routine_name", "message"):
        if key in raw:
            normalized[key] = _clean_text(raw[key], 2000)
    return normalized


def _normalize_actions(actions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized = [_normalize_action(action, index) for index, action in enumerate(actions or [])]
    if not normalized:
        normalized.append(_normalize_action({"type": "prompt", "prompt": "Run this workflow."}, 0))
    return normalized[:20]


def _load_workflows() -> list[dict[str, Any]]:
    return _load_json(WORKFLOWS_FILE, [])


def _save_workflows(items: list[dict[str, Any]]) -> None:
    _save_json(WORKFLOWS_FILE, items)


def _load_runs() -> list[dict[str, Any]]:
    return _load_json(WORKFLOW_RUNS_FILE, [])


def _save_runs(items: list[dict[str, Any]]) -> None:
    _save_json(WORKFLOW_RUNS_FILE, items[-500:])


def list_templates() -> list[dict[str, Any]]:
    return [dict(template) for template in TEMPLATES]


def list_workflows(include_disabled: bool = True) -> list[dict[str, Any]]:
    items = _load_workflows()
    if not include_disabled:
        items = [item for item in items if item.get("enabled", True)]
    return sorted(items, key=lambda item: float(item.get("updated_at", 0)), reverse=True)


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    return next((item for item in _load_workflows() if item.get("id") == workflow_id), None)


def create_workflow(
    *,
    name: str,
    description: str = "",
    trigger: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
    enabled: bool = True,
    tags: list[str] | None = None,
    owner_id: str = "local-owner",
    visibility: str = "private",
    permissions: list[str] | None = None,
) -> dict[str, Any]:
    now = _now()
    item = {
        "id": uuid.uuid4().hex,
        "version": 1,
        "name": _clean_text(name, 120),
        "description": _clean_text(description, 500),
        "trigger": _normalize_trigger(trigger),
        "actions": _normalize_actions(actions),
        "enabled": bool(enabled),
        "tags": [_clean_text(tag, 40) for tag in (tags or [])][:12],
        "owner_id": _clean_text(owner_id or "local-owner", 80),
        "visibility": visibility if visibility in VISIBILITY else "private",
        "permissions": sorted({_clean_text(permission, 80) for permission in (permissions or []) if permission}),
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
    }
    items = _load_workflows()
    items.append(item)
    _save_workflows(items)
    return item


def create_workflow_from_template(template_id: str, *, owner_id: str = "local-owner") -> dict[str, Any] | None:
    template = next((item for item in TEMPLATES if item["id"] == template_id), None)
    if template is None:
        return None
    return create_workflow(
        name=template["name"],
        description=template["description"],
        trigger=template["trigger"],
        actions=template["actions"],
        enabled=True,
        tags=template["tags"],
        owner_id=owner_id,
        visibility="private",
        permissions=template["permissions"],
    )


def update_workflow(workflow_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    items = _load_workflows()
    for item in items:
        if item.get("id") != workflow_id:
            continue
        if "name" in updates:
            item["name"] = _clean_text(updates["name"], 120)
        if "description" in updates:
            item["description"] = _clean_text(updates["description"], 500)
        if "trigger" in updates:
            item["trigger"] = _normalize_trigger(updates["trigger"])
        if "actions" in updates:
            item["actions"] = _normalize_actions(updates["actions"])
        if "enabled" in updates:
            item["enabled"] = bool(updates["enabled"])
        if "tags" in updates:
            item["tags"] = [_clean_text(tag, 40) for tag in list(updates["tags"] or [])][:12]
        if "visibility" in updates:
            visibility = str(updates["visibility"])
            item["visibility"] = visibility if visibility in VISIBILITY else item.get("visibility", "private")
        if "permissions" in updates:
            item["permissions"] = sorted({_clean_text(permission, 80) for permission in updates["permissions"]})
        item["version"] = int(item.get("version", 1)) + 1
        item["updated_at"] = _now()
        _save_workflows(items)
        return item
    return None


def delete_workflow(workflow_id: str) -> bool:
    items = _load_workflows()
    kept = [item for item in items if item.get("id") != workflow_id]
    if len(kept) == len(items):
        return False
    _save_workflows(kept)
    return True


def list_runs(workflow_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    runs = _load_runs()
    if workflow_id:
        runs = [run for run in runs if run.get("workflow_id") == workflow_id]
    return sorted(runs, key=lambda run: float(run.get("started_at", 0)), reverse=True)[: max(1, min(limit, 200))]


def _record_run(run: dict[str, Any]) -> dict[str, Any]:
    runs = _load_runs()
    runs.append(run)
    _save_runs(runs)
    return run


def _mark_workflow_run(workflow_id: str, timestamp: float | None = None) -> None:
    items = _load_workflows()
    now = timestamp or _now()
    for item in items:
        if item.get("id") == workflow_id:
            item["last_run_at"] = now
            item["updated_at"] = now
            break
    _save_workflows(items)


def _find_routine(action: dict[str, Any]) -> dict[str, Any] | None:
    routine_id = str(action.get("routine_id") or "")
    if routine_id:
        return routines.get_routine(routine_id)
    routine_name = str(action.get("routine_name") or "").strip().lower()
    if not routine_name:
        return None
    return next((item for item in routines.list_routines() if str(item.get("name", "")).lower() == routine_name), None)


async def run_workflow(
    workflow_id: str,
    *,
    runner: WorkflowRunner | None = None,
    triggered_by: str = "manual",
    dry_run: bool = False,
    run_time: float | None = None,
) -> dict[str, Any] | None:
    workflow = get_workflow(workflow_id)
    if workflow is None:
        return None

    started_at = run_time or _now()
    action_results: list[dict[str, Any]] = []
    status = "completed"
    error = ""

    try:
        for action in workflow.get("actions", []):
            action_type = str(action.get("type", "prompt"))
            result: dict[str, Any] = {
                "action_id": action.get("id"),
                "type": action_type,
                "title": action.get("title", ""),
                "status": "prepared" if dry_run or runner is None else "completed",
            }

            if action.get("requires_approval"):
                result.update({"status": "approval_required", "message": "This action requires user approval."})
            elif action_type == "prompt":
                prompt = str(action.get("prompt") or action.get("message") or workflow.get("description") or workflow["name"])
                result["prompt"] = prompt
                if runner is not None and not dry_run:
                    result["response"] = await runner(prompt)
            elif action_type == "routine":
                routine = _find_routine(action)
                if routine is None:
                    result.update({"status": "skipped", "message": "Routine not found."})
                else:
                    prompt = str(routine.get("prompt", ""))
                    result["routine_id"] = routine.get("id")
                    result["prompt"] = prompt
                    if runner is not None and not dry_run:
                        routines.mark_routine_run(str(routine.get("id")))
                        result["response"] = await runner(prompt)
            elif action_type == "calendar_brief":
                result["message"] = "Calendar read step prepared. Provider execution will attach here."
            elif action_type == "email_digest":
                result["message"] = "Mail digest step prepared. Provider execution will attach here."
            elif action_type == "notification":
                result["message"] = str(action.get("message") or "Workflow notification prepared.")
            elif action_type == "wait_for_approval":
                result.update({"status": "approval_required", "message": "Workflow paused for explicit approval."})
            action_results.append(result)
    except Exception as exc:
        status = "failed"
        error = str(exc)

    completed_at = _now()
    run = {
        "id": uuid.uuid4().hex,
        "workflow_id": workflow_id,
        "workflow_name": workflow.get("name", ""),
        "status": status,
        "triggered_by": triggered_by,
        "dry_run": dry_run,
        "action_results": action_results,
        "error": error,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": round((completed_at - started_at) * 1000, 1),
    }
    _record_run(run)
    _mark_workflow_run(workflow_id, timestamp=started_at)
    return run


def get_overview() -> dict[str, Any]:
    workflows = list_workflows()
    runs = list_runs(limit=10)
    return {
        "workflow_count": len(workflows),
        "enabled_count": sum(1 for item in workflows if item.get("enabled", True)),
        "template_count": len(TEMPLATES),
        "recent_runs": runs,
        "next_foundation_steps": [
            "Connect OAuth-backed calendar providers.",
            "Replace JSON storage with a multi-user database when team mode is enabled.",
            "Add a visual builder for triggers, conditions, and actions.",
        ],
    }
