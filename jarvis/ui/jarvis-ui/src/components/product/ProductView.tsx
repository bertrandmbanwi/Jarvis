"use client";

import { useCallback, useEffect, useState } from "react";
import { getApiBaseUrl, jarvisHeaders } from "@/lib/apiBase";

import type { WorkflowAction, WorkflowAssertion, WorkflowBudget, WorkflowTemplate, WorkflowPackage, Workflow, WorkflowVersion, WorkflowAssertionResult, WorkflowRun, WorkflowEditSession, WorkflowPresence, WorkflowAnalytics, WorkflowApproval, TeamMember, CalendarState, SchedulerStatus, AppLifecycleStatus, CalendarPreviewEvent } from "./types";
import { formatDuration, formatPercent, formatCost, formatTimestamp } from "./format";
import { MetricTile, TimelineEntryView, PolicyRow } from "./parts";
import { AssertionFields, ActionFields, ActionPolicyFields } from "./BuilderFields";
import { defaultBuilderAction, defaultBuilderAssertion, emptyCalendar } from "./builderDefaults";

interface ProductViewProps {
  authToken?: string | null;
}

export default function ProductView({ authToken }: ProductViewProps) {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [runAnalytics, setRunAnalytics] = useState<WorkflowAnalytics | null>(null);
  const [workflowVersions, setWorkflowVersions] = useState<WorkflowVersion[]>([]);
  const [selectedWorkflowForHistory, setSelectedWorkflowForHistory] = useState<Workflow | null>(null);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [calendar, setCalendar] = useState<CalendarState>(emptyCalendar);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [lifecycle, setLifecycle] = useState<AppLifecycleStatus | null>(null);
  const [message, setMessage] = useState("");
  const [workflowPackageText, setWorkflowPackageText] = useState("");
  const [customName, setCustomName] = useState("Quick Workflow");
  const [editingWorkflowId, setEditingWorkflowId] = useState<string | null>(null);
  const [editingBaseVersion, setEditingBaseVersion] = useState<number | null>(null);
  const [editingSession, setEditingSession] = useState<WorkflowEditSession | null>(null);
  const [workflowPresence, setWorkflowPresence] = useState<WorkflowPresence | null>(null);
  const [triggerMode, setTriggerMode] = useState("manual");
  const [dailyTime, setDailyTime] = useState("08:30");
  const [builderActions, setBuilderActions] = useState<WorkflowAction[]>([defaultBuilderAction("prompt", "prompt-initial")]);
  const [builderAssertions, setBuilderAssertions] = useState<WorkflowAssertion[]>([defaultBuilderAssertion("run_status_equals", "assert-initial")]);
  const [budgetPerRun, setBudgetPerRun] = useState("");
  const [budgetPerDay, setBudgetPerDay] = useState("");
  const [budgetPerMonth, setBudgetPerMonth] = useState("");
  const [approvals, setApprovals] = useState<WorkflowApproval[]>([]);
  const [runStatusFilter, setRunStatusFilter] = useState("");
  const [runModeFilter, setRunModeFilter] = useState("all");
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
      const runParams = new URLSearchParams();
      if (runStatusFilter) {
        runParams.set("status", runStatusFilter);
      }
      if (runModeFilter !== "all") {
        runParams.set("dry_run", runModeFilter === "dry" ? "true" : "false");
      }
      const query = runParams.toString();
      const data = await api(`/product/overview${query ? `?${query}` : ""}`);
      setTemplates(data.templates || []);
      setWorkflows(data.workflows || []);
      setRuns(data.runs || []);
      setRunAnalytics(data.analytics || null);
      setMembers(data.team?.members || []);
      setCalendar({ ...emptyCalendar, ...(data.calendar || {}) });
      setScheduler(data.scheduler || null);
      setApprovals(data.approvals || []);
      setLifecycle(data.lifecycle || null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load product data.");
    }
  }, [api, runModeFilter, runStatusFilter]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  useEffect(() => {
    if (!editingWorkflowId || !editingSession?.id) return;
    const interval = setInterval(() => {
      void api(`/workflows/${editingWorkflowId}/presence/${editingSession.id}/heartbeat`, {
        method: "POST",
        body: JSON.stringify({
          actor_id: "local-owner",
          ttl_seconds: 90,
        }),
      }).then((data) => {
        setEditingSession(data.session || null);
        setWorkflowPresence(data.presence || null);
      }).catch(() => undefined);
    }, 30000);
    return () => clearInterval(interval);
  }, [api, editingSession?.id, editingWorkflowId]);

  function endEditingSession(workflowId: string | null = editingWorkflowId, sessionId: string | null = editingSession?.id || null) {
    if (workflowId && sessionId) {
      void api(`/workflows/${workflowId}/presence/${sessionId}?actor_id=local-owner`, { method: "DELETE" }).catch(() => undefined);
    }
    setEditingSession(null);
    setWorkflowPresence(null);
    setEditingBaseVersion(null);
  }

  function resetBuilder() {
    endEditingSession();
    setEditingWorkflowId(null);
    setCustomName("Quick Workflow");
    setTriggerMode("manual");
    setDailyTime("08:30");
    setBuilderActions([defaultBuilderAction("prompt")]);
    setBuilderAssertions([defaultBuilderAssertion("run_status_equals")]);
    setBudgetPerRun("");
    setBudgetPerDay("");
    setBudgetPerMonth("");
  }

  async function loadWorkflowIntoBuilder(workflow: Workflow) {
    endEditingSession();
    const rrule = workflow.trigger?.rrule || "";
    const hour = rrule.match(/BYHOUR=(\d+)/)?.[1] || "08";
    const minute = rrule.match(/BYMINUTE=(\d+)/)?.[1] || "30";
    setEditingWorkflowId(workflow.id);
    setEditingBaseVersion(workflow.version || 1);
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
    setBuilderAssertions((workflow.assertions?.length ? workflow.assertions : [defaultBuilderAssertion("run_status_equals")]).map((assertion, index) => ({
      ...assertion,
      id: assertion.id || `assert-edit-${index}-${Date.now()}`,
      enabled: assertion.enabled !== false,
    })));
    setBudgetPerRun(workflow.budget?.max_cost_per_run_usd ? String(workflow.budget.max_cost_per_run_usd) : "");
    setBudgetPerDay(workflow.budget?.max_cost_per_day_usd ? String(workflow.budget.max_cost_per_day_usd) : "");
    setBudgetPerMonth(workflow.budget?.max_cost_per_month_usd ? String(workflow.budget.max_cost_per_month_usd) : "");
    try {
      const data = await api(`/workflows/${workflow.id}/presence`, {
        method: "POST",
        body: JSON.stringify({
          actor_id: "local-owner",
          actor_name: "Local Owner",
          ttl_seconds: 90,
        }),
      });
      setEditingSession(data.session || null);
      setWorkflowPresence(data.presence || null);
      const otherCount = data.presence?.other_editors?.length || 0;
      setMessage(otherCount > 0 ? `Editing ${workflow.name}; ${otherCount} other editor${otherCount === 1 ? "" : "s"} active.` : `Editing ${workflow.name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Editing ${workflow.name}.`);
    }
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

  async function exportTemplatePackage(templateId: string) {
    const data = await api(`/workflows/templates/${templateId}/package`);
    setWorkflowPackageText(JSON.stringify(data.package || data, null, 2));
    setMessage("Starter package ready.");
  }

  async function exportWorkflowPackage(workflow: Workflow) {
    const data = await api(`/workflows/${workflow.id}/package`);
    setWorkflowPackageText(JSON.stringify(data.package || data, null, 2));
    setMessage(`${workflow.name} package ready.`);
  }

  async function importWorkflowPackage() {
    let packageData: WorkflowPackage;
    try {
      packageData = JSON.parse(workflowPackageText) as WorkflowPackage;
    } catch {
      setMessage("Package JSON is not valid.");
      return;
    }
    const data = await api("/workflows/import-package", {
      method: "POST",
      body: JSON.stringify({
        package: packageData,
        actor_id: "local-owner",
      }),
    });
    setMessage(`Imported ${data.workflow?.name || packageData.name || "workflow package"}.`);
    setWorkflowPackageText("");
    await loadData();
    if (data.workflow?.id) {
      await loadWorkflowVersions(data.workflow);
    }
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
    const assertions = builderAssertions.map((assertion) => ({
      ...assertion,
      title: assertion.title || assertion.type.replaceAll("_", " "),
      enabled: assertion.enabled !== false,
      action_id: assertion.action_id || undefined,
      value: assertion.value || undefined,
      expected_status: assertion.expected_status || undefined,
      max_duration_ms: assertion.type === "max_duration_ms" ? Math.max(1, Number(assertion.max_duration_ms || 30000)) : undefined,
    }));
    const budget: WorkflowBudget = {};
    const perRun = Number.parseFloat(budgetPerRun);
    const perDay = Number.parseFloat(budgetPerDay);
    const perMonth = Number.parseFloat(budgetPerMonth);
    if (Number.isFinite(perRun) && perRun > 0) budget.max_cost_per_run_usd = perRun;
    if (Number.isFinite(perDay) && perDay > 0) budget.max_cost_per_day_usd = perDay;
    if (Number.isFinite(perMonth) && perMonth > 0) budget.max_cost_per_month_usd = perMonth;
    if (Object.keys(budget).length > 0) budget.enforce_on_release = true;
    const endpoint = editingWorkflowId ? `/workflows/${editingWorkflowId}` : "/workflows";
    const editingWorkflowBeforeSave = editingWorkflowId;
    const editingSessionBeforeSave = editingSession?.id || "";
    let saved: Workflow | null = null;
    try {
      saved = await api(endpoint, {
        method: editingWorkflowId ? "PUT" : "POST",
        body: JSON.stringify({
          name: customName,
          description: actions.map((action) => action.title).join(" -> ").slice(0, 180),
          trigger,
          actions,
          assertions,
          budget,
          tags: triggerMode === "schedule" ? ["scheduled"] : ["manual"],
          permissions,
          actor_id: "local-owner",
          version_note: editingWorkflowId ? "Updated from workflow builder." : "Created from workflow builder.",
          base_version: editingWorkflowId ? editingBaseVersion : undefined,
          edit_session_id: editingSessionBeforeSave || undefined,
          conflict_strategy: "reject",
        }),
      });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Workflow could not be saved.");
      return;
    }
    if (editingWorkflowBeforeSave && editingSessionBeforeSave) {
      await api(`/workflows/${editingWorkflowBeforeSave}/presence/${editingSessionBeforeSave}?actor_id=local-owner`, { method: "DELETE" }).catch(() => undefined);
    }
    setMessage(editingWorkflowId ? "Workflow updated and versioned." : "Workflow created.");
    setEditingWorkflowId(null);
    setEditingBaseVersion(null);
    setEditingSession(null);
    setWorkflowPresence(null);
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

  async function dryRunWorkflowVersion(workflowId: string, versionId: string) {
    const data = await api(`/workflows/${workflowId}/versions/${versionId}/dry-run`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setMessage(`Version dry run recorded: ${data.run?.status || "complete"}.`);
    if (data.run?.id) {
      setSelectedRun(data.run);
    }
    await loadData();
    if (selectedWorkflowForHistory?.id === workflowId) {
      await loadWorkflowVersions(selectedWorkflowForHistory);
    }
  }

  async function runAssertionSuite(workflowId: string, versionId: string) {
    const data = await api(`/workflows/${workflowId}/versions/${versionId}/assertions/run`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    const result: WorkflowAssertionResult | undefined = data.result;
    setMessage(result?.passed
      ? `Assertions passed (${result.passed_count}/${result.total}).`
      : `Assertions failed (${result?.failed_count || 0}/${result?.total || 0}).`);
    await loadData();
    if (selectedWorkflowForHistory?.id === workflowId) {
      await loadWorkflowVersions(selectedWorkflowForHistory);
    }
  }

  async function publishWorkflowVersion(workflowId: string, versionId: string) {
    const data = await api(`/workflows/${workflowId}/versions/${versionId}/publish`, {
      method: "POST",
      body: JSON.stringify({
        channel: "stable",
        actor_id: "local-owner",
        note: "Promoted from workflow history.",
        activate: true,
      }),
    });
    setMessage(data.requires_approval ? "Promotion approval requested." : "Stable release promoted and activated.");
    await loadData();
    if (selectedWorkflowForHistory?.id === workflowId) {
      await loadWorkflowVersions(selectedWorkflowForHistory);
    }
  }

  async function runWorkflow(id: string, dryRun: boolean, releaseChannel?: string) {
    const payload: { dry_run: boolean; release_channel?: string } = { dry_run: dryRun };
    if (releaseChannel !== undefined) {
      payload.release_channel = releaseChannel;
    }
    const data = await api(`/workflows/${id}/run`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const channel = data.run?.release_channel ? ` (${data.run.release_channel})` : "";
    setMessage(dryRun ? `Dry run recorded${channel}.` : `Workflow ran${channel}: ${data.run?.status || "complete"}.`);
    if (data.run?.id) {
      setSelectedRun(data.run);
    }
    await loadData();
  }

  async function inspectRun(id: string) {
    const data = await api(`/workflows/runs/${id}`);
    setSelectedRun(data);
  }

  async function replayRun(id: string, dryRun: boolean) {
    const data = await api(`/workflows/runs/${id}/replay`, {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun }),
    });
    const replayed = data.replay_run;
    const warning = Array.isArray(data.warnings) && data.warnings.length ? ` ${data.warnings[0]}` : "";
    setMessage(`${dryRun ? "Dry replay" : "Live replay"} complete via ${data.strategy || "workflow"}.${warning}`);
    if (replayed?.id) {
      setSelectedRun(replayed);
    }
    await loadData();
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

  function updateBuilderAssertion(index: number, updates: Partial<WorkflowAssertion>) {
    setBuilderAssertions((current) => current.map((assertion, assertionIndex) => (
      assertionIndex === index ? { ...assertion, ...updates } : assertion
    )));
  }

  function changeBuilderAssertionType(index: number, type: string) {
    setBuilderAssertions((current) => current.map((assertion, assertionIndex) => (
      assertionIndex === index ? { ...defaultBuilderAssertion(type), id: assertion.id } : assertion
    )));
  }

  function addBuilderAssertion(type: string) {
    setBuilderAssertions((current) => [...current, defaultBuilderAssertion(type)]);
  }

  function removeBuilderAssertion(index: number) {
    setBuilderAssertions((current) => current.length === 1 ? current : current.filter((_, assertionIndex) => assertionIndex !== index));
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

  async function refreshLifecycle() {
    const data = await api("/app/lifecycle/status");
    setLifecycle(data || null);
    setMessage("App lifecycle refreshed.");
  }

  async function installLaunchAgent() {
    await api("/app/lifecycle/launch-agent/install", {
      method: "POST",
      body: JSON.stringify({ dry_run: false }),
    });
    setMessage("Launch agent installed for this checkout.");
    await refreshLifecycle();
  }

  async function uninstallLaunchAgent() {
    await api("/app/lifecycle/launch-agent/uninstall", {
      method: "POST",
      body: JSON.stringify({ unload: true, dry_run: false }),
    });
    setMessage("Launch agent removed.");
    await refreshLifecycle();
  }

  async function restartJarvis() {
    if (!window.confirm("Restart JARVIS now? Active voice, workflow, and socket sessions will briefly disconnect.")) {
      return;
    }
    const data = await api("/app/lifecycle/restart", {
      method: "POST",
      body: JSON.stringify({ mode: lifecycle?.runtime.mode || "full", dry_run: false }),
    });
    setMessage(data.message || "JARVIS restart scheduled.");
  }

  async function quitJarvis() {
    if (!window.confirm("Quit JARVIS now? You will need to relaunch it from the desktop or terminal.")) {
      return;
    }
    const data = await api("/app/lifecycle/quit", {
      method: "POST",
      body: JSON.stringify({ dry_run: false, force_after_seconds: 8 }),
    });
    setMessage(data.message || "JARVIS quit scheduled.");
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
                    <div className="grid grid-cols-2 gap-2 mt-3">
                      <button
                        className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                        onClick={() => createFromTemplate(template.id)}
                      >
                        Create
                      </button>
                      <button
                        className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                        onClick={() => exportTemplatePackage(template.id)}
                      >
                        Package
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="jarvis-card">
              <div className="flex items-center justify-between gap-3 mb-3">
                <div className="jarvis-card-header mb-0">Workflow Packages</div>
                <button
                  className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md disabled:opacity-40"
                  disabled={!workflowPackageText.trim()}
                  onClick={importWorkflowPackage}
                >
                  Import Package
                </button>
              </div>
              <textarea
                className="jarvis-input min-h-36 resize-y font-mono text-2xs"
                value={workflowPackageText}
                onChange={(event) => setWorkflowPackageText(event.target.value)}
                placeholder='{"schema":"jarvis.workflow.package",...}'
              />
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
              {editingWorkflowId && (
                <div className="mb-3 rounded-md border border-jarvis-cyan/10 bg-jarvis-cyan/[0.025] px-3 py-2">
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div className="text-2xs text-jarvis-text-dim/55 font-mono">
                      base v{editingBaseVersion || 1}
                      {editingSession?.id ? ` · session ${editingSession.id.slice(0, 8)}` : ""}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(workflowPresence?.active_editors || []).length === 0 ? (
                        <span className="jarvis-badge">solo edit</span>
                      ) : workflowPresence?.active_editors?.map((editor) => (
                        <span key={editor.id} className="jarvis-badge">
                          {editor.actor_name || editor.actor_id}{editor.id === editingSession?.id ? " · you" : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                  {workflowPresence?.has_conflict && workflowPresence.other_editors?.[0] && (
                    <div className="text-2xs text-yellow-200/70 mt-2">
                      {workflowPresence.other_editors[0].actor_name || workflowPresence.other_editors[0].actor_id} is editing this workflow too.
                    </div>
                  )}
                </div>
              )}
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
                  <div className="grid grid-cols-3 gap-2 rounded-md border border-white/[0.04] bg-white/[0.015] p-3">
                    <label className="block">
                      <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Run $</span>
                      <input
                        className="jarvis-input mt-1"
                        type="number"
                        min={0}
                        step="0.0001"
                        value={budgetPerRun}
                        onChange={(event) => setBudgetPerRun(event.target.value)}
                      />
                    </label>
                    <label className="block">
                      <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Day $</span>
                      <input
                        className="jarvis-input mt-1"
                        type="number"
                        min={0}
                        step="0.001"
                        value={budgetPerDay}
                        onChange={(event) => setBudgetPerDay(event.target.value)}
                      />
                    </label>
                    <label className="block">
                      <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Month $</span>
                      <input
                        className="jarvis-input mt-1"
                        type="number"
                        min={0}
                        step="0.01"
                        value={budgetPerMonth}
                        onChange={(event) => setBudgetPerMonth(event.target.value)}
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
                  <div className="rounded-md border border-jarvis-cyan/10 bg-jarvis-cyan/[0.025] p-3 space-y-3">
                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="text-xs text-jarvis-text/70 uppercase tracking-wider">Release Assertions</div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {["output_contains", "output_not_contains", "action_status_equals", "max_duration_ms", "no_approval_required"].map((type) => (
                          <button
                            key={type}
                            className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-2 py-2 rounded-md"
                            onClick={() => addBuilderAssertion(type)}
                          >
                            + {type.replaceAll("_", " ")}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-3">
                      {builderAssertions.map((assertion, index) => (
                        <AssertionFields
                          key={assertion.id || index}
                          assertion={assertion}
                          index={index}
                          actions={builderActions}
                          updateAssertion={updateBuilderAssertion}
                          changeAssertionType={changeBuilderAssertionType}
                          removeAssertion={removeBuilderAssertion}
                        />
                      ))}
                    </div>
                  </div>
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
                          {workflow.active_release_channel && <span className="jarvis-badge">{workflow.active_release_channel} pinned</span>}
                          {workflow.budget?.max_cost_per_run_usd && <span className="jarvis-badge">run {formatCost(workflow.budget.max_cost_per_run_usd)}</span>}
                          {!workflow.enabled && <span className="jarvis-badge">disabled</span>}
                        </div>
                        <p className="text-xs text-jarvis-text-dim/55 mt-1 max-w-2xl">{workflow.description || workflow.actions?.[0]?.prompt}</p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => { void loadWorkflowIntoBuilder(workflow); }}>
                          Edit
                        </button>
                        <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => loadWorkflowVersions(workflow)}>
                          History
                        </button>
                        <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => exportWorkflowPackage(workflow)}>
                          Export
                        </button>
                        <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => runWorkflow(workflow.id, true)}>
                          Dry Run
                        </button>
                        {workflow.active_release_channel && (
                          <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => runWorkflow(workflow.id, true, "")}>
                            Draft Dry
                          </button>
                        )}
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
                  ) : workflowVersions.map((version) => {
                    const readiness = version.release_readiness;
                    const assertionResult = readiness?.evidence?.assertion_result;
                    const costBudget = readiness?.evidence?.cost_budget;
                    const dryRunCost = costBudget?.actual?.cost_usd ?? readiness?.evidence?.dry_run?.cost?.cost_usd;
                    const readinessLabel = readiness?.ready
                      ? "ready"
                      : readiness?.status === "missing_dry_run"
                        ? "needs dry run"
                        : readiness?.status === "over_budget"
                          ? "over budget"
                          : "blocked";
                    return (
                      <div key={version.id} className="rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3">
                        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs text-jarvis-text/70">Version {version.version}</span>
                              <span className="jarvis-badge">{version.event}</span>
                              <span className="jarvis-badge">{readinessLabel}</span>
                              {assertionResult && (
                                <span className="jarvis-badge">
                                  tests {assertionResult.passed_count}/{assertionResult.total}
                                </span>
                              )}
                              {typeof dryRunCost === "number" && (
                                <span className="jarvis-badge">cost {formatCost(dryRunCost)}</span>
                              )}
                              <span className="text-2xs text-jarvis-text-dim/45 font-mono">
                                {new Date(version.created_at * 1000).toLocaleString()}
                              </span>
                            </div>
                            <div className="text-2xs text-jarvis-text-dim/45 mt-1">
                              {version.actor_id || "local-owner"}
                              {version.changed_fields?.length ? ` · ${version.changed_fields.join(", ")}` : ""}
                              {version.note ? ` · ${version.note}` : ""}
                            </div>
                            {readiness?.evidence?.dry_run_id && (
                              <div className="text-2xs text-jarvis-text-dim/45 mt-1">
                                dry run {readiness.evidence.dry_run_id.slice(0, 8)}
                              </div>
                            )}
                            {assertionResult && !assertionResult.passed && assertionResult.assertions?.find((item) => !item.passed)?.message && (
                              <div className="text-2xs text-jarvis-text-dim/45 mt-1">
                                {assertionResult.assertions.find((item) => !item.passed)?.message}
                              </div>
                            )}
                            {!readiness?.ready && readiness?.blockers?.[0] && (
                              <div className="text-2xs text-jarvis-text-dim/45 mt-1">
                                {readiness.blockers[0]}
                              </div>
                            )}
                            {costBudget?.blockers?.[0] && readiness?.ready && (
                              <div className="text-2xs text-jarvis-text-dim/45 mt-1">
                                {costBudget.blockers[0]}
                              </div>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center gap-2 shrink-0">
                            <button
                              className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                              onClick={() => dryRunWorkflowVersion(version.workflow_id, version.id)}
                            >
                              Test
                            </button>
                            <button
                              className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md disabled:opacity-40"
                              disabled={!readiness?.evidence?.dry_run_id}
                              onClick={() => runAssertionSuite(version.workflow_id, version.id)}
                            >
                              Assert
                            </button>
                            <button
                              className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                              onClick={() => { if (version.snapshot) void loadWorkflowIntoBuilder(version.snapshot as Workflow); }}
                            >
                              Load
                            </button>
                            <button
                              className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md disabled:opacity-40"
                              disabled={!readiness?.ready}
                              onClick={() => publishWorkflowVersion(version.workflow_id, version.id)}
                            >
                              Promote
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
                    );
                  })}
                </div>
              </section>
            )}

            <section className="jarvis-card">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-3">
                <div className="jarvis-card-header mb-0">Run Analytics</div>
                <span className="jarvis-badge">{runAnalytics?.total_runs || 0} indexed</span>
              </div>
              <div className="grid grid-cols-2 lg:grid-cols-6 gap-2">
                <MetricTile label="Success" value={formatPercent(runAnalytics?.success_rate)} />
                <MetricTile label="Failure" value={formatPercent(runAnalytics?.failure_rate)} />
                <MetricTile label="Avg Run" value={formatDuration(runAnalytics?.avg_duration_ms)} />
                <MetricTile label="P95 Run" value={formatDuration(runAnalytics?.p95_duration_ms)} />
                <MetricTile label="Spend" value={formatCost(runAnalytics?.total_cost_usd)} />
                <MetricTile label="Avg Cost" value={formatCost(runAnalytics?.avg_cost_usd)} />
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-3">
                <div className="rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3">
                  <div className="text-2xs uppercase tracking-wider text-jarvis-text-dim/45 mb-2">Status Mix</div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(runAnalytics?.status_counts || {}).length === 0 ? (
                      <span className="text-xs text-jarvis-text-dim/45">No runs yet.</span>
                    ) : Object.entries(runAnalytics?.status_counts || {}).map(([status, count]) => (
                      <span key={status} className="jarvis-badge">{status}: {count}</span>
                    ))}
                    <span className="jarvis-badge">dry: {runAnalytics?.dry_runs || 0}</span>
                    <span className="jarvis-badge">live: {runAnalytics?.live_runs || 0}</span>
                  </div>
                </div>
                <div className="rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3">
                  <div className="text-2xs uppercase tracking-wider text-jarvis-text-dim/45 mb-2">Recent Errors</div>
                  <div className="space-y-2">
                    {(runAnalytics?.recent_errors || []).length === 0 ? (
                      <span className="text-xs text-jarvis-text-dim/45">No recent workflow errors.</span>
                    ) : runAnalytics?.recent_errors?.slice(0, 3).map((error) => (
                      <button
                        key={error.run_id}
                        className="block w-full text-left rounded-md border border-white/[0.04] bg-black/20 px-2 py-2"
                        onClick={() => inspectRun(error.run_id)}
                      >
                        <div className="text-xs text-jarvis-text/65">{error.workflow_name}</div>
                        <div className="text-2xs text-jarvis-text-dim/45 break-words">{error.status} · {error.error}</div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {(runAnalytics?.action_stats || []).length > 0 && (
                <div className="mt-3 rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3">
                  <div className="text-2xs uppercase tracking-wider text-jarvis-text-dim/45 mb-2">Action Health</div>
                  <div className="space-y-1">
                    {runAnalytics?.action_stats?.slice(0, 4).map((action) => (
                      <div key={`${action.type}-${action.title}`} className="flex items-center justify-between gap-3 text-2xs">
                        <span className="text-jarvis-text/60 truncate">{action.title || action.type}</span>
                        <span className="text-jarvis-text-dim/45 shrink-0">
                          {action.failed} failed · {action.skipped} skipped · {formatDuration(action.avg_duration_ms)} · {formatCost(action.avg_cost_usd)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="jarvis-card">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-3">
                <div className="jarvis-card-header mb-0">Recent Runs</div>
                <div className="flex flex-wrap gap-2">
                  <select
                    className="jarvis-input w-32"
                    value={runModeFilter}
                    onChange={(event) => setRunModeFilter(event.target.value)}
                  >
                    <option value="all">All modes</option>
                    <option value="dry">Dry</option>
                    <option value="live">Live</option>
                  </select>
                  <select
                    className="jarvis-input w-40"
                    value={runStatusFilter}
                    onChange={(event) => setRunStatusFilter(event.target.value)}
                  >
                    <option value="">All statuses</option>
                    <option value="completed">Completed</option>
                    <option value="completed_with_errors">With errors</option>
                    <option value="failed">Failed</option>
                  </select>
                </div>
              </div>
              <div className="space-y-2">
                {runs.length === 0 ? (
                  <p className="text-sm text-jarvis-text-dim/45">No workflow runs yet.</p>
                ) : runs.map((run) => (
                  <div key={run.id} className="flex items-center justify-between gap-3 rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-2">
                    <div>
                      <div className="text-xs text-jarvis-text/70">{run.workflow_name}</div>
                      <div className="text-2xs text-jarvis-text-dim/45 font-mono">
                        {run.triggered_by} · {run.dry_run ? "dry" : "live"} · v{run.workflow_version || 1}{run.release_channel ? ` · ${run.release_channel}` : ""} · {formatCost(run.cost?.cost_usd)} · {new Date(run.started_at * 1000).toLocaleString()}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => inspectRun(run.id)}>
                        Inspect
                      </button>
                      <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => replayRun(run.id, true)}>
                        Replay
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
                        {selectedRun.triggered_by} · {selectedRun.dry_run ? "dry" : "live"} · v{selectedRun.workflow_version || 1}{selectedRun.release_channel ? ` · ${selectedRun.release_channel}` : ""} · {formatDuration(selectedRun.duration_ms)} · {formatCost(selectedRun.cost?.cost_usd)}
                      </div>
                      {selectedRun.replay?.source_run_id && (
                        <div className="text-2xs text-jarvis-text-dim/45 font-mono mt-1">
                          replayed from {selectedRun.replay.source_run_id.slice(0, 8)} via {selectedRun.replay.strategy || "workflow"}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => replayRun(selectedRun.id, true)}>
                        Replay Dry
                      </button>
                      <button className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={() => replayRun(selectedRun.id, false)}>
                        Replay Live
                      </button>
                      <span className="jarvis-badge">{selectedRun.status}</span>
                    </div>
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
              <div className="flex items-center justify-between gap-3 mb-3">
                <div className="jarvis-card-header mb-0">App Lifecycle</div>
                <span className={`status-dot ${lifecycle?.status === "online" ? "connected" : "disconnected"}`} />
              </div>
              <div className="space-y-2">
                <PolicyRow label="Mode" value={lifecycle?.runtime.mode || "unknown"} />
                <PolicyRow label="Runtime" value={lifecycle?.runtime.status || "unknown"} />
                <PolicyRow label="Wrapper" value={lifecycle?.runtime.launcher_running ? "running" : "not tracked"} />
                <PolicyRow label="API" value={lifecycle?.ports.api ? `:${lifecycle.ports.api}` : "unknown"} />
                <PolicyRow label="UI" value={lifecycle?.ports.ui ? `:${lifecycle.ports.ui}` : "unknown"} />
                <PolicyRow label="App Bundle" value={lifecycle?.app_bundles?.some((item) => item.installed) ? "installed" : "missing"} />
                <PolicyRow label="Launch Agent" value={lifecycle?.launch_agent.installed ? (lifecycle.launch_agent.loaded ? "loaded" : "installed") : "not installed"} />
                <PolicyRow label="Started" value={formatTimestamp(lifecycle?.runtime.started_at)} />
              </div>
              <div className="mt-3 rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-2 space-y-1">
                {["backend", "ui", "overlay", "tunnel"].map((name) => {
                  const process = lifecycle?.processes?.[name];
                  return (
                    <div key={name} className="flex items-center justify-between gap-3 text-2xs">
                      <span className="text-jarvis-text-dim/45 capitalize">{name}</span>
                      <span className="font-mono text-jarvis-text/55">
                        {process?.running ? `pid ${process.pid}` : "offline"}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div className="grid grid-cols-2 gap-2 mt-3">
                <button className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={refreshLifecycle}>
                  Refresh
                </button>
                <button
                  className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md"
                  onClick={lifecycle?.launch_agent.installed ? uninstallLaunchAgent : installLaunchAgent}
                >
                  {lifecycle?.launch_agent.installed ? "Remove Agent" : "Install Agent"}
                </button>
                <button
                  className="jarvis-btn-ghost text-2xs uppercase tracking-wider px-3 py-2 rounded-md disabled:opacity-40"
                  disabled={lifecycle?.controls?.can_restart === false}
                  onClick={restartJarvis}
                >
                  Restart
                </button>
                <button className="jarvis-btn-primary text-2xs uppercase tracking-wider px-3 py-2 rounded-md" onClick={quitJarvis}>
                  Quit
                </button>
              </div>
            </section>

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
                        {approval.action?.type === "publish_workflow_version" && (
                          <div className="text-2xs text-jarvis-text-dim/45 mt-1">
                            v{approval.action.version || "?"} · {approval.action.channel || "stable"} · {approval.action.requested_by || "local-owner"}
                            {approval.action.dry_run_id ? ` · dry ${approval.action.dry_run_id.slice(0, 8)}` : ""}
                          </div>
                        )}
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
