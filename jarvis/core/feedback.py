"""Lightweight feedback log for user corrections and preferences."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from jarvis.config import settings

FEEDBACK_FILE = settings.DATA_DIR / "feedback.json"


def _load() -> list[dict[str, Any]]:
    if not FEEDBACK_FILE.exists():
        return []
    try:
        data = json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save(items: list[dict[str, Any]]) -> None:
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_FILE.write_text(json.dumps(items[-500:], indent=2), encoding="utf-8")


def add_feedback(
    text: str,
    *,
    category: str = "correction",
    source: str = "user",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one feedback/correction item."""
    item = {
        "id": uuid.uuid4().hex,
        "category": category,
        "source": source,
        "text": text.strip(),
        "metadata": metadata or {},
        "created_at": time.time(),
    }
    items = _load()
    items.append(item)
    _save(items)
    return item


def list_feedback(limit: int = 50, category: str = "") -> list[dict[str, Any]]:
    """Return recent feedback items."""
    items = _load()
    if category:
        items = [item for item in items if item.get("category") == category]
    return items[-max(1, min(limit, 200)):]


def delete_feedback(feedback_id: str) -> bool:
    """Delete one feedback item by id."""
    items = _load()
    kept = [item for item in items if item.get("id") != feedback_id]
    if len(kept) == len(items):
        return False
    _save(kept)
    return True
