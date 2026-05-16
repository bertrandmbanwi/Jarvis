"""Calendar connection metadata and scheduling policy scaffolding."""
from __future__ import annotations

import json
import time
from contextlib import suppress
from typing import Any

from jarvis.config import settings
from jarvis.core import profile

CALENDAR_STATE_FILE = settings.DATA_DIR / "calendar_state.json"

PROVIDER_TEMPLATES: dict[str, dict[str, Any]] = {
    "google": {
        "name": "Google Calendar",
        "oauth_required": True,
        "scopes": ["calendar.events.readonly", "calendar.events"],
    },
    "outlook": {
        "name": "Outlook Calendar",
        "oauth_required": True,
        "scopes": ["Calendars.Read", "Calendars.ReadWrite"],
    },
    "apple": {
        "name": "Apple Calendar",
        "oauth_required": False,
        "scopes": ["local_calendar_read", "local_calendar_write"],
    },
}


def _now() -> float:
    return time.time()


def _default_policy() -> dict[str, Any]:
    user_timezone = str(profile.get_preference("timezone") or "").strip() or "America/Chicago"
    return {
        "timezone": user_timezone,
        "working_hours": {"start": "09:00", "end": "17:00"},
        "default_duration_minutes": 30,
        "conflict_strategy": "ask",
        "auto_create_events": False,
        "require_confirmation_for_guests": True,
        "buffer_minutes": 10,
    }


def _default_state() -> dict[str, Any]:
    now = _now()
    return {
        "connections": [],
        "policy": _default_policy(),
        "created_at": now,
        "updated_at": now,
    }


def _load() -> dict[str, Any]:
    if not CALENDAR_STATE_FILE.exists():
        state = _default_state()
        _save(state)
        return state
    try:
        data = json.loads(CALENDAR_STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _default_state()
    except (OSError, json.JSONDecodeError):
        return _default_state()


def _save(state: dict[str, Any]) -> None:
    CALENDAR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def list_provider_templates() -> dict[str, dict[str, Any]]:
    return {key: dict(value) for key, value in PROVIDER_TEMPLATES.items()}


def get_state() -> dict[str, Any]:
    state = _load()
    state["providers"] = list_provider_templates()
    return state


def list_connections() -> list[dict[str, Any]]:
    return list(_load().get("connections", []))


def upsert_connection(
    *,
    provider: str,
    account_label: str = "",
    enabled: bool = False,
    status: str = "not_connected",
    scopes: list[str] | None = None,
) -> dict[str, Any] | None:
    provider_key = provider.strip().lower()
    if provider_key not in PROVIDER_TEMPLATES:
        return None
    state = _load()
    connections = list(state.get("connections", []))
    now = _now()
    normalized_status = status if status in {"not_connected", "connected", "needs_auth", "error"} else "not_connected"
    requested_scopes = scopes or PROVIDER_TEMPLATES[provider_key]["scopes"]

    connection = {
        "provider": provider_key,
        "name": PROVIDER_TEMPLATES[provider_key]["name"],
        "account_label": _clean(account_label, 180),
        "enabled": bool(enabled),
        "status": normalized_status,
        "scopes": list(requested_scopes),
        "updated_at": now,
    }

    for index, item in enumerate(connections):
        if item.get("provider") == provider_key:
            connection["created_at"] = item.get("created_at", now)
            connections[index] = connection
            break
    else:
        connection["created_at"] = now
        connections.append(connection)

    state["connections"] = connections
    state["updated_at"] = now
    _save(state)
    return connection


def remove_connection(provider: str) -> bool:
    provider_key = provider.strip().lower()
    state = _load()
    connections = list(state.get("connections", []))
    kept = [item for item in connections if item.get("provider") != provider_key]
    if len(kept) == len(connections):
        return False
    state["connections"] = kept
    state["updated_at"] = _now()
    _save(state)
    return True


def update_policy(updates: dict[str, Any]) -> dict[str, Any]:
    state = _load()
    policy = {**_default_policy(), **dict(state.get("policy", {}))}
    if "timezone" in updates:
        policy["timezone"] = _clean(updates["timezone"], 80)
    if "working_hours" in updates and isinstance(updates["working_hours"], dict):
        working_hours = updates["working_hours"]
        policy["working_hours"] = {
            "start": _clean(working_hours.get("start", policy["working_hours"]["start"]), 20),
            "end": _clean(working_hours.get("end", policy["working_hours"]["end"]), 20),
    }
    if "default_duration_minutes" in updates:
        with suppress(TypeError, ValueError):
            policy["default_duration_minutes"] = max(5, min(int(updates["default_duration_minutes"]), 480))
    if "conflict_strategy" in updates:
        strategy = str(updates["conflict_strategy"])
        policy["conflict_strategy"] = strategy if strategy in {"ask", "skip", "next_available"} else "ask"
    for key in ("auto_create_events", "require_confirmation_for_guests"):
        if key in updates:
            policy[key] = bool(updates[key])
    if "buffer_minutes" in updates:
        with suppress(TypeError, ValueError):
            policy["buffer_minutes"] = max(0, min(int(updates["buffer_minutes"]), 120))
    state["policy"] = policy
    state["updated_at"] = _now()
    _save(state)
    return policy


def assess_scheduling_request(
    *,
    title: str,
    start: str = "",
    end: str = "",
    attendees: list[str] | None = None,
    provider: str = "",
) -> dict[str, Any]:
    state = _load()
    policy = {**_default_policy(), **dict(state.get("policy", {}))}
    attendees = attendees or []
    enabled_connections = [
        item for item in state.get("connections", [])
        if item.get("enabled") and item.get("status") == "connected"
    ]
    selected = provider.strip().lower()
    if selected:
        enabled_connections = [item for item in enabled_connections if item.get("provider") == selected]

    blockers: list[str] = []
    if not enabled_connections:
        blockers.append("No connected calendar provider is enabled.")
    if attendees and policy.get("require_confirmation_for_guests", True):
        blockers.append("Guest invitations require confirmation.")
    if not policy.get("auto_create_events", False):
        blockers.append("Auto-create is disabled by scheduling policy.")

    return {
        "title": _clean(title, 180),
        "start": _clean(start, 80),
        "end": _clean(end, 80),
        "attendees": attendees,
        "provider": selected or (enabled_connections[0]["provider"] if enabled_connections else ""),
        "policy": policy,
        "can_auto_schedule": not blockers,
        "requires_confirmation": bool(blockers),
        "blockers": blockers,
    }
