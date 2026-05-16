"use client";

import { useCallback, useEffect, useState } from "react";
import { getApiBaseUrl, jarvisHeaders } from "@/lib/apiBase";

interface WorkflowCondition {
  type: string;
  action_id?: string;
  value?: string;
}

interface WorkflowAction {
  id?: string;
  type: string;
  title: string;
  prompt?: string;
  message?: string;
  provider?: string;
  calendar_id?: string;
  timezone?: string;
  location?: string;
  notes?: string;
  start?: string;
  end?: string;
  start_date?: string;
  end_date?: string;
  attendees?: string[] | string;
  mailbox?: string;
  days?: number;
  count?: number;
  requires_approval?: boolean;
  condition?: WorkflowCondition;
  retry_count?: number;
  retry_delay_ms?: number;
  on_error?: string;
}

interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  tags?: string[];
}

interface Workflow {
  id: string;
  version?: number;
  name: string;
  description: string;
  trigger: { type: string; rrule?: string; minutes_before?: number };
  actions: WorkflowAction[];
  enabled: boolean;
  tags?: string[];
  visibility?: string;
  last_run_at?: number | null;
}

interface WorkflowVersion {
  id: string;
  workflow_id: string;
  workflow_name: string;
  version: number;
  previous_version?: number | null;
  event: string;
  actor_id: string;
  note?: string;
  changed_fields?: string[];
  snapshot?: Partial<Workflow>;
  created_at: number;
}

interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow_name: string;
  status: string;
  triggered_by: string;
  dry_run: boolean;
  started_at: number;
  completed_at?: number;
  duration_ms?: number;
  error?: string;
  action_results?: Array<{ title?: string; status?: string; response?: string; message?: string; error?: string; approval_id?: string }>;
  timeline?: WorkflowTimelineEntry[];
}

interface WorkflowTimelineAttempt {
  attempt: number;
  status: string;
  error?: string;
  started_at: number;
  completed_at: number;
  duration_ms: number;
}

interface WorkflowTimelineEntry {
  id: string;
  action_id?: string;
  type: string;
  title: string;
  status: string;
  started_at: number;
  completed_at: number;
  duration_ms: number;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  attempts?: WorkflowTimelineAttempt[];
}

interface WorkflowApproval {
  id: string;
  workflow_name: string;
  title: string;
  action_type: string;
  message: string;
  status: string;
  response?: string;
  created_at: number;
}

interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: string;
  status: string;
}

interface CalendarConnection {
  provider: string;
  name: string;
  account_label: string;
  enabled: boolean;
  status: string;
  client_id_configured?: boolean;
  connected?: boolean;
  token_expires_at?: number;
  last_error?: string;
}

interface CalendarState {
  connections: CalendarConnection[];
  providers: Record<string, { name: string; scopes: string[]; oauth_required: boolean }>;
  policy: {
    timezone: string;
    working_hours: { start: string; end: string };
    default_duration_minutes: number;
    conflict_strategy: string;
    auto_create_events: boolean;
    require_confirmation_for_guests: boolean;
    buffer_minutes: number;
  };
}

interface SchedulerStatus {
  enabled: boolean;
  scheduled_count: number;
  due_count: number;
}

interface CalendarPreviewEvent {
  id?: string;
  title?: string;
  start?: string;
  location?: string;
}

interface ProductViewProps {
  authToken?: string | null;
}

const emptyCalendar: CalendarState = {
  connections: [],
  providers: {},
  policy: {
    timezone: "America/Chicago",
    working_hours: { start: "09:00", end: "17:00" },
    default_duration_minutes: 30,
    conflict_strategy: "ask",
    auto_create_events: false,
    require_confirmation_for_guests: true,
    buffer_minutes: 10,
  },
};

const defaultBuilderAction = (type: string, id = `${type}-${Date.now()}-${Math.random().toString(16).slice(2)}`): WorkflowAction => {
  if (type === "calendar_brief") {
    return { id, type, title: "Read calendar", days: 1, count: 10, condition: { type: "always" }, retry_count: 0, retry_delay_ms: 0, on_error: "stop" };
  }
  if (type === "email_digest") {
    return { id, type, title: "Check mail", mailbox: "INBOX", count: 5, condition: { type: "always" }, retry_count: 0, retry_delay_ms: 0, on_error: "stop" };
  }
  if (type === "notification") {
    return { id, type, title: "Notify", message: "Workflow step completed.", condition: { type: "always" }, retry_count: 0, retry_delay_ms: 0, on_error: "stop" };
  }
  if (type === "create_calendar_event") {
    return {
      id,
      type,
      title: "Create event",
      provider: "",
      start: "",
      end: "",
      timezone: "America/Chicago",
      attendees: "",
      requires_approval: true,
      condition: { type: "always" },
      retry_count: 0,
      retry_delay_ms: 0,
      on_error: "stop",
    };
  }
  if (type === "wait_for_approval") {
    return { id, type, title: "Approval", requires_approval: true, condition: { type: "always" }, retry_count: 0, retry_delay_ms: 0, on_error: "stop" };
  }
  return {
    id,
    type: "prompt",
    title: "Run prompt",
    prompt: "Summarize what needs attention and suggest next steps.",
    condition: { type: "always" },
    retry_count: 0,
    retry_delay_ms: 0,
    on_error: "stop",
  };
};

export default function ProductView({ authToken }: ProductViewProps) {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [workflowVersions, setWorkflowVersions] = useState<WorkflowVersion[]>([]);
  const [selectedWorkflowForHistory, setSelectedWorkflowForHistory] = useState<Workflow | null>(null);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [calendar, setCalendar] = useState<CalendarState>(emptyCalendar);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [message, setMessage] = useState("");
  const [customName, setCustomName] = useState("Quick Workflow");
  const [editingWorkflowId, setEditingWorkflowId] = useState<string | null>(null);
  const [triggerMode, setTriggerMode] = useState("manual");
  const [dailyTime, setDailyTime] = useState("08:30");
  const [builderActions, setBuilderActions] = useState<WorkflowAction[]>([defaultBuilderAction("prompt", "prompt-initial")]);
  const [approvals, setApprovals] = useState<WorkflowApproval[]>([]);
  const [memberName, setMemberName] = useState("Operator");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("member");
  const [calendarClientIds, setCalendarClientIds] = useState<Record<string, string>>({});
  const [calendarClientSecrets, setCalendarClientSecrets] = useState<Record<string, string>>({});
  const [calendarPreviews, setCalendarPreviews] = useState<Record<string, CalendarPreviewEvent[]>>({});

  const api = useCallback(async (path: string, init?: RequestInit) => {
    const isJsonBody = typeof init?.body === "string";
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        ...jarvisHeaders(authToken, isJsonBody),
        ...(init?.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || data.detail || "Request failed.");
    }
    return data;
  }, [authToken]);

  const loadData = useCallback(async () => {
    try {
      const [
        templateData,
        workflowData,
        runData,
        teamData,
        calendarData,
        schedulerData,
        approvalData,
      ] = await Promise.all([
        api("/workflows/templates"),
        api("/workflows"),
        api("/workflows/runs?limit=8"),
        api("/team"),
        api("/calendar/connections"),
        api("/workflows/scheduler/status"),
        api("/workflows/approvals?status=pending&limit=8"),
      ]);
      setTemplates(templateData.templates || []);
      setWorkflows(workflowData.workflows || []);
      setRuns(runData.runs || []);
      setMembers(teamData.members || []);
      setCalendar({ ...emptyCalendar, ...calendarData });
      setScheduler(schedulerData);
      setApprovals(approvalData.approvals || []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load product data.");
    }
  }, [api]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  function resetBuilder() {
    setEditingWorkflowId(null);
    setCustomName("Quick Workflow");
    setTriggerMode("manual");
    setDailyTime("08:30");
    setBuilderActions([defaultBuilderAction("prompt")]);
  }

  function loadWorkflowIntoBuilder(workflow: Workflow) {
    const rrule = workflow.trigger?.rrule || "";
    const hour = rrule.match(/BYHOUR=(\d+)/)?.[1] || "08";
    const minute = rrule.match(/BYMINUTE=(\d+)/)?.[1] || "30";
    setEditingWorkflowId(workflow.id);
    setCustomName(workflow.name);
    setTriggerMode(workflow.trigger?.type === "schedule" ? "schedule" : "manual");
    setDailyTime(`${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`);
    setBuilderActions((workflow.actions?.length ? workflow.actions : [defaultBuilderAction("prompt")]).map((action, index) => ({
      ...action,
      id: action.id || `edit-${index}-${Date.now()}`,
      attendees: Array.isArray(action.attendees) ? action.attendees.join(", ") : action.attendees,
      condition: action.condition || { type: "always" },
      retry_count: action.retry_count || 0,
      retry_delay_ms: action.retry_delay_ms || 0,
      on_error: action.on_error || "stop",
    })));
    setMessage(`Editing ${workflow.name}.`);
  }

  async function loadWorkflowVersions(workflow: Workflow) {
    const data = await api(`/workflows/${workflow.id}/versions?limit=12`);
    setSelectedWorkflowForHistory(workflow);
    setWorkflowVersions(data.versions || []);
  }

  async function createFromTemplate(templateId: string) {
    await api("/workflows/from-template", {
      method: "POST",
      body: JSON.stringify({ template_id: templateId, actor_id: "local-owner" }),
    });
    setMessage("Workflow created from template.");
    await loadData();
  }

  async function createCustomWorkflow() {
    const [hour, minute] = dailyTime.split(":").map((value) => Number.parseInt(value, 10));
    const trigger = triggerMode === "schedule"
      ? { type: "schedule", rrule: `FREQ=DAILY;BYHOUR=${hour || 8};BYMINUTE=${minute || 0}` }
      : { type: "manual" };
    const actions = builderActions.map((action) => ({
      ...action,
      provider: action.provider || undefined,
      attendees: typeof action.attendees === "string"
        ? action.attendees.split(",").map((value) => value.trim()).filter(Boolean)
        : action.attendees,
      condition: action.condition?.type && action.condition.type !== "always" ? action.condition : undefined,
      retry_count: Math.max(0, Math.min(Number(action.retry_count || 0), 3)),
      retry_delay_ms: Math.max(0, Math.min(Number(action.retry_delay_ms || 0), 30000)),
      on_error: action.on_error || "stop",
      requires_approval: action.type === "create_calendar_event" || action.type === "wait_for_approval"
        ? action.requires_approval !== false
        : Boolean(action.requires_approval),
    }));
    const permissions = Array.from(new Set(actions.flatMap((action) => {
      if (action.type === "calendar_brief") return ["calendar:read"];
      if (action.type === "create_calendar_event") return ["calendar:read", "calendar:write"];
      if (action.type === "email_digest") return ["mail:read"];
      if (action.type === "notification") return ["system:notify"];
      return ["llm:chat"];
    })));
    const endpoint = editingWorkflowId ? `/workflows/${editingWorkflowId}` : "/workflows";
    const saved = await api(endpoint, {
      method: editingWorkflowId ? "PUT" : "POST",
      body: JSON.stringify({
        name: customName,
        description: actions.map((action) => action.title).join(" -> ").slice(0, 180),
        trigger,
        actions,
        tags: triggerMode === "schedule" ? ["scheduled"] : ["manual"],
        permissions,
        actor_id: "local-owner",
        version_note: editingWorkflowId ? "Updated from workflow builder." : "Created from workflow builder.",
      }),
    });
    setMessage(editingWorkflowId ? "Workflow updated and versioned." : "Workflow created.");
    setEditingWorkflowId(null);
    await loadData();
    if (saved?.id) {
      await loadWorkflowVersions(saved);
    }
  }

  async function restoreWorkflowVersion(workflowId: string, versionId: string) {
    const restored = await api(`/workflows/${workflowId}/versions/${versionId}/restore`, {
      method: "POST",
      body: JSON.stringify({
        actor_id: "local-owner",
        note: "Restored from workflow history.",
      }),
    });
    setMessage(`Restored ${restored.name || "workflow"} from history.`);
    await loadData();
    await loadWorkflowVersions(restored);
  }

  async function runWorkflow(id: string, dryRun: boolean) {
    const data = await api(`/workflows/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun }),
    });
    setMessage(dryRun ? "Dry run recorded." : `Workflow ran: ${data.run?.status || "complete"}.`);
    if (data.run?.id) {
      setSelectedRun(data.run);
    }
    await loadData();
  }

  async function inspectRun(id: string) {
    const data = await api(`/workflows/runs/${id}`);
    setSelectedRun(data);
  }

  function updateBuilderAction(index: number, updates: Partial<WorkflowAction>) {
    setBuilderActions((current) => current.map((action, actionIndex) => (
      actionIndex === index ? { ...action, ...updates } : action
    )));
  }

  function changeBuilderActionType(index: number, type: string) {
    setBuilderActions((current) => current.map((action, actionIndex) => (
      actionIndex === index ? { ...defaultBuilderAction(type), id: action.id } : action
    )));
  }

  function addBuilderAction(type: string) {
    setBuilderActions((current) => [...current, defaultBuilderAction(type)]);
  }

  function removeBuilderAction(index: number) {
    setBuilderActions((current) => current.length === 1 ? current : current.filter((_, actionIndex) => actionIndex !== index));
  }

  function moveBuilderAction(index: number, direction: -1 | 1) {
    setBuilderActions((current) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(nextIndex, 0, item);
      return next;
    });
  }

  async function approveWorkflowApproval(id: string) {
    const data = await api(`/workflows/approvals/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ actor: "local-owner" }),
    });
    setMessage(data.response || "Approval completed.");
    await loadData();
  }

  async function rejectWorkflowApproval(id: string) {
    await api(`/workflows/approvals/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ actor: "local-owner" }),
    });
    setMessage("Approval rejected.");
    await loadData();
  }

  async function addMember() {
    await api("/team/members", {
      method: "PUT",
      body: JSON.stringify({
        name: memberName,
        email: memberEmail,
        role: memberRole,
      }),
    });
    setMessage("Team member saved.");
    await loadData();
  }

  async function upsertCalendar(provider: string) {
    await api("/calendar/connections", {
      method: "PUT",
      body: JSON.stringify({
        provider,
        account_label: provider,
        enabled: true,
        status: "needs_auth",
      }),
    });
    setMessage("Calendar connection staged. OAuth can be connected next.");
    await loadData();
  }

  async function saveCalendarCredentials(provider: string) {
    await api(`/calendar/oauth/${provider}/credentials`, {
      method: "PUT",
      body: JSON.stringify({
        client_id: calendarClientIds[provider] || "",
        client_secret: calendarClientSecrets[provider] || "",
      }),
    });
    setMessage(`${provider} credentials saved.`);
    setCalendarClientSecrets((current) => ({ ...current, [provider]: "" }));
    await loadData();
  }

  async function startCalendarOAuth(provider: string) {
    const data = await api(`/calendar/oauth/${provider}/start`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (data.authorization_url) {
      window.open(data.authorization_url, "_blank", "noopener,noreferrer");
      setMessage(`${provider} authorization opened.`);
    }
  }

  async function disconnectCalendar(provider: string) {
    await api(`/calendar/oauth/${provider}/disconnect`, { method: "POST" });
    setMessage(`${provider} disconnected.`);
    await loadData();
  }

  async function testCalendarProvider(provider: string) {
    const data = await api(`/calendar/oauth/${provider}/status`);
    const state = data.connected && data.enabled ? "ready" : data.connected ? "connected but disabled" : "not connected";
    setMessage(`${data.name || provider} is ${state}.`);
  }

  async function previewCalendarProvider(provider: string) {
    const params = new URLSearchParams({ days: "1", limit: "5" });
    const data = await api(`/calendar/providers/${provider}/events?${params.toString()}`);
    const events = Array.isArray(data.events) ? data.events : [];
    setCalendarPreviews((current) => ({ ...current, [provider]: events }));
    setMessage(`${data.provider || provider} returned ${data.count || events.length} event${(data.count || events.length) === 1 ? "" : "s"}.`);
  }

  async function saveCalendarPolicy(updates: Partial<CalendarState["policy"]>) {
    await api("/calendar/policy", {
      method: "PUT",
      body: JSON.stringify(updates),
    });
    setMessage("Calendar policy saved.");
    await loadData();
  }

  return (
    <div className="flex-1 overflow-y-auto jarvis-scrollbar bg-black">
      <div className="px-4 sm:px-6 py-5 space-y-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between border-b border-white/[0.04] pb-4">
          <div>
            <h1 className="text-sm sm:text-base font-semibold tracking-[0.18em] uppercase text-jarvis-text/75">
              Workflows
            </h1>
          </div>
          <div className="flex items-center gap-2 text-2xs font-mono text-jarvis-text-dim/55">
            <span className={`status-dot ${scheduler?.enabled ? "connected" : "disconnected"}`} />
            Scheduler {scheduler?.enabled ? "enabled" : "manual"}
            <span className="text-jarvis-cyan/50">{scheduler?.due_count || 0} due</span>
          </div>
        </div>

        {message && (
          <div className="rounded-md border border-jarvis-cyan/10 bg-jarvis-cyan/5 px-3 py-2 text-xs text-jarvis-text/70">
            {message}
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.9fr] gap-5">
          <div className="space-y-5">
            <section className="jarvis-card">
              <div className="jarvis-card-header">Starter Templates</div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {templates.map((template) => (
                  <div key={template.id} className="rounded-md border border-white/[0.05] bg-white/[0.02] p-3 min-h-36 flex flex-col">
                    <div className="text-sm text-jarvis-text/75 font-medium">{template.name}</div>
                    <p className="text-xs text-jarvis-text-dim/55 leading-relaxed mt-2 flex-1">
                      {template.description}
                    </p>
                    <button
                      className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md mt-3"
                      onClick={() => createFromTemplate(template.id)}
                    >
                      Create
                    </button>
                  </div>
                ))}
              </div>
            </section>

            <section className="jarvis-card">
              <div className="flex items-center justify-between gap-3 mb-3">
                <div className="jarvis-card-header mb-0">
                  {editingWorkflowId ? "Workflow Builder · Editing" : "Workflow Builder"}
                </div>
                {editingWorkflowId && (
                  <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={resetBuilder}>
                    Cancel
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-[0.7fr_1fr] gap-3">
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Name</span>
                    <input className="jarvis-input mt-1" value={customName} onChange={(event) => setCustomName(event.target.value)} />
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="block">
                      <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Trigger</span>
                      <select className="jarvis-input mt-1" value={triggerMode} onChange={(event) => setTriggerMode(event.target.value)}>
                        <option value="manual">Manual</option>
                        <option value="schedule">Daily</option>
                      </select>
                    </label>
                    <label className="block">
                      <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Time</span>
                      <input
                        className="jarvis-input mt-1"
                        type="time"
                        value={dailyTime}
                        disabled={triggerMode !== "schedule"}
                        onChange={(event) => setDailyTime(event.target.value)}
                      />
                    </label>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {["prompt", "calendar_brief", "email_digest", "create_calendar_event", "notification", "wait_for_approval"].map((type) => (
                      <button
                        key={type}
                        className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-2 py-2 rounded-md"
                        onClick={() => addBuilderAction(type)}
                      >
                        + {type.replaceAll("_", " ")}
                      </button>
                    ))}
                  </div>
                  <button className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={createCustomWorkflow}>
                    {editingWorkflowId ? "Update Workflow" : "Save Workflow"}
                  </button>
                </div>
                <div className="space-y-3">
                  {builderActions.map((action, index) => (
                    <div key={action.id || index} className="rounded-md border border-white/[0.05] bg-white/[0.02] p-3 space-y-3">
                      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div className="flex items-center gap-2">
                          <span className="jarvis-badge">Step {index + 1}</span>
                          <select className="jarvis-input max-w-56" value={action.type} onChange={(event) => changeBuilderActionType(index, event.target.value)}>
                            <option value="prompt">Prompt</option>
                            <option value="calendar_brief">Calendar brief</option>
                            <option value="email_digest">Email digest</option>
                            <option value="create_calendar_event">Create event</option>
                            <option value="notification">Notification</option>
                            <option value="wait_for_approval">Approval gate</option>
                          </select>
                        </div>
                        <div className="flex items-center gap-2">
                          <button className="jarvis-btn-ghost text-2xs px-2 py-1 rounded-md" onClick={() => moveBuilderAction(index, -1)}>Up</button>
                          <button className="jarvis-btn-ghost text-2xs px-2 py-1 rounded-md" onClick={() => moveBuilderAction(index, 1)}>Down</button>
                          <button className="jarvis-btn-ghost text-2xs px-2 py-1 rounded-md" onClick={() => removeBuilderAction(index)}>Remove</button>
                        </div>
                      </div>
                      <label className="block">
                        <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Title</span>
                        <input className="jarvis-input mt-1" value={action.title} onChange={(event) => updateBuilderAction(index, { title: event.target.value })} />
                      </label>
                      <ActionFields
                        action={action}
                        index={index}
                        calendar={calendar}
                        updateAction={updateBuilderAction}
                      />
                      <ActionPolicyFields
                        action={action}
                        index={index}
                        actions={builderActions}
                        updateAction={updateBuilderAction}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="jarvis-card">
              <div className="jarvis-card-header">Saved Workflows</div>
              <div className="space-y-3">
                {workflows.length === 0 ? (
                  <p className="text-sm text-jarvis-text-dim/45">No workflows yet.</p>
                ) : workflows.map((workflow) => (
                  <div key={workflow.id} className="rounded-md border border-white/[0.05] bg-white/[0.02] p-3">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-jarvis-text/75 font-medium">{workflow.name}</span>
                          <span className="jarvis-badge">v{workflow.version || 1}</span>
                          <span className="jarvis-badge">{workflow.trigger?.type || "manual"}</span>
                          {!workflow.enabled && <span className="jarvis-badge">disabled</span>}
                        </div>
                        <p className="text-xs text-jarvis-text-dim/55 mt-1 max-w-2xl">{workflow.description || workflow.actions?.[0]?.prompt}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => loadWorkflowIntoBuilder(workflow)}>
                          Edit
                        </button>
                        <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => loadWorkflowVersions(workflow)}>
                          History
                        </button>
                        <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => runWorkflow(workflow.id, true)}>
                          Dry Run
                        </button>
                        <button className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => runWorkflow(workflow.id, false)}>
                          Run
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {selectedWorkflowForHistory && (
              <section className="jarvis-card">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div className="jarvis-card-header mb-0">Version History</div>
                  <span className="jarvis-badge">{selectedWorkflowForHistory.name}</span>
                </div>
                <div className="space-y-3">
                  {workflowVersions.length === 0 ? (
                    <p className="text-sm text-jarvis-text-dim/45">No versions recorded.</p>
                  ) : workflowVersions.map((version) => (
                    <div key={version.id} className="rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs text-jarvis-text/70">Version {version.version}</span>
                            <span className="jarvis-badge">{version.event}</span>
                            <span className="text-2xs text-jarvis-text-dim/45 font-mono">
                              {new Date(version.created_at * 1000).toLocaleString()}
                            </span>
                          </div>
                          <div className="text-2xs text-jarvis-text-dim/45 mt-1">
                            {version.actor_id || "local-owner"}
                            {version.changed_fields?.length ? ` · ${version.changed_fields.join(", ")}` : ""}
                            {version.note ? ` · ${version.note}` : ""}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                            onClick={() => version.snapshot && loadWorkflowIntoBuilder(version.snapshot as Workflow)}
                          >
                            Load
                          </button>
                          <button
                            className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                            onClick={() => restoreWorkflowVersion(version.workflow_id, version.id)}
                          >
                            Restore
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section className="jarvis-card">
              <div className="jarvis-card-header">Recent Runs</div>
              <div className="space-y-2">
                {runs.length === 0 ? (
                  <p className="text-sm text-jarvis-text-dim/45">No workflow runs yet.</p>
                ) : runs.map((run) => (
                  <div key={run.id} className="flex items-center justify-between gap-3 rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-2">
                    <div>
                      <div className="text-xs text-jarvis-text/70">{run.workflow_name}</div>
                      <div className="text-2xs text-jarvis-text-dim/45 font-mono">
                        {run.triggered_by} · {run.dry_run ? "dry" : "live"} · {new Date(run.started_at * 1000).toLocaleString()}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => inspectRun(run.id)}>
                        Inspect
                      </button>
                      <span className="jarvis-badge">{run.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {selectedRun && (
              <section className="jarvis-card">
                <div className="jarvis-card-header">Run Timeline</div>
                <div className="rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3 mb-3">
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="text-sm text-jarvis-text/75">{selectedRun.workflow_name}</div>
                      <div className="text-2xs text-jarvis-text-dim/45 font-mono">
                        {selectedRun.triggered_by} · {selectedRun.dry_run ? "dry" : "live"} · {formatDuration(selectedRun.duration_ms)}
                      </div>
                    </div>
                    <span className="jarvis-badge">{selectedRun.status}</span>
                  </div>
                  {selectedRun.error && <div className="text-xs text-red-300/75 mt-2">{selectedRun.error}</div>}
                </div>
                <div className="space-y-3">
                  {(selectedRun.timeline || []).length === 0 ? (
                    <p className="text-sm text-jarvis-text-dim/45">No timeline recorded for this run.</p>
                  ) : selectedRun.timeline?.map((entry, index) => (
                    <TimelineEntryView key={entry.id || `${entry.action_id}-${index}`} entry={entry} index={index} />
                  ))}
                </div>
              </section>
            )}
          </div>

          <div className="space-y-5">
            <section className="jarvis-card">
              <div className="jarvis-card-header">Team Access</div>
              <div className="space-y-3">
                {members.map((member) => (
                  <div key={member.id} className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-xs text-jarvis-text/70">{member.name}</div>
                      <div className="text-2xs text-jarvis-text-dim/45">{member.email || "local account"}</div>
                    </div>
                    <span className="jarvis-badge">{member.role}</span>
                  </div>
                ))}
              </div>
              <div className="jarvis-divider my-4" />
              <div className="space-y-3">
                <input className="jarvis-input" value={memberName} onChange={(event) => setMemberName(event.target.value)} placeholder="Name" />
                <input className="jarvis-input" value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} placeholder="Email" />
                <select className="jarvis-input" value={memberRole} onChange={(event) => setMemberRole(event.target.value)}>
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                  <option value="readonly">Read only</option>
                </select>
                <button className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={addMember}>
                  Save Member
                </button>
              </div>
            </section>

            <section className="jarvis-card">
              <div className="jarvis-card-header">Approval Queue</div>
              <div className="space-y-3">
                {approvals.length === 0 ? (
                  <p className="text-sm text-jarvis-text-dim/45">No pending approvals.</p>
                ) : approvals.map((approval) => (
                  <div key={approval.id} className="rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3 space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-xs text-jarvis-text/70">{approval.workflow_name}</div>
                        <div className="text-2xs text-jarvis-text-dim/45">
                          {approval.title || approval.action_type} · {new Date(approval.created_at * 1000).toLocaleString()}
                        </div>
                      </div>
                      <span className="jarvis-badge">{approval.status}</span>
                    </div>
                    <div className="text-xs text-jarvis-text-dim/55">{approval.message}</div>
                    <div className="flex flex-wrap gap-2">
                      <button className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => approveWorkflowApproval(approval.id)}>
                        Approve
                      </button>
                      <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => rejectWorkflowApproval(approval.id)}>
                        Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="jarvis-card">
              <div className="jarvis-card-header">Calendar Providers</div>
              <div className="space-y-3">
                {Object.entries(calendar.providers).map(([provider, details]) => {
                  const connection = calendar.connections.find((item) => item.provider === provider);
                  const previewEvents = calendarPreviews[provider] || [];
                  return (
                    <div key={provider} className="rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3 space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-xs text-jarvis-text/70">{details.name}</div>
                          <div className="text-2xs text-jarvis-text-dim/45">{connection?.status || "not_connected"}</div>
                        </div>
                        <span className={`status-dot ${connection?.status === "connected" ? "connected" : "disconnected"}`} />
                      </div>
                      {details.oauth_required ? (
                        <div className="space-y-2">
                          <input
                            className="jarvis-input"
                            value={calendarClientIds[provider] || ""}
                            onChange={(event) => setCalendarClientIds((current) => ({ ...current, [provider]: event.target.value }))}
                            placeholder={connection?.client_id_configured ? "Client ID saved" : "Client ID"}
                          />
                          <input
                            className="jarvis-input"
                            type="password"
                            value={calendarClientSecrets[provider] || ""}
                            onChange={(event) => setCalendarClientSecrets((current) => ({ ...current, [provider]: event.target.value }))}
                            placeholder="Client secret"
                          />
                          <div className="flex flex-wrap gap-2">
                            <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => saveCalendarCredentials(provider)}>
                              Save
                            </button>
                            <button className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => startCalendarOAuth(provider)}>
                              Connect
                            </button>
                            <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => testCalendarProvider(provider)}>
                              Test
                            </button>
                            <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => previewCalendarProvider(provider)}>
                              Preview
                            </button>
                            <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => disconnectCalendar(provider)}>
                              Disconnect
                            </button>
                          </div>
                          {previewEvents.length > 0 && (
                            <div className="space-y-1 rounded-md border border-jarvis-cyan/10 bg-black/20 px-2 py-2">
                              {previewEvents.slice(0, 3).map((event, index) => (
                                <div key={event.id || `${provider}-${index}`} className="text-2xs text-jarvis-text/60">
                                  <span className="font-mono text-jarvis-cyan/55">{event.start || "unscheduled"}</span>
                                  <span className="text-jarvis-text-dim/45"> · </span>
                                  <span>{event.title || "(Untitled)"}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => upsertCalendar(provider)}>
                          Stage
                        </button>
                      )}
                      {connection?.last_error && (
                        <div className="text-2xs text-red-300/75">
                          {connection.last_error}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="jarvis-card">
              <div className="jarvis-card-header">Scheduling Policy</div>
              <div className="space-y-3">
                <PolicyRow label="Timezone" value={calendar.policy.timezone} />
                <PolicyRow label="Hours" value={`${calendar.policy.working_hours.start}-${calendar.policy.working_hours.end}`} />
                <PolicyRow label="Conflicts" value={calendar.policy.conflict_strategy} />
                <PolicyRow label="Auto create" value={calendar.policy.auto_create_events ? "on" : "off"} />
                <div className="flex flex-wrap gap-2 pt-2">
                  <button
                    className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                    onClick={() => saveCalendarPolicy({ auto_create_events: false, conflict_strategy: "ask" })}
                  >
                    Ask First
                  </button>
                  <button
                    className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                    onClick={() => saveCalendarPolicy({ require_confirmation_for_guests: true })}
                  >
                    Confirm Guests
                  </button>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatDuration(value?: number) {
  if (typeof value !== "number") return "0 ms";
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.max(0, Math.round(value))} ms`;
}

function formatTraceValue(value: unknown) {
  if (value === undefined || value === null || value === "") return "none";
  if (typeof value === "string") return value.length > 180 ? `${value.slice(0, 180)}...` : value;
  try {
    const text = JSON.stringify(value);
    return text.length > 180 ? `${text.slice(0, 180)}...` : text;
  } catch {
    return String(value);
  }
}

function TimelineEntryView({ entry, index }: { entry: WorkflowTimelineEntry; index: number }) {
  const output = entry.output || {};
  const input = entry.input || {};
  const outputText = output.response || output.message || output.error || "none";
  return (
    <div className="rounded-md border border-white/[0.05] bg-white/[0.02] px-3 py-3 space-y-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <span className="jarvis-badge">Step {index + 1}</span>
          <span className="text-sm text-jarvis-text/75">{entry.title || entry.type}</span>
          <span className="text-2xs text-jarvis-text-dim/45">{entry.type.replaceAll("_", " ")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xs font-mono text-jarvis-text-dim/45">{formatDuration(entry.duration_ms)}</span>
          <span className="jarvis-badge">{entry.status}</span>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <TraceRow label="Input" value={input.prompt || input.message || input.provider || input.mailbox || input.condition || input.type} />
        <TraceRow label="Output" value={outputText} />
      </div>
      {entry.attempts && entry.attempts.length > 0 && (
        <div className="space-y-1">
          {entry.attempts.map((attempt) => (
            <div key={attempt.attempt} className="flex items-center justify-between gap-3 rounded-md border border-white/[0.04] bg-black/20 px-2 py-1">
              <span className="text-2xs text-jarvis-text/60">Attempt {attempt.attempt}</span>
              <span className="text-2xs text-jarvis-text-dim/45">{attempt.error || attempt.status} · {formatDuration(attempt.duration_ms)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TraceRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded-md border border-white/[0.04] bg-black/20 px-2 py-2">
      <div className="text-2xs text-jarvis-text-dim/45 uppercase tracking-wider">{label}</div>
      <div className="text-xs text-jarvis-text/60 mt-1 break-words">{formatTraceValue(value)}</div>
    </div>
  );
}

function ActionFields({
  action,
  index,
  calendar,
  updateAction,
}: {
  action: WorkflowAction;
  index: number;
  calendar: CalendarState;
  updateAction: (index: number, updates: Partial<WorkflowAction>) => void;
}) {
  const providerSelect = (
    <label className="block">
      <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Provider</span>
      <select
        className="jarvis-input mt-1"
        value={action.provider || ""}
        onChange={(event) => updateAction(index, { provider: event.target.value })}
      >
        <option value="">Local</option>
        {Object.entries(calendar.providers)
          .filter(([, details]) => details.oauth_required)
          .map(([provider, details]) => (
            <option key={provider} value={provider}>{details.name}</option>
          ))}
      </select>
    </label>
  );

  if (action.type === "prompt") {
    return (
      <label className="block">
        <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Prompt</span>
        <textarea
          className="jarvis-input mt-1 min-h-28 resize-none"
          value={action.prompt || ""}
          onChange={(event) => updateAction(index, { prompt: event.target.value })}
        />
      </label>
    );
  }

  if (action.type === "calendar_brief") {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        {providerSelect}
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Days</span>
          <input
            className="jarvis-input mt-1"
            type="number"
            min={1}
            max={14}
            value={action.days || 1}
            onChange={(event) => updateAction(index, { days: Number.parseInt(event.target.value, 10) || 1 })}
          />
        </label>
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Limit</span>
          <input
            className="jarvis-input mt-1"
            type="number"
            min={1}
            max={50}
            value={action.count || 10}
            onChange={(event) => updateAction(index, { count: Number.parseInt(event.target.value, 10) || 10 })}
          />
        </label>
      </div>
    );
  }

  if (action.type === "email_digest") {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Mailbox</span>
          <input className="jarvis-input mt-1" value={action.mailbox || "INBOX"} onChange={(event) => updateAction(index, { mailbox: event.target.value })} />
        </label>
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Count</span>
          <input
            className="jarvis-input mt-1"
            type="number"
            min={1}
            max={25}
            value={action.count || 5}
            onChange={(event) => updateAction(index, { count: Number.parseInt(event.target.value, 10) || 5 })}
          />
        </label>
      </div>
    );
  }

  if (action.type === "notification") {
    return (
      <label className="block">
        <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Message</span>
        <input className="jarvis-input mt-1" value={action.message || ""} onChange={(event) => updateAction(index, { message: event.target.value })} />
      </label>
    );
  }

  if (action.type === "create_calendar_event") {
    const attendees = Array.isArray(action.attendees) ? action.attendees.join(", ") : action.attendees || "";
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {providerSelect}
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Start</span>
            <input className="jarvis-input mt-1" type="datetime-local" value={action.start || ""} onChange={(event) => updateAction(index, { start: event.target.value })} />
          </label>
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">End</span>
            <input className="jarvis-input mt-1" type="datetime-local" value={action.end || ""} onChange={(event) => updateAction(index, { end: event.target.value })} />
          </label>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Calendar ID</span>
            <input className="jarvis-input mt-1" value={action.calendar_id || ""} onChange={(event) => updateAction(index, { calendar_id: event.target.value })} />
          </label>
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Timezone</span>
            <input className="jarvis-input mt-1" value={action.timezone || calendar.policy.timezone} onChange={(event) => updateAction(index, { timezone: event.target.value })} />
          </label>
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Location</span>
            <input className="jarvis-input mt-1" value={action.location || ""} onChange={(event) => updateAction(index, { location: event.target.value })} />
          </label>
        </div>
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Attendees</span>
          <input className="jarvis-input mt-1" value={attendees} onChange={(event) => updateAction(index, { attendees: event.target.value })} />
        </label>
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Notes</span>
          <textarea className="jarvis-input mt-1 min-h-20 resize-none" value={action.notes || ""} onChange={(event) => updateAction(index, { notes: event.target.value })} />
        </label>
        <label className="flex items-center gap-2 rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-2">
          <input
            type="checkbox"
            checked={action.requires_approval !== false}
            onChange={(event) => updateAction(index, { requires_approval: event.target.checked })}
          />
          <span className="text-2xs text-jarvis-text/60 uppercase tracking-wider">Require Approval</span>
        </label>
      </div>
    );
  }

  return (
    <div className="text-xs text-jarvis-text-dim/55">
      {action.requires_approval === false ? "Approval disabled" : "Approval required"}
    </div>
  );
}

function ActionPolicyFields({
  action,
  index,
  actions,
  updateAction,
}: {
  action: WorkflowAction;
  index: number;
  actions: WorkflowAction[];
  updateAction: (index: number, updates: Partial<WorkflowAction>) => void;
}) {
  const condition = action.condition || { type: "always" };
  const previousActions = actions.slice(0, index);
  const setCondition = (updates: Partial<WorkflowCondition>) => {
    updateAction(index, { condition: { ...condition, ...updates } });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_0.8fr] gap-3 rounded-md border border-white/[0.04] bg-black/20 p-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Condition</span>
          <select
            className="jarvis-input mt-1"
            value={condition.type}
            onChange={(event) => setCondition({ type: event.target.value })}
          >
            <option value="always">Always</option>
            <option value="previous_status">Previous status</option>
            <option value="previous_response_contains">Response contains</option>
            <option value="previous_response_not_contains">Response excludes</option>
          </select>
        </label>
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Step</span>
          <select
            className="jarvis-input mt-1"
            value={condition.action_id || ""}
            disabled={condition.type === "always" || previousActions.length === 0}
            onChange={(event) => setCondition({ action_id: event.target.value })}
          >
            <option value="">Previous</option>
            {previousActions.map((item, actionIndex) => (
              <option key={item.id || actionIndex} value={item.id || ""}>
                {actionIndex + 1}. {item.title || item.type}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Value</span>
          {condition.type === "previous_status" ? (
            <select
              className="jarvis-input mt-1"
              value={condition.value || "completed"}
              onChange={(event) => setCondition({ value: event.target.value })}
            >
              <option value="completed">Completed</option>
              <option value="skipped">Skipped</option>
              <option value="approval_required">Approval</option>
              <option value="failed">Failed</option>
            </select>
          ) : (
            <input
              className="jarvis-input mt-1"
              value={condition.value || ""}
              disabled={condition.type === "always"}
              onChange={(event) => setCondition({ value: event.target.value })}
            />
          )}
        </label>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Retries</span>
          <input
            className="jarvis-input mt-1"
            type="number"
            min={0}
            max={3}
            value={action.retry_count || 0}
            onChange={(event) => updateAction(index, { retry_count: Number.parseInt(event.target.value, 10) || 0 })}
          />
        </label>
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Delay ms</span>
          <input
            className="jarvis-input mt-1"
            type="number"
            min={0}
            max={30000}
            value={action.retry_delay_ms || 0}
            onChange={(event) => updateAction(index, { retry_delay_ms: Number.parseInt(event.target.value, 10) || 0 })}
          />
        </label>
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">On Error</span>
          <select className="jarvis-input mt-1" value={action.on_error || "stop"} onChange={(event) => updateAction(index, { on_error: event.target.value })}>
            <option value="stop">Stop</option>
            <option value="continue">Continue</option>
          </select>
        </label>
      </div>
    </div>
  );
}

function PolicyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-2xs text-jarvis-text-dim/45">{label}</span>
      <span className="text-2xs font-mono text-jarvis-text/55 tabular-nums">{value}</span>
    </div>
  );
}
