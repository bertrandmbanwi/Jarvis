"use client";

import { useCallback, useEffect } from "react";
import { PendingConfirmation } from "@/lib/types";

interface ConfirmationModalProps {
  confirmations: PendingConfirmation[];
  onRespond: (id: string, approved: boolean) => void;
}

const RISK_CONFIG: Record<string, { label: string; accent: string; glow: string }> = {
  critical: { label: "Critical", accent: "text-red-400", glow: "rgba(248,113,113,0.18)" },
  high: { label: "High risk", accent: "text-amber-400", glow: "rgba(251,191,36,0.16)" },
  medium: { label: "Review", accent: "text-jarvis-cyan", glow: "rgba(0,212,255,0.14)" },
};

export default function ConfirmationModal({ confirmations, onRespond }: ConfirmationModalProps) {
  const current = confirmations[0] ?? null;

  const deny = useCallback(() => {
    if (current) onRespond(current.id, false);
  }, [current, onRespond]);

  useEffect(() => {
    if (!current) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") deny();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, deny]);

  if (!current) return null;

  const config = RISK_CONFIG[current.risk] || RISK_CONFIG.medium;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      <div
        className="relative w-full max-w-md overflow-hidden bg-jarvis-surface/95 backdrop-blur-xl border border-white/[0.08] rounded-2xl shadow-2xl p-6"
        style={{ boxShadow: `0 8px 40px ${config.glow}, 0 2px 8px rgba(0,0,0,0.4)` }}
      >
        <div
          className="absolute top-0 left-0 right-0 h-[2px]"
          style={{ background: `linear-gradient(90deg, transparent, ${config.glow.replace("0.1", "0.6")}, transparent)` }}
        />

        <div className="flex items-center gap-2 mb-3">
          <span className={`text-3xs font-medium uppercase tracking-[0.14em] ${config.accent}`}>
            {config.label}
          </span>
          <span className="text-3xs font-mono text-jarvis-text-dim/50 uppercase tracking-wider">
            confirmation required
          </span>
        </div>

        <h2 id="confirm-title" className="text-sm font-medium text-jarvis-text mb-2">
          Approve this action?
        </h2>

        <p className="text-xs text-jarvis-text/70 leading-relaxed mb-1 font-mono break-words">
          {current.tool}
        </p>
        <p className="text-xs text-jarvis-text-dim/70 leading-relaxed mb-5 break-words">
          {current.summary}
        </p>

        <div className="flex gap-2.5">
          <button
            onClick={() => onRespond(current.id, true)}
            className="flex-1 py-2.5 rounded-lg text-xs font-medium text-jarvis-bg bg-jarvis-cyan hover:bg-jarvis-cyan/90 transition-colors focus:outline-none focus:ring-2 focus:ring-jarvis-cyan/40"
          >
            Approve
          </button>
          <button
            onClick={deny}
            className="flex-1 py-2.5 rounded-lg text-xs font-medium text-jarvis-text/80 bg-white/[0.05] hover:bg-white/[0.08] border border-white/[0.06] transition-colors focus:outline-none focus:ring-2 focus:ring-white/10"
          >
            Deny
          </button>
        </div>

        {confirmations.length > 1 && (
          <p className="mt-3 text-3xs text-jarvis-text-dim/40 text-center">
            {confirmations.length - 1} more pending
          </p>
        )}
      </div>
    </div>
  );
}
