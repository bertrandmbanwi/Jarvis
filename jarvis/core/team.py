"""Local team and role scaffolding for future multi-user JARVIS installs."""
from __future__ import annotations

import time
import uuid
from typing import Any

from jarvis.config import settings
from jarvis.core import sqlite_state

TEAM_FILE = settings.DATA_DIR / "team.json"

ROLE_CAPABILITIES: dict[str, set[str]] = {
    "owner": {
        "dashboard:read", "settings:write", "workflow:read", "workflow:write", "workflow:run",
        "calendar:read", "calendar:write", "team:read", "team:write", "memory:read", "memory:write",
    },
    "admin": {
        "dashboard:read", "settings:write", "workflow:read", "workflow:write", "workflow:run",
        "calendar:read", "calendar:write", "team:read", "memory:read",
    },
    "member": {"dashboard:read", "workflow:read", "workflow:run", "calendar:read", "memory:read"},
    "readonly": {"dashboard:read", "workflow:read", "calendar:read"},
}


def _now() -> float:
    return time.time()


def _default_team() -> dict[str, Any]:
    now = _now()
    return {
        "id": "local-team",
        "name": "Personal JARVIS",
        "mode": "single_user",
        "created_at": now,
        "updated_at": now,
        "members": [
            {
                "id": "local-owner",
                "name": "Becs",
                "email": "",
                "role": "owner",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    }


def _state_db_path():
    return sqlite_state.db_path_for(TEAM_FILE)


def _load() -> dict[str, Any]:
    default = _default_team()
    data = sqlite_state.load_document(
        db_path=_state_db_path(),
        namespace="team",
        legacy_path=TEAM_FILE,
        default=default,
    )
    return data if isinstance(data, dict) else default


def _save(team: dict[str, Any]) -> None:
    sqlite_state.save_document(
        db_path=_state_db_path(),
        namespace="team",
        data=team,
    )


def _clean(value: Any, limit: int = 160) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def get_team() -> dict[str, Any]:
    team = _load()
    return {**team, "permission_matrix": permission_matrix()}


def list_members() -> list[dict[str, Any]]:
    return list(_load().get("members", []))


def upsert_member(
    *,
    name: str,
    email: str = "",
    role: str = "member",
    member_id: str = "",
    status: str = "active",
) -> dict[str, Any]:
    team = _load()
    members: list[dict[str, Any]] = [
        dict(member) for member in team.get("members", []) if isinstance(member, dict)
    ]
    normalized_role = role if role in ROLE_CAPABILITIES else "member"
    now = _now()
    target_id = member_id or uuid.uuid4().hex

    for member in members:
        if member.get("id") == target_id:
            member.update({
                "name": _clean(name, 120),
                "email": _clean(email, 180),
                "role": normalized_role,
                "status": status if status in {"active", "invited", "disabled"} else "active",
                "updated_at": now,
            })
            team["members"] = members
            team["updated_at"] = now
            _save(team)
            return member

    member = {
        "id": target_id,
        "name": _clean(name, 120),
        "email": _clean(email, 180),
        "role": normalized_role,
        "status": status if status in {"active", "invited", "disabled"} else "active",
        "created_at": now,
        "updated_at": now,
    }
    members.append(member)
    team["members"] = members
    team["mode"] = "team" if len(members) > 1 else team.get("mode", "single_user")
    team["updated_at"] = now
    _save(team)
    return member


def delete_member(member_id: str) -> bool:
    if member_id == "local-owner":
        return False
    team = _load()
    members = list(team.get("members", []))
    kept = [member for member in members if member.get("id") != member_id]
    if len(kept) == len(members):
        return False
    team["members"] = kept
    team["mode"] = "team" if len(kept) > 1 else "single_user"
    team["updated_at"] = _now()
    _save(team)
    return True


def permission_matrix() -> dict[str, list[str]]:
    return {role: sorted(capabilities) for role, capabilities in ROLE_CAPABILITIES.items()}


def member_has_capability(member_id: str, capability: str) -> bool:
    member = next((item for item in list_members() if item.get("id") == member_id), None)
    if member is None or member.get("status") != "active":
        return False
    role = str(member.get("role") or "readonly")
    return capability in ROLE_CAPABILITIES.get(role, set())
