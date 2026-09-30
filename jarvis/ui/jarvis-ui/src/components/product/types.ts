export interface WorkflowCondition {
  type: string;
  action_id?: string;
  value?: string;
}

export interface WorkflowAction {
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

export interface WorkflowAssertion {
  id?: string;
  type: string;
  title: string;
  enabled?: boolean;
  action_id?: string;
  value?: string;
  expected_status?: string;
  max_duration_ms?: number;
  system?: boolean;
}

export interface WorkflowBudget {
  max_cost_per_run_usd?: number;
  max_cost_per_day_usd?: number;
  max_cost_per_month_usd?: number;
  enforce_on_release?: boolean;
}

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  tags?: string[];
}

export interface WorkflowPackage {
  schema: string;
  schema_version: number;
  kind: string;
  id?: string;
  name?: string;
  description?: string;
  tags?: string[];
  workflow?: Partial<Workflow>;
  source?: Record<string, unknown>;
}

export interface Workflow {
  id: string;
  version?: number;
  name: string;
  description: string;
  trigger: { type: string; rrule?: string; minutes_before?: number };
  actions: WorkflowAction[];
  assertions?: WorkflowAssertion[];
  budget?: WorkflowBudget;
  enabled: boolean;
  tags?: string[];
  visibility?: string;
  active_release_channel?: string;
  last_run_at?: number | null;
}

export interface WorkflowVersion {
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
  release_readiness?: ReleaseReadiness;
  created_at: number;
}

export interface ReleaseReadiness {
  ready: boolean;
  status: string;
  blockers?: string[];
  evidence?: {
    dry_run_id?: string;
    dry_run?: {
      id?: string;
      status?: string;
      started_at?: number;
      completed_at?: number;
      duration_ms?: number;
      cost?: WorkflowCost;
    } | null;
    assertion_result?: WorkflowAssertionResult | null;
    cost_budget?: {
      status: string;
      ready: boolean;
      budget?: WorkflowBudget;
      actual?: WorkflowCost & {
        daily_cost_usd?: number;
        monthly_cost_usd?: number;
      };
      blockers?: string[];
    };
  };
}

export interface WorkflowAssertionResult {
  id?: string;
  workflow_id?: string;
  workflow_version_id?: string;
  run_id?: string;
  status: string;
  passed: boolean;
  total: number;
  passed_count: number;
  failed_count: number;
  assertions: Array<{
    id: string;
    type: string;
    title: string;
    action_id?: string;
    passed: boolean;
    status: string;
    expected?: unknown;
    actual?: unknown;
    message?: string;
    system?: boolean;
  }>;
  created_at?: number;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow_name: string;
  workflow_version?: number;
  workflow_version_id?: string;
  release_channel?: string;
  status: string;
  triggered_by: string;
  dry_run: boolean;
  started_at: number;
  completed_at?: number;
  duration_ms?: number;
  cost?: WorkflowCost;
  error?: string;
  replayed_from_run_id?: string;
  replay?: {
    source_run_id?: string;
    source_started_at?: number;
    source_status?: string;
    strategy?: string;
    dry_run?: boolean;
  };
  action_results?: Array<{ title?: string; status?: string; response?: string; message?: string; error?: string; approval_id?: string; cost?: WorkflowCost }>;
  timeline?: WorkflowTimelineEntry[];
}

export interface WorkflowCost {
  cost_usd?: number;
  request_count?: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cache_creation_tokens?: number;
}

export interface WorkflowEditSession {
  id: string;
  workflow_id: string;
  workflow_name?: string;
  workflow_version?: number;
  actor_id: string;
  actor_name?: string;
  status: string;
  started_at: number;
  updated_at: number;
  expires_at: number;
}

export interface WorkflowPresence {
  workflow_id: string;
  active_editors: WorkflowEditSession[];
  other_editors: WorkflowEditSession[];
  current_session?: WorkflowEditSession | null;
  has_conflict: boolean;
  updated_at: number;
}

export interface WorkflowTimelineAttempt {
  attempt: number;
  status: string;
  error?: string;
  started_at: number;
  completed_at: number;
  duration_ms: number;
}

export interface WorkflowTimelineEntry {
  id: string;
  action_id?: string;
  type: string;
  title: string;
  status: string;
  started_at: number;
  completed_at: number;
  duration_ms: number;
  input?: Record<string, unknown>;
  output?: Record<string, unknown> & { cost?: WorkflowCost };
  cost?: WorkflowCost;
  attempts?: WorkflowTimelineAttempt[];
}

export interface WorkflowAnalytics {
  total_runs: number;
  dry_runs: number;
  live_runs: number;
  status_counts: Record<string, number>;
  success_rate: number;
  failure_rate: number;
  avg_duration_ms: number;
  p95_duration_ms: number;
  total_cost_usd: number;
  avg_cost_usd: number;
  p95_cost_usd: number;
  recent_errors?: Array<{
    run_id: string;
    workflow_id: string;
    workflow_name: string;
    status: string;
    error: string;
    started_at: number;
  }>;
  workflow_stats?: Array<{
    workflow_id: string;
    workflow_name: string;
    total_runs: number;
    failed_runs: number;
    completed_runs: number;
    total_cost_usd?: number;
    avg_cost_usd?: number;
    last_run_at: number;
  }>;
  action_stats?: Array<{
    type: string;
    title: string;
    total: number;
    failed: number;
    skipped: number;
    approval_required: number;
    avg_duration_ms: number;
    total_cost_usd?: number;
    avg_cost_usd?: number;
  }>;
}

export interface WorkflowApproval {
  id: string;
  workflow_name: string;
  title: string;
  action_type: string;
  message: string;
  action?: {
    type?: string;
    channel?: string;
    version?: number;
    dry_run_id?: string;
    requested_by?: string;
  };
  status: string;
  response?: string;
  created_at: number;
}

export interface TeamMember {
  id: string;
  name: string;
  email: string;
  role: string;
  status: string;
}

export interface CalendarConnection {
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

export interface CalendarState {
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

export interface SchedulerStatus {
  enabled: boolean;
  scheduled_count: number;
  due_count: number;
}

export interface LifecycleProcess {
  pid?: number | null;
  running: boolean;
}

export interface AppLifecycleStatus {
  status: string;
  platform: string;
  is_macos: boolean;
  jarvis_home: string;
  runtime: {
    status: string;
    mode?: string;
    started_at?: number | null;
    updated_at?: number | null;
    age_seconds?: number | null;
    launcher_running?: boolean;
    state_file_exists?: boolean;
  };
  ports: { api: number; ui: number };
  processes: Record<string, LifecycleProcess>;
  app_bundles: Array<{ scope: string; path: string; installed: boolean }>;
  launch_agent: {
    label: string;
    path: string;
    installed: boolean;
    loaded: boolean;
  };
  controls?: {
    can_quit: boolean;
    can_restart: boolean;
    restart_strategy: string;
  };
}

export interface CalendarPreviewEvent {
  id?: string;
  title?: string;
  start?: string;
  location?: string;
}
