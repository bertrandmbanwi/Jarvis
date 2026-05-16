"""Tests for workflow, team, and calendar product-bet foundations."""
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import pytest

from jarvis.core import calendar_accounts, calendar_oauth, team, workflow_scheduler, workflows
from jarvis.tools import calendar_email, mac_control


@pytest.fixture
def product_bet_files(tmp_path, monkeypatch):
    monkeypatch.setattr(workflows, "WORKFLOWS_FILE", tmp_path / "workflows.json")
    monkeypatch.setattr(workflows, "WORKFLOW_RUNS_FILE", tmp_path / "workflow_runs.json")
    monkeypatch.setattr(workflows, "WORKFLOW_APPROVALS_FILE", tmp_path / "workflow_approvals.json")
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
