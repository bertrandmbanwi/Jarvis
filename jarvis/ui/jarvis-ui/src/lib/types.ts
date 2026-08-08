export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export type ViewMode = "cinematic" | "chat" | "dashboard" | "product";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  tierUsed?: string;
  agentType?: string;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
}

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  result: string;
  timestamp: number;
}

export interface CostSummary {
  sessionCostUsd: number;
  totalRequests: number;
  requestsByTier: Record<string, number>;
  totalInputTokens: number;
  totalOutputTokens: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  activeBackend: string;
}

export interface LocalSavingsSummary {
  startedAt: number;
  uptimeSeconds: number;
  localRoutes: number;
  paidCallsAvoided: number;
  freeApiCalls: number;
  cacheHits: number;
  byAction: Record<string, number>;
  byProvider: Record<string, number>;
  lastEvent?: {
    action: string;
    toolName?: string;
    provider: string;
    cacheHit: boolean;
    timestamp: number;
  } | null;
}

export interface PublicDataProviderStatus {
  name: string;
  category: string;
  status: "ok" | "unavailable";
  latencyMs: number;
  error?: string;
}

export interface PublicDataStatus {
  checkedAt: number;
  cached: boolean;
  cacheTtlSeconds: number;
  healthyCount: number;
  degradedCount: number;
  providerCount: number;
  providers: PublicDataProviderStatus[];
}

export interface CostInsights {
  cacheHitRatio: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  byTierCostUsd: Record<string, number>;
  recommendations: string[];
  budget: {
    dailyAlertUsd: number;
    dailyHardLimitUsd: number;
    monthlyAlertUsd: number;
    monthlyHardLimitUsd: number;
    costMode: string;
  };
  hardLimits?: {
    blocked: boolean;
    dailyBlocked: boolean;
    monthlyBlocked: boolean;
  };
  today?: {
    totalCostUsd: number;
    totalRequests: number;
  };
  month?: {
    totalCostUsd: number;
    projectedMonthlyUsd: number;
  };
  savings?: LocalSavingsSummary;
}

export interface ProductFoundationStatus {
  workflows: {
    workflowCount: number;
    enabledCount: number;
    templateCount: number;
    recentRunCount: number;
  };
  team: {
    mode: string;
    memberCount: number;
  };
  calendar: {
    connectedCount: number;
    providerCount: number;
    conflictStrategy: string;
    autoCreateEvents: boolean;
  };
}

export interface ServerStatus {
  status: string;
  version: string;
  uptimeSeconds: number;
  activeBackend: string;
  activeModel: string;
  memoryStats: {
    backend?: string;
    count?: number;
    vector_store?: { backend: string; count: number | string };
    facts?: Record<string, unknown>;
    preferences?: Record<string, unknown>;
  };
  conversationTurns: number;
  sessionCost: CostSummary;
  localSavings?: LocalSavingsSummary;
}

export type ProactiveCategory = "calendar" | "email" | "greeting" | "reminder";

export interface ProactiveSuggestion {
  id: string;
  category: ProactiveCategory;
  message: string;
  priority: number;
  spoken: boolean;
  timestamp: number;
  dismissed?: boolean;
}

export type PlanEventType =
  | "plan_created"
  | "subtask_started"
  | "subtask_completed"
  | "subtask_failed"
  | "subtask_skipped"
  | "plan_completed";

export interface PlanSubtask {
  id: string;
  title: string;
  agent_type?: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  result?: string;
}

export interface PlanState {
  planId: string;
  goal: string;
  subtasks: PlanSubtask[];
  completed: number;
  total: number;
  isActive: boolean;
}

export interface ConnectedDevice {
  device_type: string;
  device_name: string;
  wants_audio: boolean;
  connected_at: number;
  last_activity: number;
  uptime_seconds: number;
}

export interface PendingConfirmation {
  id: string;
  tool: string;
  summary: string;
  risk: string;
  created_at: number;
  action_type?: string;
  affected_targets?: string[];
  reversible?: boolean;
  reason?: string;
  consequence_if_denied?: string;
  permanent_policy_key?: string;
  allowed_decisions?: ConfirmationDecision[];
}

export type ConfirmationDecision = "confirm_once" | "confirm_always" | "deny";

export interface WSMessage {
  token?: string;
  done?: boolean;
  full_response?: string;
  backend?: string;
  tier_used?: string;
  agent_type?: string;
  source?: string;
  voice_user_message?: string;
  voice_speaking?: boolean;
  voice_audio?: string;
  voice_stop?: boolean;
  audio_format?: string;
  voice_audio_chunk?: {
    audio: string;
    index: number;
    is_last: boolean;
    envelope: number[];
    duration: number;
    format?: string;
  };
  amplitude_envelope?: number[];
  audio_duration?: number;
  session_cost?: {
    session_cost_usd: number;
    total_requests: number;
    requests_by_tier: Record<string, number>;
    total_input_tokens: number;
    total_output_tokens: number;
    cache_read_tokens: number;
    cache_creation_tokens: number;
    active_backend: string;
  };
  local_savings?: {
    started_at: number;
    uptime_seconds: number;
    local_routes: number;
    paid_calls_avoided: number;
    free_api_calls: number;
    cache_hits: number;
    by_action: Record<string, number>;
    by_provider: Record<string, number>;
    last_event?: {
      action: string;
      tool_name?: string;
      provider: string;
      cache_hit: boolean;
      timestamp: number;
    } | null;
  };
  client_registered?: boolean;
  connected_devices?: ConnectedDevice[];
  audio_preference_updated?: boolean;
  wants_audio?: boolean;
  proactive_suggestion?: {
    category: ProactiveCategory;
    message: string;
    priority: number;
    spoken: boolean;
    timestamp: number;
  };
  plan_progress?: {
    event: PlanEventType;
    plan_id: string;
    goal?: string;
    subtask_id?: string;
    title?: string;
    agent_type?: string;
    result?: string;
    completed?: number;
    total?: number;
    subtasks?: Array<{ id: string; title: string; agent_type?: string }>;
  };
  type?: string;
  confirmation?: PendingConfirmation;
  error?: string;
}

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "error";
