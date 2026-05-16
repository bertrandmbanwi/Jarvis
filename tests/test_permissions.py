"""Tests for tool permissions and audit behavior."""
import sqlite3

from jarvis.core import permissions
from jarvis.core.permissions import Capability, RiskLevel, assess_tool_call, list_tool_audit, record_tool_audit


def test_shell_tool_requires_confirmation_in_enforce_mode(monkeypatch):
    monkeypatch.setenv("JARVIS_TOOL_PERMISSION_MODE", "enforce")
    decision = assess_tool_call("run_command", {"command": "ls"})
    assert decision.allowed is False
    assert decision.permission.risk == RiskLevel.CRITICAL


def test_shell_tool_is_audited_by_default(monkeypatch):
    monkeypatch.setenv("JARVIS_TOOL_PERMISSION_MODE", "audit")
    decision = assess_tool_call("run_command", {"command": "ls"})
    assert decision.allowed is True
    assert Capability.SHELL in decision.permission.capabilities


def test_record_tool_audit_redacts_sensitive_payload(tmp_path, monkeypatch):
    audit_db = tmp_path / "audit.db"
    monkeypatch.setattr(permissions, "DB_PATH", audit_db)

    record_tool_audit(
        "send_email",
        {"to": "person@example.com", "subject": "Hi", "body": "private message"},
        allowed=True,
        success=True,
        result_preview="draft created",
    )

    with sqlite3.connect(str(audit_db)) as conn:
        row = conn.execute("SELECT tool_name, input_json FROM tool_audit").fetchone()

    assert row[0] == "send_email"
    assert "private message" not in row[1]
    assert "[redacted]" in row[1]


def test_list_tool_audit_returns_recent_redacted_rows(tmp_path, monkeypatch):
    audit_db = tmp_path / "audit.db"
    monkeypatch.setattr(permissions, "DB_PATH", audit_db)

    record_tool_audit(
        "read_file",
        {"path": "/tmp/example.txt"},
        allowed=True,
        success=True,
        result_preview="ok",
    )

    rows = list_tool_audit(limit=10)
    assert rows[0]["tool_name"] == "read_file"
    assert rows[0]["input"]["path"] == "/tmp/example.txt"
    assert rows[0]["allowed"] is True
