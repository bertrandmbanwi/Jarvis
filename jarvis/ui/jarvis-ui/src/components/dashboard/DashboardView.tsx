"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { ChatMessage, CostInsights, CostSummary, ProductFoundationStatus, ServerStatus } from "@/lib/types";
import { getApiBaseUrl, jarvisHeaders } from "@/lib/apiBase";
import AgentBadge from "@/components/shared/AgentBadge";

interface DashboardViewProps {
  messages: ChatMessage[];
  costSummary: CostSummary | null;
  serverStatus: ServerStatus | null;
  isProcessing: boolean;
  onClearConversation: () => void;
  authToken?: string | null;
  userName?: string;
}

export default function DashboardView({
  messages,
  costSummary,
  serverStatus,
  isProcessing,
  onClearConversation,
  authToken,
  userName = "You",
}: DashboardViewProps) {
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const [costInsights, setCostInsights] = useState<CostInsights | null>(null);
  const [productStatus, setProductStatus] = useState<ProductFoundationStatus | null>(null);

  const loadCostInsights = useCallback(async () => {
    try {
      const response = await fetch(`${getApiBaseUrl()}/costs`, {
        headers: jarvisHeaders(authToken),
      });
      if (!response.ok) return;
      const data = await response.json();
      setCostInsights({
        cacheHitRatio: data.insights?.cache_hit_ratio || 0,
        cacheReadTokens: data.insights?.cache_read_tokens || 0,
        cacheWriteTokens: data.insights?.cache_write_tokens || 0,
        byTierCostUsd: data.insights?.by_tier_cost_usd || {},
        recommendations: data.insights?.recommendations || [],
        budget: {
          dailyAlertUsd: data.insights?.budget?.daily_alert_usd || 0,
          dailyHardLimitUsd: data.insights?.budget?.daily_hard_limit_usd || 0,
          monthlyAlertUsd: data.insights?.budget?.monthly_alert_usd || 0,
          monthlyHardLimitUsd: data.insights?.budget?.monthly_hard_limit_usd || 0,
          costMode: data.insights?.budget?.cost_mode || "balanced",
        },
        hardLimits: {
          blocked: Boolean(data.hard_limits?.blocked),
          dailyBlocked: Boolean(data.hard_limits?.daily_blocked),
          monthlyBlocked: Boolean(data.hard_limits?.monthly_blocked),
        },
        today: {
          totalCostUsd: data.today?.total_cost_usd || 0,
          totalRequests: data.today?.total_requests || 0,
        },
        month: {
          totalCostUsd: data.month?.total_cost_usd || 0,
          projectedMonthlyUsd: data.month?.projected_monthly_usd || 0,
        },
      });
    } catch {
      // Dashboard metrics are optional; keep the activity log usable.
    }
  }, [authToken]);

  const loadProductStatus = useCallback(async () => {
    try {
      const headers = jarvisHeaders(authToken);
      const [workflowResponse, teamResponse, calendarResponse] = await Promise.all([
        fetch(`${getApiBaseUrl()}/workflows/overview`, { headers }),
        fetch(`${getApiBaseUrl()}/team`, { headers }),
        fetch(`${getApiBaseUrl()}/calendar/connections`, { headers }),
      ]);
      if (!workflowResponse.ok || !teamResponse.ok || !calendarResponse.ok) return;
      const [workflowData, teamData, calendarData] = await Promise.all([
        workflowResponse.json(),
        teamResponse.json(),
        calendarResponse.json(),
      ]);
      const connections = Array.isArray(calendarData.connections) ? calendarData.connections : [];
      const providers = calendarData.providers || {};
      setProductStatus({
        workflows: {
          workflowCount: workflowData.workflow_count || 0,
          enabledCount: workflowData.enabled_count || 0,
          templateCount: workflowData.template_count || 0,
          recentRunCount: Array.isArray(workflowData.recent_runs) ? workflowData.recent_runs.length : 0,
        },
        team: {
          mode: teamData.mode || "single_user",
          memberCount: Array.isArray(teamData.members) ? teamData.members.length : 0,
        },
        calendar: {
          connectedCount: connections.filter((item: { enabled?: boolean; status?: string }) => (
            item.enabled && item.status === "connected"
          )).length,
          providerCount: Object.keys(providers).length,
          conflictStrategy: calendarData.policy?.conflict_strategy || "ask",
          autoCreateEvents: Boolean(calendarData.policy?.auto_create_events),
        },
      });
    } catch {
      // Product foundation data is additive; dashboard core should keep working.
    }
  }, [authToken]);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTo({
        top: chatScrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages]);

  useEffect(() => {
    loadCostInsights();
    const interval = setInterval(loadCostInsights, 15000);
    return () => clearInterval(interval);
  }, [loadCostInsights]);

  useEffect(() => {
    loadProductStatus();
    const interval = setInterval(loadProductStatus, 30000);
    return () => clearInterval(interval);
  }, [loadProductStatus]);

  const visibleMessages = messages.filter(
    (msg) => msg.content || (msg.role === "assistant" && msg.isStreaming)
  );
  const memoryCount = serverStatus?.memoryStats?.count
    ?? serverStatus?.memoryStats?.vector_store?.count
    ?? 0;

  return (
    <div className="flex-1 dashboard-shell overflow-hidden p-4 sm:p-5">
      <div className="h-full min-h-0 flex flex-col lg:flex-row gap-4">
        <div className="flex-1 flex flex-col min-h-0 gap-4">
          <section className="dashboard-hero p-4 sm:p-5 flex-shrink-0">
            <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className={`status-dot ${serverStatus?.status === "ok" ? "connected" : isProcessing ? "connecting" : "connected"}`} />
                  <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-jarvis-text-dim/80">
                    Command center
                  </span>
                </div>
                <h2 className="text-xl sm:text-2xl font-semibold text-jarvis-text">
                  Systems overview
                </h2>
                <p className="text-sm text-jarvis-text-dim/78 mt-1">
                  Live activity, model routing, memory, product workflows, and cost posture.
                </p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 min-w-0 sm:min-w-[28rem]">
                <MetricTile label="Backend" value={serverStatus?.activeBackend || "..."} />
                <MetricTile label="Memory" value={`${memoryCount}`} />
                <MetricTile label="Turns" value={`${serverStatus?.conversationTurns || 0}`} />
                <MetricTile label="Cost" value={`$${(costSummary?.sessionCostUsd || 0).toFixed(3)}`} accent />
              </div>
            </div>
          </section>

          <section className="activity-feed flex-1 flex flex-col min-h-0 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.07] bg-black/18 backdrop-blur-lg">
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-semibold text-jarvis-text/82">
                  Activity log
                </h3>
                {visibleMessages.length > 0 && (
                  <span className="text-2xs text-jarvis-text-dim/65 font-mono tabular-nums">
                    {visibleMessages.length}
                  </span>
                )}
              </div>
              <button
                onClick={onClearConversation}
                className="jarvis-btn-ghost text-2xs px-3 py-1.5 rounded-md"
                aria-label="Clear activity log"
              >
                Clear
              </button>
            </div>

            <div
              ref={chatScrollRef}
              className="flex-1 overflow-y-auto px-4 sm:px-5 py-4 space-y-1 jarvis-scrollbar"
            >
              {visibleMessages.length === 0 ? (
                <div className="flex-1 flex items-center justify-center h-full">
                  <p className="text-sm text-jarvis-text-dim/72 font-medium">
                    No activity yet.
                  </p>
                </div>
              ) : (
                visibleMessages.map((msg) => {
                  const isUser = msg.role === "user";
                  return (
                    <div key={msg.id} className="animate-fade-in py-2">
                      <div className="flex items-start gap-3">
                        <div className={`
                            w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0
                            text-[10px] font-semibold mt-0.5
                            ${isUser
                              ? "bg-jarvis-cyan/12 text-jarvis-cyan/80 border border-jarvis-cyan/18"
                              : "bg-jarvis-gold/10 text-jarvis-gold/80 border border-jarvis-gold/18"
                            }
                          `}>
                          {isUser ? userName.slice(0, 1).toUpperCase() || "Y" : "J"}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs font-semibold text-jarvis-text/78">
                              {isUser ? userName : "Jarvis"}
                            </span>
                            {!isUser && (msg.agentType || msg.tierUsed) && (
                              <AgentBadge agentType={msg.agentType} tierUsed={msg.tierUsed} />
                            )}
                            <span className="text-2xs text-jarvis-text-dim/45 font-mono tabular-nums">
                              {new Date(msg.timestamp).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          </div>
                          <div className="text-[14px] text-jarvis-text/84 leading-relaxed whitespace-pre-wrap">
                            {msg.content || (
                              <span className="text-jarvis-text-dim/70 italic text-xs">
                                Processing...
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}

              {isProcessing && (
                <div className="flex items-center gap-2.5 text-jarvis-text-dim/72 text-xs pl-9 py-2 animate-fade-in">
                  <div className="typing-dots flex items-center">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <span className="text-2xs font-mono">Processing...</span>
                </div>
              )}
            </div>
          </section>
        </div>

        <aside className="hidden lg:flex w-80 flex-col overflow-y-auto jarvis-scrollbar">
        <div className="p-4 space-y-4">
          <div className="jarvis-card">
            <div className="jarvis-card-header flex items-center gap-2">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-jarvis-cyan/40">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              System
            </div>
            <div className="space-y-3">
              <InfoRow
                label="Backend"
                value={serverStatus?.activeBackend || "..."}
                highlight
              />
              <InfoRow
                label="Model"
                value={serverStatus?.activeModel?.split("-").slice(1, 3).join("-") || "..."}
              />
              <InfoRow
                label="Uptime"
                value={
                  serverStatus
                    ? formatUptime(serverStatus.uptimeSeconds)
                    : "..."
                }
              />
              <InfoRow
                label="Memory"
                value={
                  serverStatus
                    ? `${memoryCount} entries`
                    : "..."
                }
              />
              <InfoRow
                label="Turns"
                value={
                  serverStatus?.conversationTurns?.toString() || "0"
                }
              />
            </div>
          </div>

          <div className="jarvis-card">
            <div className="jarvis-card-header flex items-center gap-2">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-jarvis-cyan/40">
                <line x1="12" y1="1" x2="12" y2="23" />
                <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
              Session Cost
            </div>

            <div className="mb-4">
              <div className="text-2xl font-mono text-jarvis-cyan/75 tabular-nums tracking-tight">
                ${costSummary?.sessionCostUsd?.toFixed(4) || "0.0000"}
              </div>
            </div>

            <div className="jarvis-divider mb-3" />

            <div className="space-y-2.5">
              <InfoRow
                label="Requests"
                value={costSummary?.totalRequests?.toString() || "0"}
              />
              <InfoRow
                label="Input tokens"
                value={formatNumber(costSummary?.totalInputTokens || 0)}
              />
              <InfoRow
                label="Output tokens"
                value={formatNumber(costSummary?.totalOutputTokens || 0)}
              />
              <InfoRow
                label="Cache reads"
                value={formatNumber(costSummary?.cacheReadTokens || 0)}
              />
              <InfoRow
                label="Cache writes"
                value={formatNumber(costSummary?.cacheCreationTokens || 0)}
              />
            </div>
          </div>

          <div className="jarvis-card">
            <div className="jarvis-card-header flex items-center gap-2">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-jarvis-cyan/40">
                <path d="M3 12h18" />
                <path d="M12 3v18" />
                <path d="m5 5 14 14" />
                <path d="m19 5-14 14" />
              </svg>
              Cost Controls
            </div>
            <div className="space-y-2.5">
              <InfoRow
                label="Mode"
                value={costInsights?.budget.costMode || "balanced"}
                highlight={costInsights?.budget.costMode === "economy"}
              />
              <InfoRow
                label="Today"
                value={`$${(costInsights?.today?.totalCostUsd || 0).toFixed(4)}`}
              />
              <InfoRow
                label="Month"
                value={`$${(costInsights?.month?.totalCostUsd || 0).toFixed(2)}`}
              />
              <InfoRow
                label="Cache hit"
                value={`${Math.round((costInsights?.cacheHitRatio || 0) * 100)}%`}
                highlight={(costInsights?.cacheHitRatio || 0) >= 0.5}
              />
              {costInsights?.hardLimits?.blocked && (
                <div className="text-2xs text-red-300/80 border border-red-400/20 bg-red-500/5 rounded-md px-2 py-1.5">
                  Hard spend limit is active.
                </div>
              )}
            </div>
            {costInsights?.recommendations?.length ? (
              <div className="mt-3 pt-3 border-t border-white/[0.04] space-y-2">
                {costInsights.recommendations.slice(0, 2).map((rec) => (
                  <p key={rec} className="text-2xs leading-relaxed text-jarvis-text-dim/55">
                    {rec}
                  </p>
                ))}
              </div>
            ) : null}
          </div>

          <div className="jarvis-card">
            <div className="jarvis-card-header flex items-center gap-2">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-jarvis-cyan/40">
                <path d="M4 6h16" />
                <path d="M4 12h10" />
                <path d="M4 18h7" />
                <path d="M17 15l3 3 3-5" />
              </svg>
              Product Bets
            </div>
            <div className="space-y-2.5">
              <InfoRow
                label="Workflows"
                value={`${productStatus?.workflows.enabledCount || 0}/${productStatus?.workflows.workflowCount || 0}`}
                highlight={(productStatus?.workflows.workflowCount || 0) > 0}
              />
              <InfoRow
                label="Templates"
                value={`${productStatus?.workflows.templateCount || 0}`}
              />
              <InfoRow
                label="Team mode"
                value={productStatus?.team.mode || "single_user"}
                highlight={productStatus?.team.mode === "team"}
              />
              <InfoRow
                label="Members"
                value={`${productStatus?.team.memberCount || 1}`}
              />
              <InfoRow
                label="Calendars"
                value={`${productStatus?.calendar.connectedCount || 0}/${productStatus?.calendar.providerCount || 0}`}
                highlight={(productStatus?.calendar.connectedCount || 0) > 0}
              />
              <InfoRow
                label="Scheduling"
                value={productStatus?.calendar.autoCreateEvents ? "auto" : productStatus?.calendar.conflictStrategy || "ask"}
              />
            </div>
          </div>

          {costSummary?.requestsByTier && Object.values(costSummary.requestsByTier).some(c => c > 0) && (
            <div className="jarvis-card">
              <div className="jarvis-card-header flex items-center gap-2">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-jarvis-cyan/40">
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                </svg>
                By Tier
              </div>
              <div className="space-y-3">
                {Object.entries(costSummary.requestsByTier).map(
                  ([tier, count]) =>
                    count > 0 && (
                      <div key={tier} className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-2xs text-jarvis-text-dim/55 capitalize font-medium">
                            {tier}
                          </span>
                          <span className="text-2xs font-mono text-jarvis-text/55 tabular-nums">
                            {count}
                          </span>
                        </div>
                        <div className="h-1 bg-white/[0.04] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500 ease-out"
                            style={{
                              width: `${Math.min(
                                100,
                                (count / (costSummary.totalRequests || 1)) * 100
                              )}%`,
                              background: tier === 'fast'
                                ? 'rgba(0, 255, 136, 0.35)'
                                : tier === 'deep'
                                  ? 'rgba(255, 225, 140, 0.35)'
                                  : 'rgba(0, 212, 255, 0.35)',
                            }}
                          />
                        </div>
                      </div>
                    )
                )}
              </div>
            </div>
          )}
        </div>
        </aside>
      </div>
    </div>
  );
}

function InfoRow({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-2xs text-jarvis-text-dim/70">{label}</span>
      <span className={`text-2xs font-mono tabular-nums ${
        highlight ? 'text-jarvis-cyan/85' : 'text-jarvis-text/72'
      }`}>
        {value}
      </span>
    </div>
  );
}

function MetricTile({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="metric-tile px-3 py-2.5 min-w-0">
      <div className="text-[10px] text-jarvis-text-dim/68 font-medium">
        {label}
      </div>
      <div className={`mt-1 text-sm font-semibold truncate ${accent ? "text-jarvis-gold" : "text-jarvis-text/88"}`}>
        {value}
      </div>
    </div>
  );
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

function formatNumber(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toString();
}
