import type { WorkflowCondition, WorkflowAction, WorkflowAssertion, CalendarState } from "./types";

export function AssertionFields({
  assertion,
  index,
  actions,
  updateAssertion,
  changeAssertionType,
  removeAssertion,
}: {
  assertion: WorkflowAssertion;
  index: number;
  actions: WorkflowAction[];
  updateAssertion: (index: number, updates: Partial<WorkflowAssertion>) => void;
  changeAssertionType: (index: number, type: string) => void;
  removeAssertion: (index: number) => void;
}) {
  const needsValue = assertion.type === "output_contains" || assertion.type === "output_not_contains";
  const needsStatus = assertion.type === "run_status_equals" || assertion.type === "action_status_equals";
  const needsAction = assertion.type === "action_status_equals" || needsValue;
  const needsDuration = assertion.type === "max_duration_ms";

  return (
    <div className="rounded-md border border-white/[0.05] bg-black/20 p-3 space-y-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="jarvis-badge">Assert {index + 1}</span>
          <select className="jarvis-input max-w-64" value={assertion.type} onChange={(event) => changeAssertionType(index, event.target.value)}>
            <option value="run_status_equals">Run status</option>
            <option value="no_failed_steps">No failed steps</option>
            <option value="output_contains">Output contains</option>
            <option value="output_not_contains">Output omits</option>
            <option value="action_status_equals">Action status</option>
            <option value="max_duration_ms">Max duration</option>
            <option value="no_approval_required">No approvals</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-2xs text-jarvis-text-dim/55">
            <input
              type="checkbox"
              checked={assertion.enabled !== false}
              onChange={(event) => updateAssertion(index, { enabled: event.target.checked })}
            />
            Enabled
          </label>
          <button className="jarvis-btn-ghost text-2xs px-2 py-1 rounded-md" onClick={() => removeAssertion(index)}>
            Remove
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <label className="block">
          <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Title</span>
          <input className="jarvis-input mt-1" value={assertion.title} onChange={(event) => updateAssertion(index, { title: event.target.value })} />
        </label>
        {needsAction && (
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Action</span>
            <select className="jarvis-input mt-1" value={assertion.action_id || ""} onChange={(event) => updateAssertion(index, { action_id: event.target.value })}>
              <option value="">Any action</option>
              {actions.map((action, actionIndex) => (
                <option key={action.id || actionIndex} value={action.id || ""}>
                  {action.title || `Step ${actionIndex + 1}`}
                </option>
              ))}
            </select>
          </label>
        )}
        {needsStatus && (
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Expected Status</span>
            <select className="jarvis-input mt-1" value={assertion.expected_status || "completed"} onChange={(event) => updateAssertion(index, { expected_status: event.target.value })}>
              <option value="completed">Completed</option>
              <option value="prepared">Prepared</option>
              <option value="skipped">Skipped</option>
              <option value="approval_required">Approval required</option>
              <option value="failed">Failed</option>
            </select>
          </label>
        )}
        {needsValue && (
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Text</span>
            <input className="jarvis-input mt-1" value={assertion.value || ""} onChange={(event) => updateAssertion(index, { value: event.target.value })} />
          </label>
        )}
        {needsDuration && (
          <label className="block">
            <span className="text-2xs text-jarvis-text-dim/50 uppercase tracking-wider">Max Duration</span>
            <input
              className="jarvis-input mt-1"
              type="number"
              min={1}
              value={assertion.max_duration_ms || 30000}
              onChange={(event) => updateAssertion(index, { max_duration_ms: Number.parseInt(event.target.value, 10) || 30000 })}
            />
          </label>
        )}
      </div>
    </div>
  );
}

export function ActionFields({
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

export function ActionPolicyFields({
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
