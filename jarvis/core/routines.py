"""Persistent user routines for repeatable JARVIS workflows."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from jarvis.config import settings

ROUTINES_FILE = settings.DATA_DIR / "routines.json"

DEFAULT_ROUTINES = [
    {
        "name": "Morning Brief",
        "prompt": "Give me a concise morning brief: local weather, calendar, unread email count, and any proactive suggestions.",
        "enabled": True,
        "tags": ["daily", "brief"],
    },
    {
        "name": "Evening Recap",
        "prompt": "Summarize today's Jarvis activity, open tasks, calendar tomorrow, and anything I should follow up on.",
        "enabled": True,
        "tags": ["daily", "recap"],
    },
    {
        "name": "Focus Setup",
        "prompt": "Prepare a focus session: summarize current system status, close distractions if I ask, and ask what project I am working on.",
        "enabled": True,
        "tags": ["work", "focus"],
    },
]


def _seed_routine(data: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    return {
        "id": uuid.uuid4().hex,
        "name": data["name"],
        "prompt": data["prompt"],
        "enabled": bool(data.get("enabled", True)),
        "tags": list(data.get("tags", [])),
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
    }


def _load() -> list[dict[str, Any]]:
    if not ROUTINES_FILE.exists():
        routines = [_seed_routine(item) for item in DEFAULT_ROUTINES]
        _save(routines)
        return routines
    try:
        data = json.loads(ROUTINES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save(items: list[dict[str, Any]]) -> None:
    ROUTINES_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROUTINES_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def list_routines() -> list[dict[str, Any]]:
    return _load()


def get_routine(routine_id: str) -> dict[str, Any] | None:
    return next((item for item in _load() if item.get("id") == routine_id), None)


def create_routine(name: str, prompt: str, enabled: bool = True, tags: list[str] | None = None) -> dict[str, Any]:
    items = _load()
    item = _seed_routine({"name": name.strip(), "prompt": prompt.strip(), "enabled": enabled, "tags": tags or []})
    items.append(item)
    _save(items)
    return item


def update_routine(routine_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    items = _load()
    for item in items:
        if item.get("id") == routine_id:
            for key in ("name", "prompt", "enabled", "tags"):
                if key in updates:
                    item[key] = updates[key]
            item["updated_at"] = time.time()
            _save(items)
            return item
    return None


def delete_routine(routine_id: str) -> bool:
    items = _load()
    kept = [item for item in items if item.get("id") != routine_id]
    if len(kept) == len(items):
        return False
    _save(kept)
    return True


def mark_routine_run(routine_id: str) -> dict[str, Any] | None:
    items = _load()
    for item in items:
        if item.get("id") == routine_id:
            item["last_run_at"] = time.time()
            item["updated_at"] = item["last_run_at"]
            _save(items)
            return item
    return None

