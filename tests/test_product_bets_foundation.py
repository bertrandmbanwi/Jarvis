"""Tests for workflow, team, and calendar product-bet foundations."""
from datetime import datetime

import pytest

from jarvis.core import calendar_accounts, team, workflow_scheduler, workflows


@pytest.fixture
def product_bet_files(tmp_path, monkeypatch):
    monkeypatch.setattr(workflows, "WORKFLOWS_FILE", tmp_path / "workflows.json")
    monkeypatch.setattr(workflows, "WORKFLOW_RUNS_FILE", tmp_path / "workflow_runs.json")
    monkeypatch.setattr(team, "TEAM_FILE", tmp_path / "team.json")
    monkeypatch.setattr(calendar_accounts, "CALENDAR_STATE_FILE", tmp_path / "calendar_state.json")


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


def test_team_roles_and_capabilities(product_bet_files):
    member = team.upsert_member(name="Operator", email="operator@example.com", role="member")

    assert team.member_has_capability(member["id"], "workflow:run") is True
    assert team.member_has_capability(member["id"], "team:write") is False
    assert team.get_team()["mode"] == "team"


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
