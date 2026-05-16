"""Tests for workflow, team, and calendar product-bet foundations."""
import json
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pytest

from jarvis.core import calendar_accounts, calendar_oauth, sqlite_state, team, workflow_scheduler, workflows
from jarvis.tools import calendar_email, mac_control


@pytest.fixture
def product_bet_files(tmp_path, monkeypatch):
    monkeypatch.setattr(workflows, "WORKFLOWS_FILE", tmp_path / "workflows.json")
    monkeypatch.setattr(workflows, "WORKFLOW_RUNS_FILE", tmp_path / "workflow_runs.json")
    monkeypatch.setattr(workflows, "WORKFLOW_APPROVALS_FILE", tmp_path / "workflow_approvals.json")
    monkeypatch.setattr(workflows, "WORKFLOW_VERSIONS_FILE", tmp_path / "workflow_versions.json")
    monkeypatch.setattr(workflows, "WORKFLOW_RELEASES_FILE", tmp_path / "workflow_releases.json")
    monkeypatch.setattr(workflows, "WORKFLOW_EDIT_SESSIONS_FILE", tmp_path / "workflow_edit_sessions.json")
    monkeypatch.setattr(team, "TEAM_FILE", tmp_path / "team.json")
    monkeypatch.setattr(calendar_accounts, "CALENDAR_STATE_FILE", tmp_path / "calendar_state.json")


@pytest.fixture
def fake_calendar_secrets(monkeypatch):
    store: dict[str, str] = {}
    monkeypatch.setattr(calendar_oauth, "set_secret", lambda name, value: store.__setitem__(name, value))
    monkeypatch.setattr(calendar_oauth, "get_secret", lambda name: store.get(name, ""))
    monkeypatch.setattr(calendar_oauth, "delete_secret", lambda name: store.pop(name, None))
    return store


@pytest.mark.asyncio
async def test_workflow_template_can_dry_run(product_bet_files):
    workflow = workflows.create_workflow_from_template("morning_brief")

    assert workflow is not None
    assert workflow["trigger"]["type"] == "schedule"
    assert workflow["permissions"] == ["calendar:read", "llm:chat", "mail:read"]

    run = await workflows.run_workflow(workflow["id"], dry_run=True)

    assert run is not None
    assert run["status"] == "completed"
    assert run["dry_run"] is True
    assert len(run["action_results"]) == 3
    assert workflows.get_overview()["workflow_count"] == 1


@pytest.mark.asyncio
async def test_workflow_runner_executes_prompt_action(product_bet_files):
    workflow = workflows.create_workflow(
        name="Prompt workflow",
        actions=[{"type": "prompt", "title": "Ask", "prompt": "Say hello"}],
    )

    async def runner(prompt: str) -> str:
        return f"ran: {prompt}"

    run = await workflows.run_workflow(workflow["id"], runner=runner)

    assert run is not None
    assert run["action_results"][0]["response"] == "ran: Say hello"


@pytest.mark.asyncio
async def test_workflow_condition_can_skip_branch(product_bet_files):
    workflow = workflows.create_workflow(
        name="Conditional workflow",
        actions=[
            {"id": "first", "type": "prompt", "title": "First", "prompt": "first"},
            {
                "id": "second",
                "type": "prompt",
                "title": "Second",
                "prompt": "second",
                "condition": {
                    "type": "previous_response_contains",
                    "action_id": "first",
                    "value": "continue",
                },
            },
        ],
    )
    prompts: list[str] = []

    async def runner(prompt: str) -> str:
        prompts.append(prompt)
        return "stop here"

    run = await workflows.run_workflow(workflow["id"], runner=runner)

    assert run is not None
    assert prompts == ["first"]
    assert run["action_results"][0]["status"] == "completed"
    assert run["action_results"][1]["status"] == "skipped"
    assert "Condition not met" in run["action_results"][1]["message"]


@pytest.mark.asyncio
async def test_workflow_action_retries_before_succeeding(product_bet_files):
    workflow = workflows.create_workflow(
        name="Retry workflow",
        actions=[{
            "type": "prompt",
            "title": "Retry",
            "prompt": "unstable",
            "retry_count": 2,
        }],
    )
    attempts = 0

    async def runner(prompt: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary failure")
        return f"ok:{prompt}"

    run = await workflows.run_workflow(workflow["id"], runner=runner)

    assert run is not None
    assert run["status"] == "completed"
    assert attempts == 3
    assert run["action_results"][0]["attempts"] == 3
    assert run["action_results"][0]["response"] == "ok:unstable"
    assert len(run["timeline"]) == 1
    assert len(run["timeline"][0]["attempts"]) == 3
    assert run["timeline"][0]["attempts"][0]["status"] == "failed"
    assert run["timeline"][0]["attempts"][2]["status"] == "completed"
    assert run["timeline"][0]["input"]["prompt"] == "unstable"
    assert run["timeline"][0]["output"]["response"] == "ok:unstable"
    assert workflows.get_run(run["id"])["timeline"][0]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_workflow_can_continue_after_step_failure(product_bet_files):
    workflow = workflows.create_workflow(
        name="Continue workflow",
        actions=[
            {"type": "prompt", "title": "Fail", "prompt": "explode", "on_error": "continue"},
            {"type": "prompt", "title": "Next", "prompt": "next"},
        ],
    )

    async def runner(prompt: str) -> str:
        if prompt == "explode":
            raise RuntimeError("boom")
        return f"ok:{prompt}"

    run = await workflows.run_workflow(workflow["id"], runner=runner)

    assert run is not None
    assert run["status"] == "completed_with_errors"
    assert run["action_results"][0]["status"] == "failed"
    assert run["action_results"][0]["error"] == "boom"
    assert run["action_results"][1]["response"] == "ok:next"


@pytest.mark.asyncio
async def test_workflow_timeline_records_skipped_conditions(product_bet_files):
    workflow = workflows.create_workflow(
        name="Timeline skip",
        actions=[
            {"id": "first", "type": "prompt", "title": "First", "prompt": "first"},
            {
                "id": "second",
                "type": "prompt",
                "title": "Second",
                "prompt": "second",
                "condition": {"type": "previous_status", "value": "failed"},
            },
        ],
    )

    async def runner(prompt: str) -> str:
        return f"ok:{prompt}"

    run = await workflows.run_workflow(workflow["id"], runner=runner)

    assert run is not None
    assert [item["status"] for item in run["timeline"]] == ["completed", "skipped"]
    assert run["timeline"][1]["output"]["message"].startswith("Condition not met")


def test_team_roles_and_capabilities(product_bet_files):
    member = team.upsert_member(name="Operator", email="operator@example.com", role="member")

    assert team.member_has_capability(member["id"], "workflow:run") is True
    assert team.member_has_capability(member["id"], "team:write") is False
    assert team.get_team()["mode"] == "team"


def test_workflow_edit_presence_tracks_active_editors(product_bet_files):
    workflow = workflows.create_workflow(
        name="Presence workflow",
        actions=[{"type": "prompt", "title": "Ask", "prompt": "hello"}],
    )
    operator = team.upsert_member(name="Operator", email="operator@example.com", role="admin")

    first = workflows.start_workflow_edit(
        workflow["id"],
        actor_id=operator["id"],
        actor_name=operator["name"],
        session_id="operator-session",
    )
    second = workflows.start_workflow_edit(
        workflow["id"],
        actor_id="local-owner",
        actor_name="Owner",
        session_id="owner-session",
    )

    assert first is not None
    assert second is not None
    presence = workflows.get_workflow_presence(
        workflow["id"],
        actor_id="local-owner",
        current_session_id="owner-session",
    )

    assert presence is not None
    assert presence["has_conflict"] is True
    assert presence["other_editors"][0]["actor_name"] == "Operator"
    assert workflows.heartbeat_workflow_edit(workflow["id"], "owner-session", actor_id="local-owner") is not None
    assert workflows.end_workflow_edit(workflow["id"], "operator-session", actor_id=operator["id"]) is True

    cleared = workflows.get_workflow_presence(
        workflow["id"],
        actor_id="local-owner",
        current_session_id="owner-session",
    )

    assert cleared is not None
    assert cleared["has_conflict"] is False
    assert cleared["other_editors"] == []


def test_workflow_update_conflicts_with_active_editor(product_bet_files):
    workflow = workflows.create_workflow(
        name="Conflict workflow",
        actions=[{"type": "prompt", "title": "Ask", "prompt": "hello"}],
    )
    owner_session = workflows.start_workflow_edit(
        workflow["id"],
        actor_id="local-owner",
        actor_name="Owner",
        session_id="owner-session",
    )
    operator_session = workflows.start_workflow_edit(
        workflow["id"],
        actor_id="operator",
        actor_name="Operator",
        session_id="operator-session",
    )

    assert owner_session is not None
    assert operator_session is not None

    blocked = workflows.update_workflow_with_conflict_check(
        workflow["id"],
        {"name": "Blocked update"},
        actor_id="local-owner",
        base_version=workflow["version"],
        edit_session_id="owner-session",
    )
    forced = workflows.update_workflow_with_conflict_check(
        workflow["id"],
        {"name": "Forced update"},
        actor_id="local-owner",
        base_version=workflow["version"],
        edit_session_id="owner-session",
        conflict_strategy="force",
    )

    assert blocked["status"] == "conflict"
    assert blocked["conflict"]["reasons"][0]["type"] == "active_editor_conflict"
    assert "Operator" in blocked["conflict"]["message"]
    assert forced["status"] == "updated"
    assert forced["workflow"]["name"] == "Forced update"


def test_workflow_update_conflicts_with_stale_base_version(product_bet_files):
    workflow = workflows.create_workflow(
        name="Stale workflow",
        actions=[{"type": "prompt", "title": "Ask", "prompt": "hello"}],
    )
    session = workflows.start_workflow_edit(
        workflow["id"],
        actor_id="local-owner",
        session_id="owner-session",
    )
    updated = workflows.update_workflow(
        workflow["id"],
        {"name": "Updated elsewhere"},
        actor_id="operator",
    )

    assert session is not None
    assert updated is not None

    blocked = workflows.update_workflow_with_conflict_check(
        workflow["id"],
        {"name": "Stale save"},
        actor_id="local-owner",
        base_version=workflow["version"],
        edit_session_id="owner-session",
    )

    assert blocked["status"] == "conflict"
    assert blocked["conflict"]["reasons"][0]["type"] == "version_conflict"
    assert blocked["conflict"]["current_version"] == 2


def test_product_state_imports_legacy_json_to_sqlite(product_bet_files):
    now = 1778940000.0
    legacy_workflow = {
        "id": "legacy-workflow",
        "version": 1,
        "name": "Legacy Workflow",
        "description": "Imported from JSON",
        "trigger": {"type": "manual"},
        "actions": [{"id": "action-1", "type": "prompt", "title": "Ask", "prompt": "hello"}],
        "enabled": True,
        "tags": [],
        "owner_id": "local-owner",
        "visibility": "private",
        "permissions": ["llm:chat"],
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
    }
    workflows.WORKFLOWS_FILE.write_text(json.dumps([legacy_workflow]), encoding="utf-8")
    team.TEAM_FILE.write_text(json.dumps({
        "id": "legacy-team",
        "name": "Imported Team",
        "mode": "team",
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
            },
            {
                "id": "member-1",
                "name": "Operator",
                "email": "operator@example.com",
                "role": "member",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        ],
    }), encoding="utf-8")
    calendar_accounts.CALENDAR_STATE_FILE.write_text(json.dumps({
        "connections": [
            {
                "provider": "google",
                "name": "Google Calendar",
                "account_label": "Work",
                "enabled": True,
                "status": "connected",
                "scopes": ["calendar.events"],
                "created_at": now,
                "updated_at": now,
            }
        ],
        "policy": {
            "timezone": "America/Chicago",
            "working_hours": {"start": "09:00", "end": "17:00"},
            "default_duration_minutes": 30,
            "conflict_strategy": "ask",
            "auto_create_events": True,
            "require_confirmation_for_guests": False,
            "buffer_minutes": 10,
        },
        "created_at": now,
        "updated_at": now,
    }), encoding="utf-8")

    assert workflows.list_workflows()[0]["id"] == "legacy-workflow"
    assert team.get_team()["name"] == "Imported Team"
    assert calendar_accounts.list_connections()[0]["provider"] == "google"

    status = sqlite_state.migration_status(sqlite_state.db_path_for(workflows.WORKFLOWS_FILE))

    assert status["workflows"]["migrated_from"] == str(workflows.WORKFLOWS_FILE)
    assert status["team"]["migrated_from"] == str(team.TEAM_FILE)
    assert status["calendar_state"]["migrated_from"] == str(calendar_accounts.CALENDAR_STATE_FILE)


def test_workflow_run_history_imports_to_indexed_sqlite(product_bet_files):
    legacy_run = {
        "id": "legacy-run",
        "workflow_id": "legacy-workflow",
        "workflow_name": "Legacy Workflow",
        "workflow_version": 1,
        "workflow_version_id": "version-1",
        "release_channel": "",
        "release_id": "",
        "status": "completed",
        "triggered_by": "manual",
        "dry_run": True,
        "action_results": [{"status": "prepared", "message": "ok"}],
        "timeline": [
            {
                "id": "step-1",
                "action_id": "action-1",
                "type": "prompt",
                "title": "Ask",
                "status": "prepared",
                "started_at": 1778940000.0,
                "completed_at": 1778940001.0,
                "duration_ms": 1000,
                "input": {"prompt": "hello"},
                "output": {"message": "ok"},
                "attempts": [
                    {
                        "attempt": 1,
                        "status": "prepared",
                        "started_at": 1778940000.0,
                        "completed_at": 1778940001.0,
                        "duration_ms": 1000,
                    }
                ],
            }
        ],
        "error": "",
        "started_at": 1778940000.0,
        "completed_at": 1778940001.0,
        "duration_ms": 1000,
    }
    workflows.WORKFLOW_RUNS_FILE.write_text(json.dumps([legacy_run]), encoding="utf-8")

    runs = workflows.list_runs(
        workflow_id="legacy-workflow",
        workflow_version_id="version-1",
        dry_run=True,
    )
    status = workflows.get_run_storage_status()

    assert [run["id"] for run in runs] == ["legacy-run"]
    assert workflows.get_run("legacy-run")["timeline"][0]["attempts"][0]["status"] == "prepared"
    assert status["indexed"] is True
    assert status["runs"] == 1
    assert status["steps"] == 1
    assert status["attempts"] == 1


@pytest.mark.asyncio
async def test_workflow_run_analytics_reports_health_and_action_failures(product_bet_files):
    success = workflows.create_workflow(
        name="Healthy workflow",
        actions=[{"type": "prompt", "title": "Healthy step", "prompt": "ok"}],
    )
    failure = workflows.create_workflow(
        name="Failing workflow",
        actions=[{"type": "prompt", "title": "Unstable step", "prompt": "fail"}],
    )

    async def runner(prompt: str) -> str:
        if prompt == "fail":
            raise RuntimeError("model outage")
        return "done"

    await workflows.run_workflow(success["id"], runner=runner)
    await workflows.run_workflow(failure["id"], runner=runner)

    analytics = workflows.get_run_analytics()

    assert analytics["total_runs"] == 2
    assert analytics["status_counts"]["completed"] == 1
    assert analytics["status_counts"]["failed"] == 1
    assert analytics["success_rate"] == 0.5
    assert analytics["failure_rate"] == 0.5
    assert analytics["recent_errors"][0]["error"] == "model outage"
    assert analytics["action_stats"][0]["title"] == "Unstable step"
    assert analytics["action_stats"][0]["failed"] == 1


@pytest.mark.asyncio
async def test_workflow_run_records_cost_attribution(product_bet_files, monkeypatch):
    zero = {
        "total_cost_usd": 0.0,
        "total_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_creation_tokens": 0,
    }
    after = {
        "total_cost_usd": 0.0042,
        "total_requests": 1,
        "total_input_tokens": 1200,
        "total_output_tokens": 300,
        "total_cache_read_tokens": 400,
        "total_cache_creation_tokens": 50,
    }
    snapshots = [zero, zero, after, after]

    def fake_cost_summary():
        return snapshots.pop(0) if snapshots else after

    monkeypatch.setattr(workflows.cost_tracker, "get_today_summary", fake_cost_summary)
    workflow = workflows.create_workflow(
        name="Costed workflow",
        actions=[{"type": "prompt", "title": "Costed", "prompt": "measure cost"}],
    )

    async def runner(prompt: str) -> str:
        return f"ok:{prompt}"

    run = await workflows.run_workflow(workflow["id"], runner=runner)
    analytics = workflows.get_run_analytics(workflow_id=workflow["id"])

    assert run is not None
    assert run["cost"]["cost_usd"] == 0.0042
    assert run["cost"]["request_count"] == 1
    assert run["timeline"][0]["output"]["cost"]["input_tokens"] == 1200
    assert run["action_results"][0]["cost"]["cache_read_tokens"] == 400
    assert workflows.get_run(run["id"])["cost"]["output_tokens"] == 300
    assert analytics["total_cost_usd"] == 0.0042
    assert analytics["action_stats"][0]["avg_cost_usd"] == 0.0042


@pytest.mark.asyncio
async def test_workflow_run_replay_uses_original_version_snapshot(product_bet_files):
    workflow = workflows.create_workflow(
        name="Replay workflow",
        actions=[{"type": "prompt", "title": "Original", "prompt": "original prompt"}],
    )
    original_version = workflows.list_workflow_versions(workflow["id"])[0]
    source_prompts: list[str] = []

    async def runner(prompt: str) -> str:
        source_prompts.append(prompt)
        return f"ok:{prompt}"

    source_run = await workflows.run_workflow_version(
        workflow["id"],
        original_version["id"],
        runner=runner,
        dry_run=False,
    )
    updated = workflows.update_workflow(
        workflow["id"],
        {"actions": [{"type": "prompt", "title": "Changed", "prompt": "changed prompt"}]},
    )

    assert source_run is not None
    assert updated is not None
    assert source_prompts == ["original prompt"]

    source_prompts.clear()
    replay = await workflows.replay_run(source_run["id"], runner=runner, dry_run=False)

    assert replay is not None
    assert replay["strategy"] == "version_snapshot"
    assert replay["replay_run"]["replayed_from_run_id"] == source_run["id"]
    assert replay["replay_run"]["replay"]["source_status"] == "completed"
    assert source_prompts == ["original prompt"]


def test_workflow_version_history_can_restore_snapshots(product_bet_files):
    workflow = workflows.create_workflow(
        name="Versioned workflow",
        actions=[{"type": "prompt", "title": "First", "prompt": "original"}],
        actor_id="owner",
    )

    created_versions = workflows.list_workflow_versions(workflow["id"])

    assert len(created_versions) == 1
    assert created_versions[0]["event"] == "created"
    assert created_versions[0]["actor_id"] == "owner"

    updated = workflows.update_workflow(
        workflow["id"],
        {
            "name": "Renamed workflow",
            "actions": [{"type": "prompt", "title": "Second", "prompt": "changed"}],
        },
        actor_id="member-1",
        note="Renamed and changed prompt",
    )

    assert updated is not None
    assert updated["version"] == 2

    versions = workflows.list_workflow_versions(workflow["id"])

    assert [item["event"] for item in versions[:2]] == ["updated", "created"]
    assert versions[0]["previous_version"] == 1
    assert versions[0]["actor_id"] == "member-1"
    assert versions[0]["changed_fields"] == ["actions", "name"]

    restored = workflows.restore_workflow_version(
        workflow["id"],
        created_versions[0]["id"],
        actor_id="owner",
        note="Back to original",
    )

    assert restored is not None
    assert restored["name"] == "Versioned workflow"
    assert restored["actions"][0]["prompt"] == "original"
    assert restored["version"] == 3
    assert workflows.list_workflow_versions(workflow["id"])[0]["event"] == "restored"

    assert workflows.delete_workflow(workflow["id"], actor_id="owner", note="Cleanup") is True
    deleted_versions = workflows.list_workflow_versions(workflow["id"])

    assert deleted_versions[0]["event"] == "deleted"
    assert deleted_versions[0]["note"] == "Cleanup"
    assert workflows.get_workflow(workflow["id"]) is None


@pytest.mark.asyncio
async def test_workflow_release_channel_runs_promoted_snapshot(product_bet_files):
    workflow = workflows.create_workflow(
        name="Stable automation",
        actions=[{"type": "prompt", "title": "Stable", "prompt": "stable prompt"}],
    )
    stable_version = workflows.list_workflow_versions(workflow["id"])[0]

    updated = workflows.update_workflow(
        workflow["id"],
        {"actions": [{"type": "prompt", "title": "Draft", "prompt": "draft prompt"}]},
    )

    assert updated is not None
    release = workflows.publish_workflow_version(
        workflow["id"],
        stable_version["id"],
        channel="stable",
        actor_id="owner",
        note="Promote known-good version",
    )

    assert release is not None
    assert release["version"] == 1
    assert workflows.get_workflow(workflow["id"])["active_release_channel"] == "stable"

    prompts: list[str] = []

    async def runner(prompt: str) -> str:
        prompts.append(prompt)
        return f"ok:{prompt}"

    stable_run = await workflows.run_workflow(workflow["id"], runner=runner)
    draft_run = await workflows.run_workflow(workflow["id"], runner=runner, release_channel="")

    assert stable_run is not None
    assert draft_run is not None
    assert prompts == ["stable prompt", "draft prompt"]
    assert stable_run["release_channel"] == "stable"
    assert stable_run["workflow_version"] == 1
    assert draft_run["release_channel"] == ""
    assert draft_run["workflow_version"] == 2


@pytest.mark.asyncio
async def test_workflow_release_promotion_requires_approval(product_bet_files):
    workflow = workflows.create_workflow(
        name="Approval gated release",
        actions=[{"type": "prompt", "title": "Safe", "prompt": "approved prompt"}],
    )
    version = workflows.list_workflow_versions(workflow["id"])[0]

    blocked = workflows.request_workflow_release_approval(
        workflow["id"],
        version["id"],
        channel="stable",
        actor_id="operator",
        note="Ready for stable.",
    )
    readiness = workflows.get_release_readiness(
        workflow["id"],
        version["id"],
        channel="stable",
        note="Ready for stable.",
    )

    assert blocked is None
    assert readiness["ready"] is False
    assert "A successful dry run is required" in readiness["blockers"][0]

    dry_run = await workflows.run_workflow_version(workflow["id"], version["id"], dry_run=True)

    assert dry_run is not None
    assert dry_run["dry_run"] is True
    assert dry_run["workflow_version_id"] == version["id"]
    assert workflows.get_release_gate_evidence(workflow["id"], version["id"])["ready"] is True

    request = workflows.request_workflow_release_approval(
        workflow["id"],
        version["id"],
        channel="stable",
        actor_id="operator",
        note="Ready for stable.",
    )

    assert request is not None
    assert request["status"] == "pending_approval"
    assert request["requires_approval"] is True
    assert workflows.list_workflow_releases(workflow_id=workflow["id"]) == []
    assert workflows.get_workflow(workflow["id"])["active_release_channel"] == ""

    pending = workflows.list_approvals(status="pending")

    assert len(pending) == 1
    assert pending[0]["action_type"] == "publish_workflow_version"
    assert pending[0]["action"]["channel"] == "stable"
    assert pending[0]["action"]["version"] == 1
    assert pending[0]["action"]["dry_run_id"] == dry_run["id"]

    duplicate = workflows.request_workflow_release_approval(
        workflow["id"],
        version["id"],
        channel="stable",
        actor_id="operator",
        note="Ready for stable.",
    )

    assert duplicate is not None
    assert duplicate["approval"]["id"] == pending[0]["id"]
    assert len(workflows.list_approvals(status="pending")) == 1

    approved = await workflows.approve_approval(pending[0]["id"], actor="owner", note="Approved.")

    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["execution_status"] == "completed"
    assert approved["release_id"]
    assert workflows.get_workflow(workflow["id"])["active_release_channel"] == "stable"
    assert workflows.list_workflow_releases(workflow_id=workflow["id"])[0]["actor_id"] == "owner"


@pytest.mark.asyncio
async def test_workflow_release_requires_passing_assertions(product_bet_files):
    workflow = workflows.create_workflow(
        name="Assertion gated release",
        actions=[{"type": "prompt", "title": "Dry", "prompt": "dry-run prompt"}],
        assertions=[{"type": "output_contains", "title": "Need expected output", "value": "needle"}],
    )
    version = workflows.list_workflow_versions(workflow["id"])[0]
    dry_run = await workflows.run_workflow_version(workflow["id"], version["id"], dry_run=True)

    assert dry_run is not None

    result = workflows.run_workflow_assertion_suite(workflow["id"], version["id"])
    readiness = workflows.get_release_readiness(workflow["id"], version["id"], channel="stable")
    request = workflows.request_workflow_release_approval(
        workflow["id"],
        version["id"],
        channel="stable",
        actor_id="operator",
        note="Ready for stable.",
    )

    assert result is not None
    assert result["status"] == "failed"
    assert result["failed_count"] == 1
    assert workflows.get_run(dry_run["id"])["assertion_result"]["status"] == "failed"
    assert readiness["ready"] is False
    assert readiness["status"] == "failed_assertions"
    assert "Workflow assertions must pass" in readiness["blockers"][0]
    assert request is None


@pytest.mark.asyncio
async def test_workflow_release_blocks_over_budget_dry_run(product_bet_files):
    workflow = workflows.create_workflow(
        name="Budget gated release",
        actions=[{"type": "prompt", "title": "Dry", "prompt": "dry-run prompt"}],
        budget={"max_cost_per_run_usd": 0.001},
    )
    version = workflows.list_workflow_versions(workflow["id"])[0]
    dry_run = await workflows.run_workflow_version(workflow["id"], version["id"], dry_run=True)

    assert dry_run is not None

    dry_run["cost"] = {
        "cost_usd": 0.01,
        "request_count": 1,
        "input_tokens": 1000,
        "output_tokens": 100,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }
    workflows._record_run(dry_run)

    readiness = workflows.get_release_readiness(workflow["id"], version["id"], channel="stable")
    request = workflows.request_workflow_release_approval(
        workflow["id"],
        version["id"],
        channel="stable",
        actor_id="operator",
        note="Ready for stable.",
    )

    assert readiness["ready"] is False
    assert readiness["status"] == "over_budget"
    assert "Workflow cost budget must pass" in readiness["blockers"][0]
    assert "exceeds per-run budget" in readiness["evidence"]["cost_budget"]["blockers"][0]
    assert request is None


@pytest.mark.asyncio
async def test_workflow_assertion_suite_can_pass_for_version_dry_run(product_bet_files):
    workflow = workflows.create_workflow(
        name="Passing assertion release",
        actions=[{"type": "prompt", "title": "Dry", "prompt": "dry-run prompt"}],
        assertions=[{"type": "output_contains", "title": "Prepared output", "value": "prepared"}],
    )
    version = workflows.list_workflow_versions(workflow["id"])[0]

    await workflows.run_workflow_version(workflow["id"], version["id"], dry_run=True)

    result = workflows.run_workflow_assertion_suite(workflow["id"], version["id"])
    readiness = workflows.get_release_readiness(workflow["id"], version["id"], channel="stable")

    assert result is not None
    assert result["status"] == "passed"
    assert result["failed_count"] == 0
    assert readiness["ready"] is True
    assert readiness["evidence"]["assertion_result"]["status"] == "passed"


def test_production_release_request_requires_note(product_bet_files):
    workflow = workflows.create_workflow(
        name="Production candidate",
        actions=[{"type": "prompt", "title": "Deploy", "prompt": "ship it"}],
    )
    version = workflows.list_workflow_versions(workflow["id"])[0]

    assessment = workflows.assess_release_request(workflow["id"], version["id"], channel="production")
    request = workflows.request_workflow_release_approval(workflow["id"], version["id"], channel="production")

    assert assessment["can_request"] is False
    assert "Production promotion requires a release note." in assessment["blockers"]
    assert request is None


def test_calendar_policy_blocks_auto_schedule_until_connected(product_bet_files):
    assessment = calendar_accounts.assess_scheduling_request(
        title="Planning",
        start="2026-05-18T10:00:00",
        attendees=["person@example.com"],
    )

    assert assessment["can_auto_schedule"] is False
    assert "No connected calendar provider is enabled." in assessment["blockers"]

    connection = calendar_accounts.upsert_connection(
        provider="google",
        account_label="Becs",
        enabled=True,
        status="connected",
    )
    assert connection is not None
    policy = calendar_accounts.update_policy({
        "auto_create_events": True,
        "require_confirmation_for_guests": False,
    })
    assert policy["auto_create_events"] is True

    assessment = calendar_accounts.assess_scheduling_request(
        title="Planning",
        start="2026-05-18T10:00:00",
        attendees=[],
        provider="google",
    )
    assert assessment["can_auto_schedule"] is True


def test_calendar_oauth_builds_authorization_url(product_bet_files, fake_calendar_secrets):
    status = calendar_oauth.save_credentials("google", "google-client", "google-secret")

    assert status["configured"] is True

    result = calendar_oauth.build_authorization_url("google", redirect_uri="http://localhost/callback")
    query = parse_qs(urlparse(result["authorization_url"]).query)

    assert query["client_id"] == ["google-client"]
    assert query["redirect_uri"] == ["http://localhost/callback"]
    assert query["response_type"] == ["code"]
    assert result["state"]
    assert calendar_accounts.get_state()["connections"][0]["client_id_configured"] is True
    assert "client_id" not in calendar_accounts.get_state()["connections"][0]


@pytest.mark.asyncio
async def test_calendar_oauth_exchange_and_list_events(product_bet_files, fake_calendar_secrets, monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, json=None, headers=None):
            return FakeResponse({
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/calendar.events",
            })

        async def get(self, url, headers=None, params=None):
            return FakeResponse({
                "items": [
                    {
                        "id": "evt-1",
                        "summary": "Planning",
                        "start": {"dateTime": "2026-05-18T10:00:00Z"},
                        "end": {"dateTime": "2026-05-18T10:30:00Z"},
                        "htmlLink": "https://calendar.google.com/event",
                    }
                ]
            })

    monkeypatch.setattr(calendar_oauth.httpx, "AsyncClient", FakeClient)
    calendar_oauth.save_credentials("google", "google-client", "google-secret")
    auth = calendar_oauth.build_authorization_url("google", redirect_uri="http://localhost/callback")

    status = await calendar_oauth.exchange_code("google", code="oauth-code", state=auth["state"])

    assert status["connected"] is True
    assert status["status"] == "connected"

    events = await calendar_oauth.list_events("google", days=1)

    assert events["count"] == 1
    assert events["events"][0]["title"] == "Planning"


@pytest.mark.asyncio
async def test_scheduler_detects_and_runs_due_workflow(product_bet_files):
    workflow = workflows.create_workflow(
        name="Scheduled",
        trigger={"type": "schedule", "rrule": "FREQ=DAILY;BYHOUR=8;BYMINUTE=30"},
        actions=[{"type": "prompt", "title": "Run", "prompt": "Scheduled prompt"}],
    )
    now = datetime(2026, 5, 18, 8, 30)

    assert workflow_scheduler.is_workflow_due(workflow, now) is True

    runs = await workflow_scheduler.run_due_workflows(now=now, dry_run=True)

    assert len(runs) == 1
    assert runs[0]["workflow_id"] == workflow["id"]
    assert workflow_scheduler.is_workflow_due(workflows.get_workflow(workflow["id"]) or {}, now) is False


@pytest.mark.asyncio
async def test_workflow_calendar_and_email_actions_execute_tools(product_bet_files, monkeypatch):
    async def fake_events(days: int = 1) -> str:
        return f"events:{days}"

    async def fake_unread() -> str:
        return "unread:3"

    async def fake_recent(count: int = 10, mailbox: str = "INBOX") -> str:
        return f"recent:{count}:{mailbox}"

    monkeypatch.setattr(calendar_email, "get_upcoming_events", fake_events)
    monkeypatch.setattr(calendar_email, "get_unread_count", fake_unread)
    monkeypatch.setattr(calendar_email, "get_recent_emails", fake_recent)
    workflow = workflows.create_workflow(
        name="Local tools",
        actions=[
            {"type": "calendar_brief", "title": "Calendar", "days": 2},
            {"type": "email_digest", "title": "Mail", "count": 4, "mailbox": "INBOX"},
        ],
    )

    run = await workflows.run_workflow(workflow["id"])

    assert run is not None
    assert run["action_results"][0]["response"] == "events:2"
    assert "unread:3" in run["action_results"][1]["response"]
    assert "recent:4:INBOX" in run["action_results"][1]["response"]


@pytest.mark.asyncio
async def test_workflow_calendar_brief_reads_oauth_provider(product_bet_files, monkeypatch):
    async def fake_provider_events(provider: str, *, days: int = 1, limit: int = 20, calendar_id: str = "") -> dict:
        return {
            "provider": provider,
            "events": [
                {
                    "id": "evt-1",
                    "title": f"{provider}:{calendar_id or 'primary'}",
                    "start": f"days:{days}:limit:{limit}",
                    "location": "HQ",
                }
            ],
            "count": 1,
        }

    monkeypatch.setattr(calendar_oauth, "list_events", fake_provider_events)
    workflow = workflows.create_workflow(
        name="Provider calendar",
        actions=[{
            "type": "calendar_brief",
            "title": "Calendar",
            "provider": "google",
            "calendar_id": "team-calendar",
            "days": 2,
            "count": 3,
        }],
    )

    run = await workflows.run_workflow(workflow["id"])

    assert run is not None
    response = run["action_results"][0]["response"]
    assert "Google Calendar events" in response
    assert "google:team-calendar" in response
    assert "days:2:limit:3" in response


@pytest.mark.asyncio
async def test_workflow_calendar_brief_falls_back_when_oauth_fails(product_bet_files, monkeypatch):
    async def fake_provider_events(provider: str, *, days: int = 1, limit: int = 20, calendar_id: str = "") -> dict:
        raise ValueError("provider unavailable")

    async def fake_local_events(days: int = 1) -> str:
        return f"local-events:{days}"

    monkeypatch.setattr(calendar_oauth, "list_events", fake_provider_events)
    monkeypatch.setattr(calendar_email, "get_upcoming_events", fake_local_events)
    workflow = workflows.create_workflow(
        name="Fallback calendar",
        actions=[{"type": "calendar_brief", "title": "Calendar", "provider": "outlook", "days": 2}],
    )

    run = await workflows.run_workflow(workflow["id"])

    assert run is not None
    response = run["action_results"][0]["response"]
    assert "Outlook calendar unavailable" in response
    assert "local-events:2" in response


@pytest.mark.asyncio
async def test_workflow_notification_action_executes_tool(product_bet_files, monkeypatch):
    async def fake_notification(title: str, message: str) -> str:
        return f"notified:{title}:{message}"

    monkeypatch.setattr(mac_control, "send_notification", fake_notification)
    workflow = workflows.create_workflow(
        name="Notify workflow",
        actions=[{"type": "notification", "title": "Done", "message": "Workflow complete"}],
    )

    run = await workflows.run_workflow(workflow["id"])

    assert run is not None
    assert run["action_results"][0]["response"] == "notified:Done:Workflow complete"


@pytest.mark.asyncio
async def test_calendar_event_action_requires_approval_by_default(product_bet_files, monkeypatch):
    async def fake_create_event(**kwargs) -> str:
        return f"created:{kwargs['title']}"

    monkeypatch.setattr(calendar_email, "create_calendar_event", fake_create_event)
    workflow = workflows.create_workflow(
        name="Write calendar",
        actions=[{"type": "create_calendar_event", "title": "Planning", "start_date": "May 20, 2026 9:00 AM"}],
    )

    run = await workflows.run_workflow(workflow["id"])

    assert run is not None
    assert run["action_results"][0]["status"] == "approval_required"
    assert "response" not in run["action_results"][0]

    approved = workflows.create_workflow(
        name="Approved write",
        actions=[{
            "type": "create_calendar_event",
            "title": "Planning",
            "start_date": "May 20, 2026 9:00 AM",
            "requires_approval": False,
        }],
    )

    approved_run = await workflows.run_workflow(approved["id"])

    assert approved_run is not None
    assert approved_run["action_results"][0]["response"] == "created:Planning"


@pytest.mark.asyncio
async def test_calendar_event_approval_queue_executes_after_approval(product_bet_files, monkeypatch):
    async def fake_create_event(**kwargs) -> str:
        return f"created:{kwargs['title']}:{kwargs['start_date']}"

    monkeypatch.setattr(calendar_email, "create_calendar_event", fake_create_event)
    workflow = workflows.create_workflow(
        name="Queued write",
        actions=[{"type": "create_calendar_event", "title": "Planning", "start_date": "May 20, 2026 9:00 AM"}],
    )

    run = await workflows.run_workflow(workflow["id"])

    assert run is not None
    result = run["action_results"][0]
    assert result["status"] == "approval_required"
    assert result["approval_id"]
    pending = workflows.list_approvals()
    assert len(pending) == 1
    assert pending[0]["run_id"] == run["id"]

    approved = await workflows.approve_approval(result["approval_id"], actor="Operator", note="Looks right")

    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["execution_status"] == "completed"
    assert approved["response"] == "created:Planning:May 20, 2026 9:00 AM"
    assert workflows.list_approvals() == []


def test_workflow_approval_queue_can_reject_pending_action(product_bet_files):
    workflow = workflows.create_workflow(
        name="Human gate",
        actions=[{"type": "wait_for_approval", "title": "Confirm"}],
    )

    approval = workflows._record_approval(
        workflow=workflow,
        run_id="run-1",
        action=workflow["actions"][0],
        message="Needs a decision.",
        triggered_by="test",
    )
    rejected = workflows.reject_approval(approval["id"], actor="Operator", note="Not now")

    assert rejected is not None
    assert rejected["status"] == "rejected"
    assert rejected["note"] == "Not now"
    assert workflows.list_approvals() == []


@pytest.mark.asyncio
async def test_provider_calendar_event_respects_policy_and_writes_when_allowed(product_bet_files, monkeypatch):
    calls: list[dict] = []

    async def fake_provider_create(provider: str, **kwargs) -> dict:
        calls.append({"provider": provider, **kwargs})
        return {"provider": provider, "event": {"id": "evt-1", "title": kwargs["title"]}}

    monkeypatch.setattr(calendar_oauth, "create_event", fake_provider_create)
    calendar_accounts.upsert_connection(provider="google", account_label="Work", enabled=True, status="connected")

    blocked = workflows.create_workflow(
        name="Blocked provider write",
        actions=[{
            "type": "create_calendar_event",
            "title": "Planning",
            "provider": "google",
            "start": "2026-05-20T09:00:00",
            "end": "2026-05-20T09:30:00",
            "requires_approval": False,
        }],
    )

    blocked_run = await workflows.run_workflow(blocked["id"])

    assert blocked_run is not None
    assert "Auto-create is disabled" in blocked_run["action_results"][0]["response"]
    assert calls == []

    calendar_accounts.update_policy({
        "auto_create_events": True,
        "require_confirmation_for_guests": False,
        "timezone": "America/Chicago",
    })
    allowed = workflows.create_workflow(
        name="Allowed provider write",
        actions=[{
            "type": "create_calendar_event",
            "title": "Planning",
            "provider": "google",
            "calendar_id": "team-calendar",
            "start": "2026-05-20T09:00:00",
            "end": "2026-05-20T09:30:00",
            "attendees": ["person@example.com"],
            "requires_approval": False,
        }],
    )

    allowed_run = await workflows.run_workflow(allowed["id"])

    assert allowed_run is not None
    assert allowed_run["action_results"][0]["response"] == "Created Google calendar event: Planning"
    assert calls[0]["provider"] == "google"
    assert calls[0]["calendar_id"] == "team-calendar"
    assert calls[0]["timezone"] == "America/Chicago"
    assert calls[0]["attendees"] == ["person@example.com"]
