"""Calendar connection metadata and scheduling policy scaffolding."""
from __future__ import annotations

import secrets
import time
from contextlib import suppress
from typing import Any

from jarvis.config import settings
from jarvis.core import profile, sqlite_state

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


def _state_db_path():
    return sqlite_state.db_path_for(CALENDAR_STATE_FILE)


def _load() -> dict[str, Any]:
    default = _default_state()
    data = sqlite_state.load_document(
        db_path=_state_db_path(),
        namespace="calendar_state",
        legacy_path=CALENDAR_STATE_FILE,
        default=default,
    )
    return data if isinstance(data, dict) else default


def _save(state: dict[str, Any]) -> None:
    sqlite_state.save_document(
        db_path=_state_db_path(),
        namespace="calendar_state",
        data=state,
    )


def _clean(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def list_provider_templates() -> dict[str, dict[str, Any]]:
    return {key: dict(value) for key, value in PROVIDER_TEMPLATES.items()}


def get_state() -> dict[str, Any]:
    state = dict(_load())
    state.pop("oauth_states", None)
    sanitized_connections = []
    for item in state.get("connections", []):
        if not isinstance(item, dict):
            continue
        sanitized = dict(item)
        sanitized["client_id_configured"] = bool(sanitized.pop("client_id", ""))
        sanitized_connections.append(sanitized)
    state["connections"] = sanitized_connections
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
    connections: list[dict[str, Any]] = [
        dict(item) for item in state.get("connections", []) if isinstance(item, dict)
    ]
    now = _now()
    normalized_status = status if status in {"not_connected", "connected", "needs_auth", "error"} else "not_connected"
    requested_scopes = scopes or PROVIDER_TEMPLATES[provider_key]["scopes"]

    existing = next((item for item in connections if item.get("provider") == provider_key), {})
    connection = {
        "provider": provider_key,
        "name": PROVIDER_TEMPLATES[provider_key]["name"],
        "account_label": _clean(account_label, 180),
        "enabled": bool(enabled),
        "status": normalized_status,
        "scopes": list(requested_scopes),
        "updated_at": now,
    }
    for key in ("client_id", "token_expires_at", "last_error"):
        if key in existing:
            connection[key] = existing[key]

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


def update_connection(provider: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Patch connection metadata without exposing stored OAuth tokens."""
    provider_key = provider.strip().lower()
    if provider_key not in PROVIDER_TEMPLATES:
        return None
    state = _load()
    connections: list[dict[str, Any]] = [
        dict(item) for item in state.get("connections", []) if isinstance(item, dict)
    ]
    now = _now()
    for item in connections:
        if item.get("provider") != provider_key:
            continue
        item.update(updates)
        item["provider"] = provider_key
        item["name"] = PROVIDER_TEMPLATES[provider_key]["name"]
        item["updated_at"] = now
        state["connections"] = connections
        state["updated_at"] = now
        _save(state)
        return item

    connection = {
        "provider": provider_key,
        "name": PROVIDER_TEMPLATES[provider_key]["name"],
        "account_label": _clean(updates.get("account_label", ""), 180),
        "enabled": bool(updates.get("enabled", False)),
        "status": str(updates.get("status", "not_connected")),
        "scopes": list(updates.get("scopes") or PROVIDER_TEMPLATES[provider_key]["scopes"]),
        "created_at": now,
        "updated_at": now,
    }
    for key in ("client_id", "token_expires_at", "last_error"):
        if key in updates:
            connection[key] = updates[key]
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


def create_oauth_state(provider: str, redirect_uri: str) -> str | None:
    provider_key = provider.strip().lower()
    if provider_key not in PROVIDER_TEMPLATES:
        return None
    state = _load()
    now = _now()
    oauth_state = secrets.token_urlsafe(32)
    states = [
        item for item in state.get("oauth_states", [])
        if isinstance(item, dict) and float(item.get("expires_at", 0) or 0) > now
    ]
    states.append({
        "provider": provider_key,
        "state": oauth_state,
        "redirect_uri": _clean(redirect_uri, 500),
        "created_at": now,
        "expires_at": now + 600,
    })
    state["oauth_states"] = states[-20:]
    state["updated_at"] = now
    _save(state)
    return oauth_state


def consume_oauth_state(provider: str, state_value: str) -> dict[str, Any] | None:
    provider_key = provider.strip().lower()
    state = _load()
    now = _now()
    kept: list[dict[str, Any]] = []
    match: dict[str, Any] | None = None
    for item in state.get("oauth_states", []):
        if not isinstance(item, dict) or float(item.get("expires_at", 0) or 0) <= now:
            continue
        if item.get("provider") == provider_key and item.get("state") == state_value and match is None:
            match = item
            continue
        kept.append(item)
    state["oauth_states"] = kept
    state["updated_at"] = now
    _save(state)
    return match


def mark_oauth_connected(
    provider: str,
    *,
    account_label: str = "",
    scopes: list[str] | None = None,
    token_expires_at: float = 0.0,
) -> dict[str, Any] | None:
    provider_key = provider.strip().lower()
    connection = upsert_connection(
        provider=provider_key,
        account_label=account_label or provider_key,
        enabled=True,
        status="connected",
        scopes=scopes,
    )
    if connection is None:
        return None

    state = _load()
    connections = list(state.get("connections", []))
    for item in connections:
        if item.get("provider") == provider_key:
            item["token_expires_at"] = token_expires_at
            item["last_error"] = ""
            item["updated_at"] = _now()
            break
    state["connections"] = connections
    state["updated_at"] = _now()
    _save(state)
    return next((item for item in connections if item.get("provider") == provider_key), connection)


def mark_connection_error(provider: str, error: str) -> dict[str, Any] | None:
    provider_key = provider.strip().lower()
    connection = update_connection(provider_key, {"status": "error"})
    state = _load()
    connections = list(state.get("connections", []))
    for item in connections:
        if item.get("provider") == provider_key:
            item["last_error"] = _clean(error, 500)
            item["updated_at"] = _now()
            connection = item
            break
    state["connections"] = connections
    state["updated_at"] = _now()
    _save(state)
    return connection


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
