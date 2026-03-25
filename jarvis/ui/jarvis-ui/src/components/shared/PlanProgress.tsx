"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { PlanState, PlanSubtask } from "@/lib/types";

interface PlanProgressProps {
  plan: PlanState | null;
  onCollapse?: () => void;
}

const AGENT_BADGES: Record<string, { label: string; color: string; icon: string }> = {
  planner:  { label: "Plan",    color: "text-jarvis-cyan",   icon: "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2M9 5h6" },
  browser:  { label: "Browser", color: "text-blue-400",      icon: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" },
  coder:    { label: "Code",    color: "text-green-400",     icon: "M16 18l6-6-6-6M8 6l-6 6 6 6" },
  system:   { label: "System",  color: "text-amber-400",     icon: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" },
  default:  { label: "Agent",   color: "text-jarvis-text-dim", icon: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z" },
};

function getAgentBadge(agentType?: string) {
  if (!agentType) return AGENT_BADGES.default;
  const key = agentType.toLowerCase();
  return AGENT_BADGES[key] || AGENT_BADGES.default;
}

function StatusIcon({ status }: { status: PlanSubtask["status"] }) {
  const baseClass = "w-4 h-4 flex-shrink-0 transition-all duration-300";

  switch (status) {
    case "completed":
      return (
        <div className={`${baseClass} text-green-400`}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6L9 17l-5-5" className="animate-draw-check" />
          </svg>
        </div>
      );
    case "running":
      return (
        <div className={`${baseClass} text-jarvis-cyan`}>
          <div className="w-4 h-4 rounded-full border-2 border-jarvis-cyan/30 border-t-jarvis-cyan animate-spin" />
        </div>
      );
    case "failed":
      return (
        <div className={`${baseClass} text-red-400`}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </div>
      );
    case "skipped":
      return (
        <div className={`${baseClass} text-jarvis-text-dim/30`}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M5 12h14" />
          </svg>
        </div>
      );
    default:
      // pending
      return (
        <div className={`${baseClass} text-jarvis-text-dim/20`}>
          <div className="w-3.5 h-3.5 rounded-full border border-jarvis-text-dim/15 ml-[1px] mt-[1px]" />
        </div>
      );
  }
}

export default function PlanProgress({ plan, onCollapse }: PlanProgressProps) {
  const [collapsed, setCollapsed] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (collapsed || !listRef.current || !plan) return;
    const activeIdx = plan.subtasks.findIndex((s) => s.status === "running");
    if (activeIdx >= 0) {
      const items = listRef.current.querySelectorAll("[data-subtask]");
      items[activeIdx]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [plan?.subtasks, collapsed]);

  const handleToggle = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  if (!plan || !plan.isActive) return null;

  const progress = plan.total > 0 ? (plan.completed / plan.total) * 100 : 0;

  if (collapsed) {
    return (
      <button
        onClick={handleToggle}
        className="
          fixed bottom-20 left-1/2 -translate-x-1/2 z-40
          bg-jarvis-surface/90 backdrop-blur-xl
          border border-white/[0.06] rounded-full
          px-4 py-2 flex items-center gap-3
          shadow-lg
          transition-all duration-200
          hover:border-jarvis-cyan/20
          focus:outline-none focus:ring-1 focus:ring-jarvis-cyan/20
        "
        style={{ boxShadow: "0 4px 20px rgba(0,212,255,0.08)" }}
        aria-label="Expand plan progress"
      >
        <div className="w-3 h-3 rounded-full border-2 border-jarvis-cyan/30 border-t-jarvis-cyan animate-spin" />

        <span className="text-2xs font-mono text-jarvis-text-dim/60">
          {plan.completed}/{plan.total}
        </span>

        <div className="w-20 h-1 bg-white/[0.06] rounded-full overflow-hidden">
          <div
            className="h-full bg-jarvis-cyan/50 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-jarvis-text-dim/30">
          <path d="M18 15l-6-6-6 6" />
        </svg>
      </button>
    );
  }

  return (
    <div
      className="
        fixed bottom-20 left-1/2 -translate-x-1/2 z-40
        w-96 max-w-[calc(100vw-2rem)]
        bg-jarvis-surface/95 backdrop-blur-xl
        border border-white/[0.06] rounded-xl
        shadow-lg overflow-hidden
        animate-fade-in
      "
      style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.3), 0 4px 16px rgba(0,212,255,0.06)" }}
    >
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.04]">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-5 h-5 rounded-md bg-jarvis-cyan/8 flex items-center justify-center">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-jarvis-cyan/60">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <path d="M22 4L12 14.01l-3-3" />
            </svg>
          </div>

          <div className="min-w-0">
            <div className="text-3xs text-jarvis-text-dim/40 uppercase tracking-[0.1em] font-medium">
              Active Plan
            </div>
            <div className="text-xs text-jarvis-text/65 truncate" title={plan.goal}>
              {plan.goal}
            </div>
          </div>
        </div>

        <button
          onClick={handleToggle}
          className="
            w-6 h-6 rounded-md flex items-center justify-center
            text-jarvis-text-dim/25 hover:text-jarvis-text-dim/50
            hover:bg-white/[0.05]
            transition-all duration-150
            focus:outline-none focus:ring-1 focus:ring-jarvis-cyan/20
          "
          aria-label="Collapse plan progress"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
      </div>

      <div className="px-4 pt-2.5 pb-1.5">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-3xs text-jarvis-text-dim/35 font-mono">
            Progress
          </span>
          <span className="text-3xs text-jarvis-cyan/60 font-mono tabular-nums">
            {plan.completed}/{plan.total}
          </span>
        </div>
        <div className="h-1.5 bg-white/[0.04] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700 ease-out"
            style={{
              width: `${progress}%`,
              background: "linear-gradient(90deg, rgba(0,212,255,0.5), rgba(0,212,255,0.7))",
              boxShadow: "0 0 8px rgba(0,212,255,0.3)",
            }}
          />
        </div>
      </div>

      <div
        ref={listRef}
        className="px-4 py-2 max-h-52 overflow-y-auto jarvis-scrollbar space-y-0.5"
      >
        {plan.subtasks.map((subtask, idx) => {
          const badge = getAgentBadge(subtask.agent_type);
          const isActive = subtask.status === "running";
          const isDone = subtask.status === "completed";

          return (
            <div
              key={subtask.id}
              data-subtask={subtask.id}
              className={`
                flex items-start gap-2.5 py-1.5 px-2 rounded-lg
                transition-all duration-300
                ${isActive ? "bg-jarvis-cyan/[0.04]" : ""}
                ${isDone ? "opacity-60" : ""}
              `}
            >
              <div className="mt-0.5">
                <StatusIcon status={subtask.status} />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`text-xs leading-snug ${
                      isActive
                        ? "text-jarvis-text/80"
                        : isDone
                          ? "text-jarvis-text/50 line-through decoration-white/10"
                          : "text-jarvis-text/55"
                    }`}
                  >
                    {subtask.title}
                  </span>
                </div>

                {subtask.agent_type && (
                  <div className="flex items-center gap-1 mt-0.5">
                    <svg
                      width="9"
                      height="9"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className={`${badge.color}/50`}
                    >
                      <path d={badge.icon} />
                    </svg>
                    <span className={`text-3xs font-mono ${badge.color}/40`}>
                      {badge.label}
                    </span>
                  </div>
                )}
              </div>

              <span className="text-3xs font-mono text-jarvis-text-dim/20 mt-0.5 tabular-nums">
                {idx + 1}
              </span>
            </div>
          );
        })}
      </div>

      <div className="px-4 py-2 border-t border-white/[0.03]">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-jarvis-cyan/40 animate-pulse" />
          <span className="text-3xs text-jarvis-text-dim/30 font-mono">
            Executing...
          </span>
        </div>
      </div>
    </div>
  );
}
