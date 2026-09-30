"""Request and response models for the HTTP API."""
from typing import Any

from pydantic import BaseModel


class PinRequest(BaseModel):
    pin: str


class SetPinRequest(BaseModel):
    current_pin: str
    new_pin: str


class ChatRequest(BaseModel):
    message: str
    tier: str = ""


class JobRequest(BaseModel):
    message: str
    kind: str = "chat"


class ConfirmActionRequest(BaseModel):
    action_id: str
    approved: bool


class CostEstimateRequest(BaseModel):
    message: str
    tier: str = "brain"


class RoutineRequest(BaseModel):
    name: str
    prompt: str
    enabled: bool = True
    tags: list[str] = []
    schedule_time: str | None = None  # local "HH:MM"
    schedule_days: list[str] = []  # "mon".."sun"; empty = every day
    speak: bool = False


class RoutineRunRequest(BaseModel):
    background: bool = False


class FeedbackRequest(BaseModel):
    text: str
    category: str = "correction"


class BatchRequest(BaseModel):
    prompts: list[str]
    tier: str = "brain"


class PrivacyRequest(BaseModel):
    enabled: bool


class WorkflowRequest(BaseModel):
    name: str
    description: str = ""
    trigger: dict[str, Any] = {}
    actions: list[dict[str, Any]] = []
    assertions: list[dict[str, Any]] = []
    budget: dict[str, Any] = {}
    enabled: bool = True
    tags: list[str] = []
    owner_id: str = "local-owner"
    visibility: str = "private"
    permissions: list[str] = []
    actor_id: str = "local-owner"
    version_note: str = ""
    active_release_channel: str | None = None
    base_version: int | None = None
    edit_session_id: str = ""
    conflict_strategy: str = "reject"


class WorkflowTemplateRequest(BaseModel):
    template_id: str
    owner_id: str = "local-owner"
    actor_id: str = "local-owner"


class WorkflowPackageImportRequest(BaseModel):
    package: dict[str, Any]
    owner_id: str = "local-owner"
    actor_id: str = "local-owner"
    name: str = ""


class WorkflowRunRequest(BaseModel):
    background: bool = False
    dry_run: bool = False
    release_channel: str | None = None


class WorkflowReplayRequest(BaseModel):
    dry_run: bool = True


class WorkflowEditPresenceRequest(BaseModel):
    actor_id: str = "local-owner"
    actor_name: str = ""
    session_id: str = ""
    ttl_seconds: int = 90


class WorkflowAssertionRunRequest(BaseModel):
    run_id: str = ""


class WorkflowApprovalRequest(BaseModel):
    actor: str = "local-owner"
    note: str = ""


class WorkflowVersionRestoreRequest(BaseModel):
    actor_id: str = "local-owner"
    note: str = ""


class WorkflowPublishRequest(BaseModel):
    channel: str = "stable"
    actor_id: str = "local-owner"
    note: str = ""
    activate: bool = True
    require_approval: bool | None = None


class SchedulerRunRequest(BaseModel):
    dry_run: bool = True


class LifecycleLaunchAgentRequest(BaseModel):
    load: bool = False
    unload: bool = False
    dry_run: bool = False


class LifecycleControlRequest(BaseModel):
    mode: str = "full"
    dry_run: bool = False
    delay_seconds: float = 0.75
    force_after_seconds: float = 8.0


class TeamMemberRequest(BaseModel):
    name: str
    email: str = ""
    role: str = "member"
    member_id: str = ""
    status: str = "active"


class CalendarConnectionRequest(BaseModel):
    provider: str
    account_label: str = ""
    enabled: bool = False
    status: str = "not_connected"
    scopes: list[str] = []


class CalendarOAuthCredentialsRequest(BaseModel):
    client_id: str
    client_secret: str = ""


class CalendarOAuthStartRequest(BaseModel):
    redirect_uri: str = ""


class CalendarProviderEventsRequest(BaseModel):
    title: str
    start: str
    end: str
    timezone: str = "UTC"
    location: str = ""
    notes: str = ""
    calendar_id: str = ""
    attendees: list[str] = []


class CalendarPolicyRequest(BaseModel):
    timezone: str | None = None
    working_hours: dict[str, Any] | None = None
    default_duration_minutes: int | None = None
    conflict_strategy: str | None = None
    auto_create_events: bool | None = None
    require_confirmation_for_guests: bool | None = None
    buffer_minutes: int | None = None


class ScheduleAssessmentRequest(BaseModel):
    title: str
    start: str = ""
    end: str = ""
    attendees: list[str] = []
    provider: str = ""


class ChatResponse(BaseModel):
    response: str
    elapsed_ms: float
    tier_used: str
    backend: str
    local_savings: dict


class StatusResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    active_backend: str
    active_model: str
    memory_stats: dict
    conversation_turns: int
    session_cost: dict
    local_savings: dict


class ProactiveSettingsRequest(BaseModel):
    enabled: bool | None = None
    category: str | None = None
    category_enabled: bool | None = None
