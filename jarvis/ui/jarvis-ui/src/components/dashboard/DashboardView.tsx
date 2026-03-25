"use client";

import { useEffect, useRef } from "react";
import { ChatMessage, CostSummary, ServerStatus } from "@/lib/types";
import AgentBadge from "@/components/shared/AgentBadge";

interface DashboardViewProps {
  messages: ChatMessage[];
  costSummary: CostSummary | null;
  serverStatus: ServerStatus | null;
  isProcessing: boolean;
  onClearConversation: () => void;
}

export default function DashboardView({
  messages,
  costSummary,
  serverStatus,
  isProcessing,
  onClearConversation,
}: DashboardViewProps) {
  const chatScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTo({
        top: chatScrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages]);

  const visibleMessages = messages.filter(
    (msg) => msg.content || (msg.role === "assistant" && msg.isStreaming)
  );

  return (
    <div className="flex-1 flex flex-col sm:flex-row overflow-hidden">
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between px-5 py-2.5 border-b border-white/[0.04] bg-jarvis-surface/60 backdrop-blur-lg">
          <div className="flex items-center gap-2">
            <h2 className="text-2xs font-medium text-jarvis-text-dim/55 uppercase tracking-[0.12em]">
              Activity Log
            </h2>
            {visibleMessages.length > 0 && (
              <span className="text-3xs text-jarvis-text-dim/25 font-mono tabular-nums">
                {visibleMessages.length}
              </span>
            )}
          </div>
          <button
            onClick={onClearConversation}
            className="jarvis-btn-ghost text-3xs uppercase tracking-wider px-2 py-1 rounded-md"
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
              <p className="text-sm text-jarvis-text-dim/30 font-light">
                No activity yet. Use Voice or Chat to interact with JARVIS.
              </p>
            </div>
          ) : (
            visibleMessages.map((msg) => {
              const isUser = msg.role === "user";
              return (
                <div key={msg.id} className="animate-fade-in py-2">
                  <div className="flex items-start gap-3">
                    <div className={`
                        w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0
                        text-3xs font-semibold mt-0.5
                        ${isUser
                          ? "bg-jarvis-cyan/8 text-jarvis-cyan/50 border border-jarvis-cyan/10"
                          : "bg-white/[0.03] text-jarvis-text-dim/40 border border-white/[0.05]"
                        }
                      `}>
                      {isUser ? "B" : "J"}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-2xs font-medium text-jarvis-text-dim/50">
                          {isUser ? "Becs" : "JARVIS"}
                        </span>
                        {!isUser && (msg.agentType || msg.tierUsed) && (
                          <AgentBadge agentType={msg.agentType} tierUsed={msg.tierUsed} />
                        )}
                        <span className="text-3xs text-jarvis-text-dim/20 font-mono tabular-nums">
                          {new Date(msg.timestamp).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>
                      <div className="text-[13px] text-jarvis-text/70 leading-relaxed whitespace-pre-wrap">
                        {msg.content || (
                          <span className="text-jarvis-text-dim/40 italic text-xs">
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
            <div className="flex items-center gap-2.5 text-jarvis-text-dim/50 text-xs pl-9 py-2 animate-fade-in">
              <div className="typing-dots flex items-center">
                <span></span>
                <span></span>
                <span></span>
              </div>
              <span className="text-2xs font-mono">Processing...</span>
            </div>
          )}
        </div>
      </div>

      <div className="hidden sm:flex w-72 flex-col border-l border-white/[0.04] bg-jarvis-surface/40 backdrop-blur-lg overflow-y-auto jarvis-scrollbar">
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
                    ? `${serverStatus.memoryStats.count} entries`
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
      <span className="text-2xs text-jarvis-text-dim/45">{label}</span>
      <span className={`text-2xs font-mono tabular-nums ${
        highlight ? 'text-jarvis-cyan/60' : 'text-jarvis-text/55'
      }`}>
        {value}
      </span>
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
