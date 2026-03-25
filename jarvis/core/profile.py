"""User profile management with persistent JSON storage."""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from jarvis.config import settings

logger = logging.getLogger("jarvis.profile")

PROFILE_FILE = settings.PROFILE_DIR / "profile.json"

# Default profile template
_DEFAULT_PROFILE: dict[str, Any] = {
    "name": "Becs",
    "preferred_address": "sir",
    "preferred_browser": "Google Chrome",
    "preferred_search_engine": "DuckDuckGo",
    "timezone": "",
    "location_city": "Forney",
    "location_state": "Texas",
    "nearby_cities": ["Dallas", "Arlington", "Plano", "Frisco"],
    "preferences": {},
    "shortcuts": {},
    "notes": [],
}

# In-memory profile (loaded on import)
_profile: dict[str, Any] = {}


def _load_profile() -> dict[str, Any]:
    """Load profile from disk or create default."""
    if PROFILE_FILE.exists():
        try:
            data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
            merged = {**_DEFAULT_PROFILE, **data}
            logger.info("User profile loaded from %s", PROFILE_FILE)
            return merged
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load profile: %s. Using defaults.", e)

    _save_profile(_DEFAULT_PROFILE)
    logger.info("Default user profile created at %s", PROFILE_FILE)
    return dict(_DEFAULT_PROFILE)


def _save_profile(data: dict[str, Any]) -> None:
    """Write profile to disk."""
    try:
        PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as e:
        logger.error("Failed to save profile: %s", e)


_profile = _load_profile()


def get_profile() -> dict[str, Any]:
    """Return the full user profile."""

    return dict(_profile)


def get_preference(key: str) -> Optional[Any]:
    """Get a profile field from top-level or preferences sub-dict."""
    if key in _profile:
        return _profile[key]
    return _profile.get("preferences", {}).get(key)


def update_profile(updates: dict[str, Any]) -> dict[str, Any]:
    """Update profile fields; known keys set directly, others go to preferences."""
    known_top_keys = set(_DEFAULT_PROFILE.keys())

    for key, value in updates.items():
        if key in known_top_keys:
            _profile[key] = value
            logger.info("Profile updated: %s = %s", key, value)
        else:
            _profile.setdefault("preferences", {})[key] = value
            logger.info("Preference updated: %s = %s", key, value)

    _save_profile(_profile)
    return dict(_profile)


def add_note(note: str) -> list[str]:
    """Add a note to the user's profile notes list."""
    _profile.setdefault("notes", []).append(note)
    _save_profile(_profile)
    logger.info("Note added to profile: %s", note[:60])
    return list(_profile["notes"])


def delete_preference(key: str) -> bool:
    """Remove a preference from the preferences sub-dict."""
    prefs = _profile.get("preferences", {})
    if key in prefs:
        del prefs[key]
        _save_profile(_profile)
        logger.info("Preference deleted: %s", key)
        return True
    return False


async def get_user_profile() -> str:
    """Get the full user profile as a formatted string."""
    profile = get_profile()
    lines = []
    for key, value in profile.items():
        if key == "preferences" and isinstance(value, dict):
            if value:
                lines.append("Custom preferences:")
                for pk, pv in value.items():
                    lines.append(f"  {pk}: {pv}")
        elif key == "shortcuts" and isinstance(value, dict):
            if value:
                lines.append("Shortcuts:")
                for sk, sv in value.items():
                    lines.append(f"  {sk}: {sv}")
        elif key == "notes" and isinstance(value, list):
            if value:
                lines.append(f"Notes: {len(value)} saved")
                for i, note in enumerate(value[-5:], 1):
                    lines.append(f"  {i}. {note}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


async def update_user_profile(key: str, value: str) -> str:
    """Update a single user profile field."""
    update_profile({key: value})
    return f"Profile updated: {key} = {value}"


async def get_user_preference(key: str) -> str:
    """Get a single user preference by key."""
    val = get_preference(key)
    if val is None:
        return f"No preference found for '{key}'."
    return f"{key}: {val}"


async def add_user_note(note: str) -> str:
    """Save a note to the user's profile."""
    notes = add_note(note)
    return f"Note saved. You now have {len(notes)} note(s)."
