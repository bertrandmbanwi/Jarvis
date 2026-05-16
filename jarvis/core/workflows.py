"""Team-ready workflow definitions and execution history.

This is the foundation for a visual workflow builder. Workflow state is stored
in SQLite, with a lazy importer for the earlier JSON files.
"""
from __future__ import annotations

import asyncio
import copy
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from jarvis.config import settings
from jarvis.core import routines, sqlite_state, workflow_run_store

WORKFLOWS_FILE = settings.DATA_DIR / "workflows.json"
WORKFLOW_RUNS_FILE = settings.DATA_DIR / "workflow_runs.json"
WORKFLOW_APPROVALS_FILE = settings.DATA_DIR / "workflow_approvals.json"
WORKFLOW_VERSIONS_FILE = settings.DATA_DIR / "workflow_versions.json"
WORKFLOW_RELEASES_FILE = settings.DATA_DIR / "workflow_releases.json"

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
RELEASE_POLICIES: dict[str, dict[str, Any]] = {
    "stable": {
        "channel": "stable",
        "approval_required": True,
        "required_approvals": 1,
        "requires_successful_dry_run": True,
        "dry_run_max_age_seconds": 7 * 24 * 60 * 60,
        "requires_note": False,
        "description": "Stable promotions require one recent successful dry run and one explicit approval.",
    },
    "production": {
        "channel": "production",
        "approval_required": True,
        "required_approvals": 1,
        "requires_successful_dry_run": True,
        "dry_run_max_age_seconds": 7 * 24 * 60 * 60,
        "requires_note": True,
        "description": "Production promotions require a recent successful dry run, approval, and a release note.",
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


def _state_db_path():
    return sqlite_state.db_path_for(WORKFLOWS_FILE)


def _load_list(namespace: str, legacy_path, default: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = sqlite_state.load_document(
        db_path=_state_db_path(),
        namespace=namespace,
        legacy_path=legacy_path,
        default=default,
    )
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return default


def _save_list(namespace: str, data: list[dict[str, Any]]) -> None:
    sqlite_state.save_document(
        db_path=_state_db_path(),
        namespace=namespace,
        data=data,
    )


def _load_workflows() -> list[dict[str, Any]]:
    return _load_list("workflows", WORKFLOWS_FILE, [])


def _save_workflows(items: list[dict[str, Any]]) -> None:
    _save_list("workflows", items)


def _load_runs() -> list[dict[str, Any]]:
    return workflow_run_store.list_runs(
        db_path=_state_db_path(),
        legacy_path=WORKFLOW_RUNS_FILE,
        limit=500,
    )


def _save_runs(items: list[dict[str, Any]]) -> None:
    for item in items[-500:]:
        workflow_run_store.save_run(
            db_path=_state_db_path(),
            legacy_path=WORKFLOW_RUNS_FILE,
            run=item,
            limit=500,
        )


def _load_approvals() -> list[dict[str, Any]]:
    return _load_list("workflow_approvals", WORKFLOW_APPROVALS_FILE, [])


def _save_approvals(items: list[dict[str, Any]]) -> None:
    _save_list("workflow_approvals", items[-500:])


def _load_versions() -> list[dict[str, Any]]:
    return _load_list("workflow_versions", WORKFLOW_VERSIONS_FILE, [])


def _save_versions(items: list[dict[str, Any]]) -> None:
    _save_list("workflow_versions", items[-1000:])


def _load_releases() -> list[dict[str, Any]]:
    return _load_list("workflow_releases", WORKFLOW_RELEASES_FILE, [])


def _save_releases(items: list[dict[str, Any]]) -> None:
    _save_list("workflow_releases", items[-1000:])


def _record_workflow_version(
    workflow: dict[str, Any],
    *,
    event: str,
    actor_id: str = "local-owner",
    note: str = "",
    previous: dict[str, Any] | None = None,
    changed_fields: list[str] | None = None,
) -> dict[str, Any]:
    record = {
        "id": uuid.uuid4().hex,
        "workflow_id": str(workflow.get("id") or ""),
        "workflow_name": _clean_text(workflow.get("name"), 120),
        "version": int(workflow.get("version", 1) or 1),
        "previous_version": int(previous.get("version", 0) or 0) if previous else None,
        "event": _clean_text(event, 40),
        "actor_id": _clean_text(actor_id or "local-owner", 120),
        "note": _clean_text(note, 500),
        "changed_fields": sorted({field for field in (changed_fields or []) if field}),
        "snapshot": copy.deepcopy(workflow),
        "created_at": _now(),
    }
    versions = _load_versions()
    versions.append(record)
    _save_versions(versions)
    return record


def _set_active_release_channel(workflow_id: str, channel: str) -> dict[str, Any] | None:
    items = _load_workflows()
    for item in items:
        if item.get("id") != workflow_id:
            continue
        item["active_release_channel"] = channel
        item["updated_at"] = _now()
        _save_workflows(items)
        return item
    return None


def list_templates() -> list[dict[str, Any]]:
    return [dict(template) for template in TEMPLATES]


def list_workflows(include_disabled: bool = True) -> list[dict[str, Any]]:
    items = _load_workflows()
    if not include_disabled:
        items = [item for item in items if item.get("enabled", True)]
    return sorted(items, key=lambda item: float(item.get("updated_at", 0)), reverse=True)


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    return next((item for item in _load_workflows() if item.get("id") == workflow_id), None)


def list_workflow_versions(workflow_id: str, limit: int = 50) -> list[dict[str, Any]]:
    versions = [item for item in _load_versions() if item.get("workflow_id") == workflow_id]
    return sorted(versions, key=lambda item: float(item.get("created_at", 0)), reverse=True)[: max(1, min(limit, 200))]


def get_workflow_version(workflow_id: str, version_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in _load_versions()
            if item.get("workflow_id") == workflow_id and item.get("id") == version_id
        ),
        None,
    )


def list_workflow_releases(
    workflow_id: str = "",
    channel: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    releases = _load_releases()
    if workflow_id:
        releases = [item for item in releases if item.get("workflow_id") == workflow_id]
    if channel:
        releases = [item for item in releases if item.get("channel") == channel]
    return sorted(releases, key=lambda item: float(item.get("created_at", 0)), reverse=True)[: max(1, min(limit, 200))]


def get_workflow_release(workflow_id: str, channel: str = "stable") -> dict[str, Any] | None:
    return next(iter(list_workflow_releases(workflow_id=workflow_id, channel=channel, limit=1)), None)


def _version_id_for_workflow_version(workflow_id: str, version_number: int) -> str:
    versions = [
        item
        for item in _load_versions()
        if item.get("workflow_id") == workflow_id and int(item.get("version", 0) or 0) == version_number
    ]
    if not versions:
        return ""
    latest = sorted(versions, key=lambda item: float(item.get("created_at", 0)), reverse=True)[0]
    return str(latest.get("id") or "")


def get_release_policies() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(RELEASE_POLICIES)


def get_release_gate_evidence(
    workflow_id: str,
    version_id: str,
    *,
    channel: str = "stable",
) -> dict[str, Any]:
    normalized_channel = _release_channel(channel)
    policy = RELEASE_POLICIES[normalized_channel]
    version = get_workflow_version(workflow_id, version_id)
    if version is None:
        return {
            "status": "missing_version",
            "ready": False,
            "dry_run": None,
            "dry_run_id": "",
            "max_age_seconds": int(policy.get("dry_run_max_age_seconds", 0) or 0),
        }

    version_number = int(version.get("version", 0) or 0)
    dry_runs = list_runs(
        workflow_id=workflow_id,
        workflow_version_id=version_id,
        dry_run=True,
        limit=10,
    )
    if not dry_runs:
        dry_runs = list_runs(
            workflow_id=workflow_id,
            workflow_version=version_number,
            dry_run=True,
            limit=10,
        )
        dry_runs = [run for run in dry_runs if not run.get("workflow_version_id")]
    latest = dry_runs[0] if dry_runs else None
    max_age_seconds = int(policy.get("dry_run_max_age_seconds", 0) or 0)
    if latest is None:
        return {
            "status": "missing_dry_run",
            "ready": False,
            "dry_run": None,
            "dry_run_id": "",
            "max_age_seconds": max_age_seconds,
        }
    age_seconds = max(0, _now() - float(latest.get("completed_at") or latest.get("started_at") or 0))
    if str(latest.get("status") or "") != "completed":
        return {
            "status": "failed_dry_run",
            "ready": False,
            "dry_run": latest,
            "dry_run_id": str(latest.get("id") or ""),
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
        }
    if max_age_seconds and age_seconds > max_age_seconds:
        return {
            "status": "stale_dry_run",
            "ready": False,
            "dry_run": latest,
            "dry_run_id": str(latest.get("id") or ""),
            "age_seconds": age_seconds,
            "max_age_seconds": max_age_seconds,
        }
    return {
        "status": "ready",
        "ready": True,
        "dry_run": latest,
        "dry_run_id": str(latest.get("id") or ""),
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
    }


def get_release_readiness(
    workflow_id: str,
    version_id: str,
    *,
    channel: str = "stable",
    note: str = "",
) -> dict[str, Any]:
    assessment = assess_release_request(workflow_id, version_id, channel=channel, note=note)
    evidence = dict(assessment.get("evidence") or {})
    dry_run = evidence.get("dry_run")
    if isinstance(dry_run, dict):
        evidence["dry_run"] = {
            "id": dry_run.get("id"),
            "status": dry_run.get("status"),
            "started_at": dry_run.get("started_at"),
            "completed_at": dry_run.get("completed_at"),
            "duration_ms": dry_run.get("duration_ms"),
        }
    return {
        "ready": bool(assessment.get("can_request")),
        "status": "ready" if assessment.get("can_request") else str(evidence.get("status") or "blocked"),
        "channel": assessment.get("channel"),
        "blockers": assessment.get("blockers", []),
        "evidence": evidence,
    }


def assess_release_request(
    workflow_id: str,
    version_id: str,
    *,
    channel: str = "stable",
    note: str = "",
) -> dict[str, Any]:
    normalized_channel = _release_channel(channel)
    policy = copy.deepcopy(RELEASE_POLICIES[normalized_channel])
    workflow = get_workflow(workflow_id)
    version = get_workflow_version(workflow_id, version_id)
    blockers: list[str] = []
    if workflow is None:
        blockers.append("Workflow not found.")
    if version is None:
        blockers.append("Workflow version not found.")
    if policy.get("requires_note") and not _clean_text(note, 500):
        blockers.append(f"{normalized_channel.title()} promotion requires a release note.")
    evidence = get_release_gate_evidence(workflow_id, version_id, channel=normalized_channel)
    if policy.get("requires_successful_dry_run") and not evidence.get("ready"):
        status = str(evidence.get("status") or "")
        if status == "missing_dry_run":
            blockers.append("A successful dry run is required for this workflow version before promotion.")
        elif status == "failed_dry_run":
            blockers.append("The latest dry run for this workflow version did not complete successfully.")
        elif status == "stale_dry_run":
            blockers.append("The successful dry run for this workflow version is stale.")
    return {
        "can_request": not blockers,
        "blockers": blockers,
        "channel": normalized_channel,
        "policy": policy,
        "evidence": evidence,
        "workflow": workflow,
        "version": version,
    }


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
    actor_id: str = "local-owner",
    note: str = "",
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
        "active_release_channel": "",
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
    }
    items = _load_workflows()
    items.append(item)
    _save_workflows(items)
    _record_workflow_version(item, event="created", actor_id=actor_id or str(item["owner_id"]), note=note)
    return item


def create_workflow_from_template(
    template_id: str,
    *,
    owner_id: str = "local-owner",
    actor_id: str = "local-owner",
) -> dict[str, Any] | None:
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
        actor_id=actor_id or owner_id,
        note=f"Created from template: {template_id}",
    )


def update_workflow(
    workflow_id: str,
    updates: dict[str, Any],
    *,
    actor_id: str = "local-owner",
    note: str = "",
) -> dict[str, Any] | None:
    items = _load_workflows()
    for item in items:
        if item.get("id") != workflow_id:
            continue
        previous = copy.deepcopy(item)
        changed_fields = [field for field in updates if field in {
            "name",
            "description",
            "trigger",
            "actions",
            "enabled",
            "tags",
            "visibility",
            "permissions",
            "active_release_channel",
        }]
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
        if "active_release_channel" in updates:
            channel = str(updates["active_release_channel"] or "").strip().lower()
            item["active_release_channel"] = channel if channel in RELEASE_CHANNELS else ""
        item["version"] = int(item.get("version", 1)) + 1
        item["updated_at"] = _now()
        _save_workflows(items)
        _record_workflow_version(
            item,
            event="updated",
            actor_id=actor_id,
            note=note,
            previous=previous,
            changed_fields=changed_fields,
        )
        return item
    return None


def restore_workflow_version(
    workflow_id: str,
    version_id: str,
    *,
    actor_id: str = "local-owner",
    note: str = "",
) -> dict[str, Any] | None:
    version = get_workflow_version(workflow_id, version_id)
    snapshot = copy.deepcopy(version.get("snapshot")) if version else None
    if not isinstance(snapshot, dict):
        return None
    version_number = version.get("version") if version else 0

    items = _load_workflows()
    now = _now()
    existing_index = next((index for index, item in enumerate(items) if item.get("id") == workflow_id), -1)
    previous = copy.deepcopy(items[existing_index]) if existing_index >= 0 else None

    restored = copy.deepcopy(snapshot)
    restored["id"] = workflow_id
    restored["version"] = int((previous or snapshot).get("version", 1) or 1) + 1
    restored["created_at"] = (previous or snapshot).get("created_at", now)
    restored["updated_at"] = now
    restored["last_run_at"] = (previous or snapshot).get("last_run_at")

    if existing_index >= 0:
        items[existing_index] = restored
    else:
        items.append(restored)
    _save_workflows(items)
    _record_workflow_version(
        restored,
        event="restored",
        actor_id=actor_id,
        note=note or f"Restored from version {version_number}",
        previous=previous,
        changed_fields=["restore"],
    )
    return restored


def publish_workflow_version(
    workflow_id: str,
    version_id: str = "",
    *,
    channel: str = "stable",
    actor_id: str = "local-owner",
    note: str = "",
    activate: bool = True,
) -> dict[str, Any] | None:
    channel = _release_channel(channel)

    current = get_workflow(workflow_id)
    version = get_workflow_version(workflow_id, version_id) if version_id else None
    if version_id and version is None:
        return None
    snapshot = copy.deepcopy(version.get("snapshot")) if version else copy.deepcopy(current)
    if not isinstance(snapshot, dict):
        return None

    release = {
        "id": uuid.uuid4().hex,
        "workflow_id": workflow_id,
        "workflow_name": _clean_text(snapshot.get("name"), 120),
        "channel": channel,
        "version_id": str(version.get("id") if version else ""),
        "version": int(snapshot.get("version", 1) or 1),
        "actor_id": _clean_text(actor_id or "local-owner", 120),
        "note": _clean_text(note, 500),
        "snapshot": snapshot,
        "created_at": _now(),
    }
    releases = _load_releases()
    releases.append(release)
    _save_releases(releases)
    if activate and current is not None:
        _set_active_release_channel(workflow_id, channel)
    return release


def _find_pending_release_approval(workflow_id: str, version_id: str, channel: str) -> dict[str, Any] | None:
    for approval in _load_approvals():
        action = dict(approval.get("action") or {})
        if (
            approval.get("status") == "pending"
            and action.get("type") == "publish_workflow_version"
            and action.get("workflow_id") == workflow_id
            and action.get("version_id") == version_id
            and action.get("channel") == channel
        ):
            return approval
    return None


def request_workflow_release_approval(
    workflow_id: str,
    version_id: str,
    *,
    channel: str = "stable",
    actor_id: str = "local-owner",
    note: str = "",
    activate: bool = True,
    require_approval: bool | None = None,
) -> dict[str, Any] | None:
    assessment = assess_release_request(workflow_id, version_id, channel=channel, note=note)
    if not assessment["can_request"]:
        return None

    normalized_channel = str(assessment["channel"])
    policy = dict(assessment["policy"])
    workflow = dict(assessment["workflow"] or {})
    version = dict(assessment["version"] or {})
    evidence = dict(assessment.get("evidence") or {})
    needs_approval = bool(policy.get("approval_required", True)) if require_approval is None else bool(require_approval)
    if not needs_approval:
        release = publish_workflow_version(
            workflow_id,
            version_id,
            channel=normalized_channel,
            actor_id=actor_id,
            note=note,
            activate=activate,
        )
        if release is None:
            return None
        return {
            "status": "published",
            "requires_approval": False,
            "release": release,
            "policy": policy,
            "evidence": evidence,
        }

    pending = _find_pending_release_approval(workflow_id, version_id, normalized_channel)
    if pending is not None:
        return {
            "status": "pending_approval",
            "requires_approval": True,
            "approval": pending,
            "policy": policy,
            "evidence": evidence,
        }

    action = {
        "id": uuid.uuid4().hex,
        "type": "publish_workflow_version",
        "title": f"Promote v{version.get('version', '?')} to {normalized_channel}",
        "workflow_id": workflow_id,
        "version_id": version_id,
        "version": int(version.get("version", 1) or 1),
        "channel": normalized_channel,
        "activate": activate,
        "requested_by": _clean_text(actor_id or "local-owner", 120),
        "note": _clean_text(note, 500),
        "dry_run_id": str(evidence.get("dry_run_id") or ""),
        "policy": policy,
        "requires_approval": True,
    }
    message = (
        f"Release policy requires approval before {workflow.get('name', 'this workflow')} "
        f"v{action['version']} can be promoted to {normalized_channel}."
    )
    approval = _record_approval(
        workflow=workflow,
        run_id="",
        action=action,
        message=message,
        triggered_by="release_policy",
    )
    return {
        "status": "pending_approval",
        "requires_approval": True,
        "approval": approval,
        "policy": policy,
        "evidence": evidence,
    }


def delete_workflow(workflow_id: str, *, actor_id: str = "local-owner", note: str = "") -> bool:
    items = _load_workflows()
    removed = next((item for item in items if item.get("id") == workflow_id), None)
    kept = [item for item in items if item.get("id") != workflow_id]
    if len(kept) == len(items):
        return False
    _save_workflows(kept)
    if removed is not None:
        _record_workflow_version(removed, event="deleted", actor_id=actor_id, note=note)
    return True


def list_runs(
    workflow_id: str = "",
    limit: int = 50,
    *,
    status: str = "",
    dry_run: bool | None = None,
    release_channel: str = "",
    workflow_version_id: str = "",
    workflow_version: int | None = None,
    started_after: float | None = None,
    started_before: float | None = None,
) -> list[dict[str, Any]]:
    return workflow_run_store.list_runs(
        db_path=_state_db_path(),
        legacy_path=WORKFLOW_RUNS_FILE,
        workflow_id=workflow_id,
        status=status,
        dry_run=dry_run,
        release_channel=release_channel,
        workflow_version_id=workflow_version_id,
        workflow_version=workflow_version,
        started_after=started_after,
        started_before=started_before,
        limit=limit,
    )


def get_run(run_id: str) -> dict[str, Any] | None:
    return workflow_run_store.get_run(
        db_path=_state_db_path(),
        legacy_path=WORKFLOW_RUNS_FILE,
        run_id=run_id,
    )


def get_run_storage_status() -> dict[str, int | bool]:
    return workflow_run_store.storage_status(
        db_path=_state_db_path(),
        legacy_path=WORKFLOW_RUNS_FILE,
    )


def _run_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 1)


def _run_error_summary(run: dict[str, Any]) -> str:
    if run.get("error"):
        return _clean_text(run.get("error"), 500)
    timeline_raw = run.get("timeline")
    timeline = timeline_raw if isinstance(timeline_raw, list) else []
    for entry in timeline:
        if not isinstance(entry, dict) or str(entry.get("status") or "") != "failed":
            continue
        output_raw = entry.get("output")
        output = output_raw if isinstance(output_raw, dict) else {}
        return _clean_text(output.get("error") or output.get("message") or entry.get("title"), 500)
    return ""


def get_run_analytics(
    workflow_id: str = "",
    *,
    started_after: float | None = None,
    started_before: float | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    runs = list_runs(
        workflow_id=workflow_id,
        started_after=started_after,
        started_before=started_before,
        limit=limit,
    )
    total = len(runs)
    status_counts: dict[str, int] = {}
    workflow_stats: dict[str, dict[str, Any]] = {}
    action_stats: dict[str, dict[str, Any]] = {}
    durations: list[float] = []
    recent_errors: list[dict[str, Any]] = []
    dry_runs = 0
    live_runs = 0

    for run in runs:
        status = str(run.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if run.get("dry_run") is True:
            dry_runs += 1
        else:
            live_runs += 1

        duration = _run_float(run.get("duration_ms"))
        if duration > 0:
            durations.append(duration)

        workflow_name = str(run.get("workflow_name") or "Workflow")
        workflow_key = str(run.get("workflow_id") or workflow_name)
        workflow_item = workflow_stats.setdefault(
            workflow_key,
            {
                "workflow_id": workflow_key,
                "workflow_name": workflow_name,
                "total_runs": 0,
                "failed_runs": 0,
                "completed_runs": 0,
                "last_run_at": 0.0,
            },
        )
        workflow_item["total_runs"] += 1
        workflow_item["last_run_at"] = max(_run_float(workflow_item.get("last_run_at")), _run_float(run.get("started_at")))
        if status == "completed":
            workflow_item["completed_runs"] += 1
        if status in {"failed", "completed_with_errors"}:
            workflow_item["failed_runs"] += 1

        error_summary = _run_error_summary(run)
        if status in {"failed", "completed_with_errors"} or error_summary:
            recent_errors.append({
                "run_id": run.get("id", ""),
                "workflow_id": run.get("workflow_id", ""),
                "workflow_name": workflow_name,
                "status": status,
                "error": error_summary or status.replace("_", " "),
                "started_at": _run_float(run.get("started_at")),
            })

        timeline_raw = run.get("timeline")
        timeline = timeline_raw if isinstance(timeline_raw, list) else []
        for entry in timeline:
            if not isinstance(entry, dict):
                continue
            action_type = str(entry.get("type") or "action")
            title = str(entry.get("title") or action_type.replace("_", " "))
            action_key = f"{action_type}:{title}"
            action_item = action_stats.setdefault(
                action_key,
                {
                    "type": action_type,
                    "title": title,
                    "total": 0,
                    "failed": 0,
                    "skipped": 0,
                    "approval_required": 0,
                    "duration_total_ms": 0.0,
                    "avg_duration_ms": 0.0,
                },
            )
            action_item["total"] += 1
            entry_status = str(entry.get("status") or "")
            if entry_status == "failed":
                action_item["failed"] += 1
            elif entry_status == "skipped":
                action_item["skipped"] += 1
            elif entry_status == "approval_required":
                action_item["approval_required"] += 1
            action_item["duration_total_ms"] += _run_float(entry.get("duration_ms"))

    for item in action_stats.values():
        total_actions = int(item.get("total", 0) or 0)
        if total_actions:
            item["avg_duration_ms"] = round(_run_float(item.get("duration_total_ms")) / total_actions, 1)
        item.pop("duration_total_ms", None)

    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0) + status_counts.get("completed_with_errors", 0)
    return {
        "total_runs": total,
        "dry_runs": dry_runs,
        "live_runs": live_runs,
        "status_counts": status_counts,
        "success_rate": round(completed / total, 3) if total else 0.0,
        "failure_rate": round(failed / total, 3) if total else 0.0,
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else 0.0,
        "p95_duration_ms": _percentile(durations, 0.95),
        "recent_errors": recent_errors[:8],
        "workflow_stats": sorted(
            workflow_stats.values(),
            key=lambda item: (_run_float(item.get("last_run_at")), int(item.get("total_runs", 0) or 0)),
            reverse=True,
        )[:10],
        "action_stats": sorted(
            action_stats.values(),
            key=lambda item: (int(item.get("failed", 0) or 0), _run_float(item.get("avg_duration_ms"))),
            reverse=True,
        )[:12],
    }


async def replay_run(
    run_id: str,
    *,
    runner: WorkflowRunner | None = None,
    dry_run: bool = True,
    triggered_by: str = "",
) -> dict[str, Any] | None:
    source_run = get_run(run_id)
    if source_run is None:
        return None

    workflow_id = str(source_run.get("workflow_id") or "")
    version_id = str(source_run.get("workflow_version_id") or "")
    if not version_id:
        version_number = int(source_run.get("workflow_version", 0) or 0)
        if workflow_id and version_number:
            version_id = _version_id_for_workflow_version(workflow_id, version_number)

    replay_trigger = triggered_by or ("replay_dry_run" if dry_run else "replay_live")
    warnings: list[str] = []
    strategy = "current_workflow"
    replay: dict[str, Any] | None = None

    if workflow_id and version_id and get_workflow_version(workflow_id, version_id) is not None:
        strategy = "version_snapshot"
        replay = await run_workflow_version(
            workflow_id,
            version_id,
            runner=runner,
            triggered_by=replay_trigger,
            dry_run=dry_run,
        )
    else:
        if version_id:
            warnings.append("Original workflow version snapshot is unavailable; replay used the current workflow.")
        release_channel = str(source_run.get("release_channel") or "")
        if release_channel:
            strategy = "release_channel"
            replay = await run_workflow(
                workflow_id,
                runner=runner,
                triggered_by=replay_trigger,
                dry_run=dry_run,
                release_channel=release_channel,
            )
            if replay is None:
                warnings.append("Original release channel is unavailable; replay used the current workflow draft.")
        if replay is None:
            replay = await run_workflow(
                workflow_id,
                runner=runner,
                triggered_by=replay_trigger,
                dry_run=dry_run,
                release_channel="",
            )
            strategy = "current_workflow"

    if replay is None:
        return {
            "source_run": source_run,
            "replay_run": None,
            "strategy": strategy,
            "warnings": warnings or ["Workflow is unavailable and cannot be replayed."],
        }

    replay["replayed_from_run_id"] = run_id
    replay["replay"] = {
        "source_run_id": run_id,
        "source_started_at": source_run.get("started_at"),
        "source_status": source_run.get("status"),
        "strategy": strategy,
        "dry_run": dry_run,
    }
    _record_run(replay)
    return {
        "source_run": source_run,
        "replay_run": replay,
        "strategy": strategy,
        "warnings": warnings,
    }


def list_approvals(status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
    approvals = _load_approvals()
    if status:
        approvals = [item for item in approvals if item.get("status") == status]
    return sorted(approvals, key=lambda item: float(item.get("created_at", 0)), reverse=True)[: max(1, min(limit, 200))]


def _record_run(run: dict[str, Any]) -> dict[str, Any]:
    return workflow_run_store.save_run(
        db_path=_state_db_path(),
        legacy_path=WORKFLOW_RUNS_FILE,
        run=run,
        limit=500,
    )


def _record_approval(
    *,
    workflow: dict[str, Any],
    run_id: str,
    action: dict[str, Any],
    message: str,
    triggered_by: str,
) -> dict[str, Any]:
    now = _now()
    approval = {
        "id": uuid.uuid4().hex,
        "workflow_id": workflow.get("id", ""),
        "workflow_name": workflow.get("name", ""),
        "run_id": run_id,
        "action_id": action.get("id", ""),
        "action_type": action.get("type", ""),
        "title": action.get("title", ""),
        "message": message,
        "action": dict(action),
        "status": "pending",
        "triggered_by": triggered_by,
        "created_at": now,
        "updated_at": now,
    }
    approvals = _load_approvals()
    approvals.append(approval)
    _save_approvals(approvals)
    return approval


def _update_approval(approval_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    approvals = _load_approvals()
    for item in approvals:
        if item.get("id") != approval_id:
            continue
        item.update(updates)
        item["updated_at"] = _now()
        _save_approvals(approvals)
        return item
    return None


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


async def _with_timeout(label: str, coro: Awaitable[Any], timeout: float = 18.0) -> Any:
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        return f"{label} timed out."
    except Exception as exc:
        return f"{label} failed: {exc}"


def _bounded_int(action: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(action.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _oauth_provider_from_action(action: dict[str, Any]) -> str:
    provider = str(action.get("provider") or "").strip().lower()
    return provider if provider in OAUTH_CALENDAR_PROVIDERS else ""


def _format_provider_events(provider: str, payload: dict[str, Any], *, days: int) -> str:
    events = payload.get("events", [])
    provider_name = "Google Calendar" if provider == "google" else "Outlook Calendar"
    if not isinstance(events, list) or not events:
        return f"{provider_name} has no events in the next {days} day{'s' if days != 1 else ''}."

    lines = [f"{provider_name} events for the next {days} day{'s' if days != 1 else ''}:"]
    for event in events[:20]:
        if not isinstance(event, dict):
            continue
        title = str(event.get("title") or "(Untitled)")
        start = str(event.get("start") or "unscheduled")
        location = str(event.get("location") or "")
        line = f"- {start}: {title}"
        if location:
            line = f"{line} @ {location}"
        lines.append(line)
    return "\n".join(lines)


async def _execute_calendar_brief(action: dict[str, Any]) -> str:
    from jarvis.tools.calendar_email import get_upcoming_events

    days = _bounded_int(action, "days", 1, 1, 14)
    provider = _oauth_provider_from_action(action)
    if provider:
        from jarvis.core import calendar_oauth

        limit = _bounded_int(action, "count", 20, 1, 50)
        provider_result = await _with_timeout(
            f"{provider} calendar brief",
            calendar_oauth.list_events(
                provider,
                days=days,
                limit=limit,
                calendar_id=str(action.get("calendar_id") or ""),
            ),
            timeout=22.0,
        )
        if isinstance(provider_result, dict):
            return _format_provider_events(provider, provider_result, days=days)

        fallback = await _with_timeout("Local calendar brief", get_upcoming_events(days=days), timeout=22.0)
        return f"{provider.title()} calendar unavailable: {provider_result}\n\n{fallback}"

    local_result = await _with_timeout("Calendar brief", get_upcoming_events(days=days), timeout=22.0)
    return str(local_result)


async def _execute_email_digest(action: dict[str, Any]) -> str:
    from jarvis.tools.calendar_email import get_recent_emails, get_unread_count

    count = _bounded_int(action, "count", 5, 1, 25)
    mailbox = str(action.get("mailbox") or "INBOX")
    unread = await _with_timeout("Unread email check", get_unread_count(), timeout=12.0)
    recent = await _with_timeout("Recent email digest", get_recent_emails(count=count, mailbox=mailbox), timeout=22.0)
    return f"{unread}\n\n{recent}"


async def _execute_notification(action: dict[str, Any], workflow_name: str) -> str:
    from jarvis.tools.mac_control import send_notification

    title = str(action.get("title") or workflow_name or "JARVIS Workflow")
    message = str(action.get("message") or action.get("prompt") or "Workflow step completed.")
    result = await _with_timeout("Notification", send_notification(title, message), timeout=8.0)
    return str(result)


async def _execute_calendar_event(action: dict[str, Any], *, approved: bool = False) -> str:
    from jarvis.tools.calendar_email import create_calendar_event

    title = str(action.get("title") or action.get("message") or "JARVIS Event")
    start_date = str(action.get("start") or action.get("start_date") or "")
    if not start_date:
        return "Calendar event skipped: start_date is required."
    provider = _oauth_provider_from_action(action)
    if provider:
        from jarvis.core import calendar_accounts, calendar_oauth

        end_date = str(action.get("end") or action.get("end_date") or "")
        if not end_date:
            return "Calendar event skipped: end/end_date is required for provider-backed calendars."
        attendees = [str(value) for value in action.get("attendees", []) if str(value).strip()]
        assessment = calendar_accounts.assess_scheduling_request(
            title=title,
            start=start_date,
            end=end_date,
            attendees=attendees,
            provider=provider,
        )
        if not assessment.get("can_auto_schedule"):
            blockers_list = [str(item) for item in assessment.get("blockers", [])]
            if not approved or "No connected calendar provider is enabled." in blockers_list:
                blockers = ", ".join(blockers_list)
                return f"Calendar event skipped: {blockers or 'Scheduling policy requires confirmation.'}"

        created = await _with_timeout(
            "Provider calendar event creation",
            calendar_oauth.create_event(
                provider,
                title=title,
                start=start_date,
                end=end_date,
                timezone=str(action.get("timezone") or assessment.get("policy", {}).get("timezone") or "UTC"),
                location=str(action.get("location") or ""),
                notes=str(action.get("notes") or ""),
                attendees=attendees,
                calendar_id=str(action.get("calendar_id") or ""),
            ),
            timeout=22.0,
        )
        if isinstance(created, dict):
            event = created.get("event", {})
            event_title = event.get("title") if isinstance(event, dict) else title
            return f"Created {provider.title()} calendar event: {event_title or title}"
        return str(created)

    result = await _with_timeout(
        "Calendar event creation",
        create_calendar_event(
            title=title,
            start_date=start_date,
            end_date=str(action.get("end") or action.get("end_date") or ""),
            location=str(action.get("location") or ""),
            notes=str(action.get("notes") or ""),
            calendar_name=str(action.get("calendar_name") or ""),
            all_day=bool(action.get("all_day", False)),
        ),
        timeout=22.0,
    )
    return str(result)


async def approve_approval(approval_id: str, *, actor: str = "local-owner", note: str = "") -> dict[str, Any] | None:
    approvals = _load_approvals()
    approval = next((item for item in approvals if item.get("id") == approval_id), None)
    if approval is None:
        return None
    if approval.get("status") != "pending":
        return approval

    action = dict(approval.get("action") or {})
    response = "Approval granted."
    execution_status = "approved"
    release_id = ""
    try:
        if action.get("type") == "create_calendar_event":
            action["requires_approval"] = False
            response = await _execute_calendar_event(action, approved=True)
            execution_status = "completed"
        elif action.get("type") == "publish_workflow_version":
            assessment = assess_release_request(
                str(action.get("workflow_id") or ""),
                str(action.get("version_id") or ""),
                channel=str(action.get("channel") or "stable"),
                note=note or str(action.get("note") or ""),
            )
            if not assessment.get("can_request"):
                response = "Release promotion failed: " + "; ".join(str(item) for item in assessment.get("blockers", []))
                execution_status = "failed"
                release = None
            else:
                release = publish_workflow_version(
                    str(action.get("workflow_id") or ""),
                    str(action.get("version_id") or ""),
                    channel=str(action.get("channel") or "stable"),
                    actor_id=actor,
                    note=note or str(action.get("note") or ""),
                    activate=bool(action.get("activate", True)),
                )
            if release is None:
                if execution_status != "failed":
                    response = "Release promotion failed: workflow version not found."
                    execution_status = "failed"
            else:
                release_id = str(release.get("id") or "")
                response = (
                    f"Published {release.get('workflow_name', 'workflow')} "
                    f"v{release.get('version', '?')} to {release.get('channel', 'stable')}."
                )
                execution_status = "completed"
    except Exception as exc:
        response = str(exc)
        execution_status = "failed"

    return _update_approval(
        approval_id,
        {
            "status": "approved",
            "actor": _clean_text(actor, 120),
            "note": _clean_text(note, 500),
            "response": response,
            "execution_status": execution_status,
            "release_id": release_id,
            "completed_at": _now(),
        },
    )


def reject_approval(approval_id: str, *, actor: str = "local-owner", note: str = "") -> dict[str, Any] | None:
    approval = next((item for item in _load_approvals() if item.get("id") == approval_id), None)
    if approval is None:
        return None
    if approval.get("status") != "pending":
        return approval
    return _update_approval(
        approval_id,
        {
            "status": "rejected",
            "actor": _clean_text(actor, 120),
            "note": _clean_text(note, 500),
            "completed_at": _now(),
        },
    )


def _base_action_result(action: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    return {
        "action_id": action.get("id"),
        "type": str(action.get("type", "prompt")),
        "title": action.get("title", ""),
        "status": "prepared" if dry_run else "completed",
    }


def _result_text(result: dict[str, Any]) -> str:
    parts = [
        str(result.get("response") or ""),
        str(result.get("message") or ""),
        str(result.get("error") or ""),
    ]
    return " ".join(part for part in parts if part).lower()


def _context_result(condition: dict[str, Any], action_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    action_id = str(condition.get("action_id") or "").strip()
    if action_id:
        return next((item for item in action_results if item.get("action_id") == action_id), None)
    return action_results[-1] if action_results else None


def _condition_matches(action: dict[str, Any], action_results: list[dict[str, Any]]) -> bool:
    condition = dict(action.get("condition") or {})
    mode = str(condition.get("type") or "always").strip().lower()
    if mode == "always":
        return True
    previous = _context_result(condition, action_results)
    if previous is None:
        return False
    value = str(condition.get("value") or "").strip().lower()
    if mode == "previous_status":
        return str(previous.get("status") or "").lower() == (value or "completed")
    if mode == "previous_response_contains":
        return bool(value) and value in _result_text(previous)
    if mode == "previous_response_not_contains":
        return not value or value not in _result_text(previous)
    return True


def _condition_message(action: dict[str, Any]) -> str:
    condition = dict(action.get("condition") or {})
    mode = str(condition.get("type") or "always").replace("_", " ")
    value = str(condition.get("value") or "").strip()
    return f"Condition not met: {mode}{f' = {value}' if value else ''}."


def _retry_attempts(action: dict[str, Any]) -> int:
    try:
        retry_count = int(action.get("retry_count", 0) or 0)
    except (TypeError, ValueError):
        retry_count = 0
    return 1 + max(0, min(retry_count, 3))


def _retry_delay_seconds(action: dict[str, Any]) -> float:
    try:
        retry_delay_ms = int(action.get("retry_delay_ms", 0) or 0)
    except (TypeError, ValueError):
        retry_delay_ms = 0
    return max(0, min(retry_delay_ms, 30000)) / 1000


def _audit_value(value: Any, limit: int = 2000) -> Any:
    if isinstance(value, str):
        return _clean_text(value, limit)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_audit_value(item, 500) for item in value[:25]]
    if isinstance(value, dict):
        return {
            str(key): _audit_value(item, 500)
            for key, item in value.items()
            if str(key) not in {"client_secret", "access_token", "refresh_token"}
        }
    return _clean_text(value, limit)


def _audit_action_input(action: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "id",
        "type",
        "title",
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
        "attendees",
        "days",
        "count",
        "condition",
        "retry_count",
        "retry_delay_ms",
        "on_error",
        "requires_approval",
        "all_day",
    }
    return {key: _audit_value(value) for key, value in action.items() if key in allowed}


def _audit_action_output(result: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "status",
        "message",
        "response",
        "error",
        "approval_id",
        "attempts",
        "prompt",
        "routine_id",
    }
    return {key: _audit_value(value, 4000) for key, value in result.items() if key in allowed}


def _timeline_entry(
    *,
    action: dict[str, Any],
    status: str,
    started_at: float,
    completed_at: float,
    result: dict[str, Any],
    attempt_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "action_id": action.get("id"),
        "type": str(action.get("type", "prompt")),
        "title": action.get("title", ""),
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": round((completed_at - started_at) * 1000, 1),
        "input": _audit_action_input(action),
        "output": _audit_action_output(result),
        "attempts": attempt_trace or [],
    }


async def _run_action_once(
    *,
    action: dict[str, Any],
    workflow: dict[str, Any],
    run_id: str,
    runner: WorkflowRunner | None,
    triggered_by: str,
    dry_run: bool,
) -> dict[str, Any]:
    action_type = str(action.get("type", "prompt"))
    result = _base_action_result(action, dry_run=dry_run)

    if action.get("requires_approval"):
        message = "Workflow paused for explicit approval." if action_type == "wait_for_approval" else "This action requires user approval."
        result.update({"status": "approval_required", "message": message})
        if not dry_run:
            approval = _record_approval(
                workflow=workflow,
                run_id=run_id,
                action=action,
                message=message,
                triggered_by=triggered_by,
            )
            result["approval_id"] = approval["id"]
    elif action_type == "prompt":
        prompt = str(action.get("prompt") or action.get("message") or workflow.get("description") or workflow["name"])
        result["prompt"] = prompt
        if runner is not None and not dry_run:
            result["response"] = await runner(prompt)
        elif not dry_run:
            result["status"] = "skipped"
            result["message"] = "No prompt runner was provided."
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
            elif not dry_run:
                result["status"] = "skipped"
                result["message"] = "No prompt runner was provided."
    elif action_type == "calendar_brief":
        if dry_run:
            result["message"] = "Calendar brief prepared."
        else:
            result["response"] = await _execute_calendar_brief(action)
    elif action_type == "email_digest":
        if dry_run:
            result["message"] = "Email digest prepared."
        else:
            result["response"] = await _execute_email_digest(action)
    elif action_type == "notification":
        if dry_run:
            result["message"] = str(action.get("message") or "Workflow notification prepared.")
        else:
            result["response"] = await _execute_notification(action, str(workflow.get("name", "")))
    elif action_type == "create_calendar_event":
        if dry_run:
            result.update({"status": "approval_required", "message": "Calendar writes require explicit approval."})
        elif action.get("requires_approval") is False:
            result["response"] = await _execute_calendar_event(action)
        else:
            result.update({"status": "approval_required", "message": "Calendar writes require explicit approval."})
    elif action_type == "wait_for_approval":
        message = "Workflow paused for explicit approval."
        result.update({"status": "approval_required", "message": message})
        if not dry_run:
            approval = _record_approval(
                workflow=workflow,
                run_id=run_id,
                action=action,
                message=message,
                triggered_by=triggered_by,
            )
            result["approval_id"] = approval["id"]
    return result


async def _execute_workflow_snapshot(
    workflow_id: str,
    workflow: dict[str, Any],
    *,
    runner: WorkflowRunner | None = None,
    triggered_by: str = "manual",
    dry_run: bool = False,
    run_time: float | None = None,
    release_channel: str = "",
    release_id: str = "",
    workflow_version_id: str = "",
) -> dict[str, Any] | None:
    started_at = run_time or _now()
    run_id = uuid.uuid4().hex
    action_results: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    status = "completed"
    error = ""

    try:
        for action in workflow.get("actions", []):
            action_started_at = _now()
            if not _condition_matches(action, action_results):
                skipped_result = _base_action_result(action, dry_run=dry_run)
                skipped_result.update({"status": "skipped", "message": _condition_message(action)})
                action_results.append(skipped_result)
                action_completed_at = _now()
                timeline.append(_timeline_entry(
                    action=action,
                    status="skipped",
                    started_at=action_started_at,
                    completed_at=action_completed_at,
                    result=skipped_result,
                ))
                continue

            attempts = _retry_attempts(action)
            retry_delay = _retry_delay_seconds(action)
            action_result: dict[str, Any] | None = None
            attempt_trace: list[dict[str, Any]] = []
            stop_after_action = False
            for attempt in range(1, attempts + 1):
                attempt_started_at = _now()
                try:
                    action_result = await _run_action_once(
                        action=action,
                        workflow=workflow,
                        run_id=run_id,
                        runner=runner,
                        triggered_by=triggered_by,
                        dry_run=dry_run,
                    )
                    if attempts > 1:
                        action_result["attempts"] = attempt
                    attempt_completed_at = _now()
                    attempt_trace.append({
                        "attempt": attempt,
                        "status": str(action_result.get("status") or "completed"),
                        "started_at": attempt_started_at,
                        "completed_at": attempt_completed_at,
                        "duration_ms": round((attempt_completed_at - attempt_started_at) * 1000, 1),
                    })
                    break
                except Exception as exc:
                    attempt_completed_at = _now()
                    attempt_trace.append({
                        "attempt": attempt,
                        "status": "failed",
                        "error": _clean_text(exc, 1000),
                        "started_at": attempt_started_at,
                        "completed_at": attempt_completed_at,
                        "duration_ms": round((attempt_completed_at - attempt_started_at) * 1000, 1),
                    })
                    if attempt < attempts:
                        if retry_delay:
                            await asyncio.sleep(retry_delay)
                        continue
                    action_result = _base_action_result(action, dry_run=dry_run)
                    action_result.update({
                        "status": "failed",
                        "error": str(exc),
                        "attempts": attempt,
                    })
                    if str(action.get("on_error") or "stop").lower() == "continue":
                        status = "completed_with_errors" if status == "completed" else status
                        action_result["message"] = "Step failed; continuing workflow."
                    else:
                        status = "failed"
                        error = str(exc)
                        stop_after_action = True
            if action_result is not None:
                action_result["attempt_trace"] = attempt_trace
                action_results.append(action_result)
                action_completed_at = _now()
                timeline.append(_timeline_entry(
                    action=action,
                    status=str(action_result.get("status") or "completed"),
                    started_at=action_started_at,
                    completed_at=action_completed_at,
                    result=action_result,
                    attempt_trace=attempt_trace,
                ))
            if stop_after_action:
                break
    except Exception as exc:
        status = "failed"
        error = str(exc)

    completed_at = _now()
    run = {
        "id": run_id,
        "workflow_id": workflow_id,
        "workflow_name": workflow.get("name", ""),
        "workflow_version": int(workflow.get("version", 1) or 1),
        "workflow_version_id": workflow_version_id,
        "release_channel": release_channel,
        "release_id": release_id,
        "status": status,
        "triggered_by": triggered_by,
        "dry_run": dry_run,
        "action_results": action_results,
        "timeline": timeline,
        "error": error,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": round((completed_at - started_at) * 1000, 1),
    }
    _record_run(run)
    _mark_workflow_run(workflow_id, timestamp=started_at)
    return run


async def run_workflow(
    workflow_id: str,
    *,
    runner: WorkflowRunner | None = None,
    triggered_by: str = "manual",
    dry_run: bool = False,
    run_time: float | None = None,
    release_channel: str | None = None,
) -> dict[str, Any] | None:
    current_workflow = get_workflow(workflow_id)
    if current_workflow is None:
        return None
    workflow = copy.deepcopy(current_workflow)
    resolved_release: dict[str, Any] | None = None
    channel = str(current_workflow.get("active_release_channel") or "") if release_channel is None else str(release_channel or "")
    version_id = _version_id_for_workflow_version(workflow_id, int(workflow.get("version", 1) or 1))
    if channel:
        resolved_release = get_workflow_release(workflow_id, channel)
        if resolved_release is None:
            return None
        snapshot = copy.deepcopy(resolved_release.get("snapshot"))
        if not isinstance(snapshot, dict):
            return None
        workflow = snapshot
        workflow["id"] = workflow_id
        version_id = str(resolved_release.get("version_id") or "") or _version_id_for_workflow_version(
            workflow_id,
            int(workflow.get("version", 1) or 1),
        )

    return await _execute_workflow_snapshot(
        workflow_id,
        workflow,
        runner=runner,
        triggered_by=triggered_by,
        dry_run=dry_run,
        run_time=run_time,
        release_channel=channel,
        release_id=str(resolved_release.get("id") if resolved_release else ""),
        workflow_version_id=version_id,
    )


async def run_workflow_version(
    workflow_id: str,
    version_id: str,
    *,
    runner: WorkflowRunner | None = None,
    triggered_by: str = "version_dry_run",
    dry_run: bool = True,
    run_time: float | None = None,
) -> dict[str, Any] | None:
    version = get_workflow_version(workflow_id, version_id)
    snapshot = copy.deepcopy(version.get("snapshot")) if version else None
    if not isinstance(snapshot, dict):
        return None
    snapshot["id"] = workflow_id
    return await _execute_workflow_snapshot(
        workflow_id,
        snapshot,
        runner=runner,
        triggered_by=triggered_by,
        dry_run=dry_run,
        run_time=run_time,
        workflow_version_id=version_id,
    )


def get_overview() -> dict[str, Any]:
    workflows = list_workflows()
    runs = list_runs(limit=10)
    return {
        "workflow_count": len(workflows),
        "enabled_count": sum(1 for item in workflows if item.get("enabled", True)),
        "template_count": len(TEMPLATES),
        "pending_approval_count": len(list_approvals(status="pending", limit=200)),
        "recent_runs": runs,
        "next_foundation_steps": [
            "Add workflow test suites with explicit assertions before release promotion.",
            "Attribute LLM cost to workflow runs and actions for budget-aware automation tuning.",
            "Add team presence and conflict handling for simultaneous workflow edits.",
        ],
    }
