"""Tool permission catalog and audit logging.

JARVIS exposes powerful local tools, so every tool has an explicit operational
classification. The default runtime mode is audit-only to preserve existing
voice flows, while deployments can set JARVIS_TOOL_PERMISSION_MODE=enforce to
block calls that require explicit confirmation.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from jarvis.config import settings
from jarvis.core.tracing import get_trace_id

logger = logging.getLogger("jarvis.permissions")

DB_PATH = settings.DATA_DIR / "jarvis_security_audit.db"
_REDACTED = "[redacted]"
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "body",
    "code",
    "content",
    "password",
    "pin",
    "secret",
    "text",
    "token",
}


class Capability(StrEnum):
    READ_LOCAL = "read_local"
    WRITE_LOCAL = "write_local"
    SYSTEM_CONTROL = "system_control"
    SHELL = "shell"
    BROWSER = "browser"
    EXTERNAL_NETWORK = "external_network"
    COMMUNICATION = "communication"
    MEMORY = "memory"
    OBSERVATION = "observation"
    DESTRUCTIVE = "destructive"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ToolPermission:
    """Operational permissions for a tool."""

    capabilities: frozenset[Capability]
    risk: RiskLevel
    requires_confirmation: bool = False
    reason: str = ""


@dataclass(frozen=True)
class PermissionDecision:
    """Decision returned before a tool executes."""

    allowed: bool
    permission: ToolPermission
    reason: str = ""


def _perm(
    *capabilities: Capability,
    risk: RiskLevel = RiskLevel.LOW,
    requires_confirmation: bool = False,
    reason: str = "",
) -> ToolPermission:
    return ToolPermission(
        capabilities=frozenset(capabilities),
        risk=risk,
        requires_confirmation=requires_confirmation,
        reason=reason,
    )


TOOL_PERMISSIONS: dict[str, ToolPermission] = {
    # macOS app and system controls
    "open_application": _perm(Capability.SYSTEM_CONTROL, risk=RiskLevel.MEDIUM),
    "close_application": _perm(
        Capability.SYSTEM_CONTROL,
        risk=RiskLevel.HIGH,
        requires_confirmation=True,
        reason="Can terminate a user-facing app.",
    ),
    "get_running_applications": _perm(Capability.OBSERVATION),
    "get_frontmost_application": _perm(Capability.OBSERVATION),
    "open_url": _perm(Capability.BROWSER, Capability.EXTERNAL_NETWORK, risk=RiskLevel.MEDIUM),
    "open_url_in_browser": _perm(Capability.BROWSER, Capability.EXTERNAL_NETWORK, risk=RiskLevel.MEDIUM),
    "search_in_browser": _perm(Capability.BROWSER, Capability.EXTERNAL_NETWORK, risk=RiskLevel.MEDIUM),
    "get_system_info": _perm(Capability.OBSERVATION),
    "get_battery_status": _perm(Capability.OBSERVATION),
    "set_volume": _perm(Capability.SYSTEM_CONTROL, risk=RiskLevel.MEDIUM),
    "set_brightness": _perm(Capability.SYSTEM_CONTROL, risk=RiskLevel.MEDIUM),
    "send_notification": _perm(Capability.SYSTEM_CONTROL, Capability.COMMUNICATION, risk=RiskLevel.MEDIUM),
    "get_clipboard": _perm(Capability.READ_LOCAL, Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "set_clipboard": _perm(Capability.WRITE_LOCAL, risk=RiskLevel.MEDIUM),
    "paste_to_app": _perm(Capability.WRITE_LOCAL, Capability.SYSTEM_CONTROL, risk=RiskLevel.HIGH),
    "write_to_app": _perm(Capability.WRITE_LOCAL, Capability.SYSTEM_CONTROL, risk=RiskLevel.HIGH),
    # Filesystem
    "list_directory": _perm(Capability.READ_LOCAL),
    "read_file": _perm(Capability.READ_LOCAL),
    "search_files": _perm(Capability.READ_LOCAL),
    "get_file_info": _perm(Capability.READ_LOCAL),
    "open_file": _perm(Capability.READ_LOCAL, Capability.SYSTEM_CONTROL, risk=RiskLevel.MEDIUM),
    "write_file": _perm(Capability.WRITE_LOCAL, risk=RiskLevel.HIGH),
    "move_file": _perm(Capability.WRITE_LOCAL, risk=RiskLevel.HIGH),
    "copy_file": _perm(Capability.WRITE_LOCAL, risk=RiskLevel.MEDIUM),
    "create_directory": _perm(Capability.WRITE_LOCAL, risk=RiskLevel.MEDIUM),
    # Screen and browser
    "capture_screen": _perm(Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "read_screen_text": _perm(Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "analyze_screen": _perm(Capability.OBSERVATION, Capability.EXTERNAL_NETWORK, risk=RiskLevel.HIGH),
    "browse_web": _perm(Capability.BROWSER, Capability.EXTERNAL_NETWORK, risk=RiskLevel.HIGH),
    "browser_navigate": _perm(Capability.BROWSER, Capability.EXTERNAL_NETWORK, risk=RiskLevel.MEDIUM),
    "browser_screenshot": _perm(Capability.BROWSER, Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "get_browser_state": _perm(Capability.BROWSER, Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "browser_switch_tab": _perm(Capability.BROWSER, risk=RiskLevel.MEDIUM),
    "browser_upload_file": _perm(Capability.BROWSER, Capability.READ_LOCAL, risk=RiskLevel.HIGH),
    "sync_browser_sessions": _perm(Capability.BROWSER, Capability.READ_LOCAL, risk=RiskLevel.HIGH),
    "close_browser": _perm(Capability.BROWSER, risk=RiskLevel.MEDIUM),
    "chrome_navigate": _perm(Capability.BROWSER, Capability.EXTERNAL_NETWORK, risk=RiskLevel.MEDIUM),
    "chrome_click": _perm(Capability.BROWSER, risk=RiskLevel.MEDIUM),
    "chrome_type": _perm(Capability.BROWSER, Capability.WRITE_LOCAL, risk=RiskLevel.HIGH),
    "chrome_read_page": _perm(Capability.BROWSER, Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "chrome_find_elements": _perm(Capability.BROWSER, Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "chrome_screenshot": _perm(Capability.BROWSER, Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "chrome_get_tabs": _perm(Capability.BROWSER, Capability.OBSERVATION, risk=RiskLevel.MEDIUM),
    "chrome_execute_js": _perm(Capability.BROWSER, risk=RiskLevel.HIGH),
    "chrome_fill_form": _perm(Capability.BROWSER, Capability.WRITE_LOCAL, risk=RiskLevel.HIGH),
    "chrome_scroll": _perm(Capability.BROWSER, risk=RiskLevel.MEDIUM),
    "chrome_extension_status": _perm(Capability.OBSERVATION),
    # Shell and coding
    "run_command": _perm(
        Capability.SHELL,
        Capability.DESTRUCTIVE,
        risk=RiskLevel.CRITICAL,
        requires_confirmation=True,
        reason="Can execute arbitrary shell commands.",
    ),
    "run_terminal_command_smart": _perm(
        Capability.SHELL,
        Capability.DESTRUCTIVE,
        risk=RiskLevel.CRITICAL,
        requires_confirmation=True,
        reason="Delegates shell execution to Claude Code.",
    ),
    "run_claude_code": _perm(Capability.SHELL, Capability.WRITE_LOCAL, risk=RiskLevel.CRITICAL),
    "scaffold_project": _perm(Capability.SHELL, Capability.WRITE_LOCAL, risk=RiskLevel.HIGH),
    # Web and external APIs
    "search_web": _perm(Capability.EXTERNAL_NETWORK),
    "search_news": _perm(Capability.EXTERNAL_NETWORK),
    "search_and_read": _perm(Capability.EXTERNAL_NETWORK),
    "get_weather": _perm(Capability.EXTERNAL_NETWORK),
    "fetch_page_text": _perm(Capability.EXTERNAL_NETWORK),
    "fetch_page_links": _perm(Capability.EXTERNAL_NETWORK),
    # Profile, memory, learning
    "get_user_profile": _perm(Capability.MEMORY, Capability.READ_LOCAL),
    "update_user_profile": _perm(Capability.MEMORY, Capability.WRITE_LOCAL, risk=RiskLevel.MEDIUM),
    "get_user_preference": _perm(Capability.MEMORY, Capability.READ_LOCAL),
    "add_user_note": _perm(Capability.MEMORY, Capability.WRITE_LOCAL, risk=RiskLevel.MEDIUM),
    "get_user_facts": _perm(Capability.MEMORY, Capability.READ_LOCAL),
    "search_user_facts": _perm(Capability.MEMORY, Capability.READ_LOCAL),
    "forget_fact": _perm(Capability.MEMORY, Capability.WRITE_LOCAL, risk=RiskLevel.HIGH),
    "get_user_patterns": _perm(Capability.MEMORY, Capability.READ_LOCAL),
    "get_memory_stats": _perm(Capability.MEMORY, Capability.READ_LOCAL),
    "get_plan_status": _perm(Capability.OBSERVATION),
    "get_plan_history": _perm(Capability.READ_LOCAL),
    "cancel_active_plan": _perm(Capability.WRITE_LOCAL, risk=RiskLevel.HIGH),
    "get_learning_insights": _perm(Capability.READ_LOCAL, Capability.OBSERVATION),
    "get_tool_reliability": _perm(Capability.READ_LOCAL, Capability.OBSERVATION),
    "get_proactive_status": _perm(Capability.OBSERVATION),
    "set_proactive_setting": _perm(Capability.WRITE_LOCAL, risk=RiskLevel.MEDIUM),
    "get_agent_status": _perm(Capability.OBSERVATION),
    "get_active_agents": _perm(Capability.OBSERVATION),
    "get_system_health": _perm(Capability.OBSERVATION),
    "get_perf_stats": _perm(Capability.OBSERVATION),
    "get_cache_stats": _perm(Capability.OBSERVATION),
    "clear_cache": _perm(Capability.WRITE_LOCAL, risk=RiskLevel.MEDIUM),
    "get_recent_notes": _perm(Capability.READ_LOCAL, Capability.MEMORY, risk=RiskLevel.MEDIUM),
    "read_note": _perm(Capability.READ_LOCAL, Capability.MEMORY, risk=RiskLevel.MEDIUM),
    "search_notes": _perm(Capability.READ_LOCAL, Capability.MEMORY, risk=RiskLevel.MEDIUM),
    "create_note": _perm(Capability.WRITE_LOCAL, Capability.MEMORY, risk=RiskLevel.MEDIUM),
    "get_note_folders": _perm(Capability.READ_LOCAL, Capability.MEMORY),
    # Calendar and mail
    "get_upcoming_events": _perm(Capability.READ_LOCAL, Capability.COMMUNICATION, risk=RiskLevel.MEDIUM),
    "create_calendar_event": _perm(
        Capability.WRITE_LOCAL,
        Capability.COMMUNICATION,
        risk=RiskLevel.HIGH,
        requires_confirmation=True,
    ),
    "get_calendar_list": _perm(Capability.READ_LOCAL, Capability.COMMUNICATION, risk=RiskLevel.MEDIUM),
    "search_calendar_events": _perm(Capability.READ_LOCAL, Capability.COMMUNICATION, risk=RiskLevel.MEDIUM),
    "get_recent_emails": _perm(Capability.READ_LOCAL, Capability.COMMUNICATION, risk=RiskLevel.MEDIUM),
    "get_unread_count": _perm(Capability.READ_LOCAL, Capability.COMMUNICATION, risk=RiskLevel.MEDIUM),
    "send_email": _perm(
        Capability.COMMUNICATION,
        risk=RiskLevel.HIGH,
        requires_confirmation=True,
        reason="Can send messages externally when confirmed.",
    ),
    "search_emails": _perm(Capability.READ_LOCAL, Capability.COMMUNICATION, risk=RiskLevel.MEDIUM),
    "read_email": _perm(Capability.READ_LOCAL, Capability.COMMUNICATION, risk=RiskLevel.MEDIUM),
}


def get_tool_permission(tool_name: str) -> ToolPermission:
    """Return the explicit permission for a tool, with safe inference fallback."""
    if tool_name in TOOL_PERMISSIONS:
        return TOOL_PERMISSIONS[tool_name]
    if tool_name.startswith("get_") or tool_name.startswith("search_") or tool_name.startswith("read_"):
        return _perm(Capability.READ_LOCAL)
    return _perm(Capability.OBSERVATION, risk=RiskLevel.MEDIUM, reason="Permission inferred from tool name.")


def _permission_mode() -> str:
    mode = os.getenv("JARVIS_TOOL_PERMISSION_MODE", "audit").lower().strip()
    return mode if mode in {"audit", "enforce"} else "audit"


def assess_tool_call(tool_name: str, tool_input: dict[str, Any]) -> PermissionDecision:
    """Assess whether a tool should be allowed to run in the current policy mode."""
    permission = get_tool_permission(tool_name)
    if _permission_mode() == "enforce" and permission.requires_confirmation and not tool_input.get("confirmed", False):
        reason = permission.reason or "Tool requires explicit confirmation."
        return PermissionDecision(allowed=False, permission=permission, reason=reason)
    return PermissionDecision(allowed=True, permission=permission)


def _redact(value: Any, key_hint: str = "") -> Any:
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, key_hint) for v in value[:50]]
    if key_hint.lower() in _SENSITIVE_KEYS:
        return _REDACTED
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...[truncated]"
    return value


def _init_audit_db(path: Path | None = None) -> None:
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tool_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT DEFAULT '',
            tool_name TEXT NOT NULL,
            capabilities TEXT NOT NULL,
            risk TEXT NOT NULL,
            allowed BOOLEAN NOT NULL,
            success BOOLEAN,
            duration_s REAL DEFAULT 0,
            input_json TEXT DEFAULT '{}',
            result_preview TEXT DEFAULT '',
            error TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_tool ON tool_audit(tool_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_trace ON tool_audit(trace_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_audit_created ON tool_audit(created_at DESC)")


def record_tool_audit(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    allowed: bool,
    success: bool | None = None,
    duration_s: float = 0.0,
    result_preview: str = "",
    error: str = "",
) -> None:
    """Persist a redacted audit row for a tool call."""
    permission = get_tool_permission(tool_name)
    try:
        _init_audit_db()
        payload = {
            "trace_id": get_trace_id(),
            "tool_name": tool_name,
            "capabilities": json.dumps(sorted(c.value for c in permission.capabilities)),
            "risk": permission.risk.value,
            "allowed": allowed,
            "success": success,
            "duration_s": round(duration_s, 6),
            "input_json": json.dumps(_redact(tool_input), sort_keys=True, default=str),
            "result_preview": result_preview[:500],
            "error": error[:500],
        }
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """
                INSERT INTO tool_audit (
                    trace_id, tool_name, capabilities, risk, allowed, success,
                    duration_s, input_json, result_preview, error
                )
                VALUES (
                    :trace_id, :tool_name, :capabilities, :risk, :allowed, :success,
                    :duration_s, :input_json, :result_preview, :error
                )
                """,
                payload,
            )
    except Exception as exc:
        logger.debug("Tool audit write failed for %s: %s", tool_name, exc)


def summarize_permissions() -> dict[str, Any]:
    """Return a compact summary useful for tests and diagnostics."""
    by_risk: dict[str, int] = {}
    by_capability: dict[str, int] = {}
    for permission in TOOL_PERMISSIONS.values():
        by_risk[permission.risk.value] = by_risk.get(permission.risk.value, 0) + 1
        for capability in permission.capabilities:
            by_capability[capability.value] = by_capability.get(capability.value, 0) + 1
    return {
        "tool_count": len(TOOL_PERMISSIONS),
        "by_risk": by_risk,
        "by_capability": by_capability,
    }


def list_tool_audit(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent redacted tool audit rows."""
    _init_audit_db()
    bounded_limit = max(1, min(limit, 200))
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, trace_id, tool_name, capabilities, risk, allowed, success,
                   duration_s, input_json, result_preview, error, created_at
            FROM tool_audit
            ORDER BY id DESC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        try:
            item["capabilities"] = json.loads(item["capabilities"])
        except json.JSONDecodeError:
            item["capabilities"] = []
        try:
            item["input"] = json.loads(item.pop("input_json"))
        except json.JSONDecodeError:
            item["input"] = {}
        item["allowed"] = bool(item["allowed"])
        item["success"] = None if item["success"] is None else bool(item["success"])
        results.append(item)
    return results
