export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export type ViewMode = "cinematic" | "chat" | "dashboard";

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

export interface ServerStatus {
  status: string;
  version: string;
  uptimeSeconds: number;
  activeBackend: string;
  activeModel: string;
  memoryStats: { backend: string; count: number };
  conversationTurns: number;
  sessionCost: CostSummary;
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
  error?: string;
}

export type OrbState = "idle" | "listening" | "thinking" | "speaking" | "error";
