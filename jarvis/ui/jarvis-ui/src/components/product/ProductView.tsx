"use client";

import { useCallback, useEffect, useState } from "react";
import { getApiBaseUrl, jarvisHeaders } from "@/lib/apiBase";

interface WorkflowAction {
  id?: string;
  type: string;
  title: string;
  prompt?: string;
  provider?: string;
  calendar_id?: string;
  days?: number;
  requires_approval?: boolean;
}

interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  tags?: string[];
}

interface Workflow {
  id: string;
  name: string;
  description: string;
  trigger: { type: string; rrule?: string; minutes_before?: number };
  actions: WorkflowAction[];
  enabled: boolean;
  tags?: string[];
  visibility?: string;
  last_run_at?: number | null;
}

interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow_name: string;
  status: string;
  triggered_by: string;
  dry_run: boolean;
  started_at: number;
  action_results?: Array<{ title?: string; status?: string; response?: string; message?: string }>;
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

export default function ProductView({ authToken }: ProductViewProps) {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [calendar, setCalendar] = useState<CalendarState>(emptyCalendar);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [message, setMessage] = useState("");
  const [customName, setCustomName] = useState("Quick Workflow");
  const [customPrompt, setCustomPrompt] = useState("Summarize what needs attention and suggest next steps.");
  const [triggerMode, setTriggerMode] = useState("manual");
  const [dailyTime, setDailyTime] = useState("08:30");
  const [includeCalendarBrief, setIncludeCalendarBrief] = useState(false);
  const [workflowCalendarProvider, setWorkflowCalendarProvider] = useState("");
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
      ] = await Promise.all([
        api("/workflows/templates"),
        api("/workflows"),
        api("/workflows/runs?limit=8"),
        api("/team"),
        api("/calendar/connections"),
        api("/workflows/scheduler/status"),
      ]);
      setTemplates(templateData.templates || []);
      setWorkflows(workflowData.workflows || []);
      setRuns(runData.runs || []);
      setMembers(teamData.members || []);
      setCalendar({ ...emptyCalendar, ...calendarData });
      setScheduler(schedulerData);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load product data.");
    }
  }, [api]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  async function createFromTemplate(templateId: string) {
    await api("/workflows/from-template", {
      method: "POST",
      body: JSON.stringify({ template_id: templateId }),
    });
    setMessage("Workflow created from template.");
    await loadData();
  }

  async function createCustomWorkflow() {
    const [hour, minute] = dailyTime.split(":").map((value) => Number.parseInt(value, 10));
    const trigger = triggerMode === "schedule"
      ? { type: "schedule", rrule: `FREQ=DAILY;BYHOUR=${hour || 8};BYMINUTE=${minute || 0}` }
      : { type: "manual" };
    const actions: WorkflowAction[] = [];
    if (includeCalendarBrief) {
      actions.push({
        type: "calendar_brief",
        title: "Read calendar",
        provider: workflowCalendarProvider || undefined,
        days: 1,
      });
    }
    actions.push({ type: "prompt", title: "Run prompt", prompt: customPrompt });
    await api("/workflows", {
      method: "POST",
      body: JSON.stringify({
        name: customName,
        description: customPrompt.slice(0, 180),
        trigger,
        actions,
        tags: triggerMode === "schedule" ? ["scheduled"] : ["manual"],
        permissions: includeCalendarBrief ? ["calendar:read", "llm:chat"] : ["llm:chat"],
      }),
    });
    setMessage("Workflow created.");
    await loadData();
  }

  async function runWorkflow(id: string, dryRun: boolean) {
    const data = await api(`/workflows/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun }),
    });
    setMessage(dryRun ? "Dry run recorded." : `Workflow ran: ${data.run?.status || "complete"}.`);
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
              <div className="jarvis-card-header">New Prompt Workflow</div>
              <div className="grid grid-cols-1 lg:grid-cols-[0.65fr_1fr] gap-3">
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
                  <label className="flex items-center gap-2 rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-2">
                    <input
                      type="checkbox"
                      checked={includeCalendarBrief}
                      onChange={(event) => setIncludeCalendarBrief(event.target.checked)}
                    />
                    <span className="text-2xs text-jarvis-text/60 uppercase tracking-wider">Calendar Brief</span>
                  </label>
                  <label className="block">
                    <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Calendar Source</span>
                    <select
                      className="jarvis-input mt-1"
                      value={workflowCalendarProvider}
                      disabled={!includeCalendarBrief}
                      onChange={(event) => setWorkflowCalendarProvider(event.target.value)}
                    >
                      <option value="">Local</option>
                      {Object.entries(calendar.providers)
                        .filter(([, details]) => details.oauth_required)
                        .map(([provider, details]) => (
                          <option key={provider} value={provider}>{details.name}</option>
                        ))}
                    </select>
                  </label>
                </div>
                <label className="block">
                  <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Prompt</span>
                  <textarea
                    className="jarvis-input mt-1 min-h-32 resize-none"
                    value={customPrompt}
                    onChange={(event) => setCustomPrompt(event.target.value)}
                  />
                </label>
              </div>
              <button className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md mt-3" onClick={createCustomWorkflow}>
                Save Workflow
              </button>
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
                          <span className="jarvis-badge">{workflow.trigger?.type || "manual"}</span>
                          {!workflow.enabled && <span className="jarvis-badge">disabled</span>}
                        </div>
                        <p className="text-xs text-jarvis-text-dim/55 mt-1 max-w-2xl">{workflow.description || workflow.actions?.[0]?.prompt}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
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
                    <span className="jarvis-badge">{run.status}</span>
                  </div>
                ))}
              </div>
            </section>
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

function PolicyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-2xs text-jarvis-text-dim/45">{label}</span>
      <span className="text-2xs font-mono text-jarvis-text/55 tabular-nums">{value}</span>
    </div>
  );
}
