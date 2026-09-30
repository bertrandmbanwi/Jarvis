import type { WorkflowAction, WorkflowAssertion, Workflow, CalendarState } from "./types";

export const emptyCalendar: CalendarState = {
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

export const defaultBuilderAction = (type: string, id = `${type}-${Date.now()}-${Math.random().toString(16).slice(2)}`): WorkflowAction => {
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

export const defaultBuilderAssertion = (
  type: string,
  id = `assert-${type}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
): WorkflowAssertion => {
  if (type === "output_contains") {
    return { id, type, title: "Output contains", value: "prepared", enabled: true };
  }
  if (type === "output_not_contains") {
    return { id, type, title: "Output omits error", value: "error", enabled: true };
  }
  if (type === "action_status_equals") {
    return { id, type, title: "Action status", action_id: "", expected_status: "prepared", enabled: true };
  }
  if (type === "max_duration_ms") {
    return { id, type, title: "Max duration", max_duration_ms: 30000, enabled: true };
  }
  if (type === "no_approval_required") {
    return { id, type, title: "No approval gates", enabled: true };
  }
  return { id, type: "run_status_equals", title: "Run completed", expected_status: "completed", enabled: true };
};
