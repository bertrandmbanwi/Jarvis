"use client";

import { useCallback, useEffect } from "react";
import { ConfirmationDecision, PendingConfirmation } from "@/lib/types";

interface ConfirmationModalProps {
  confirmations: PendingConfirmation[];
  onRespond: (id: string, decision: ConfirmationDecision) => void;
}

const RISK_CONFIG: Record<string, { label: string; accent: string; glow: string }> = {
  critical: { label: "Risk: critical", accent: "text-red-400", glow: "rgba(248,113,113,0.18)" },
  high: { label: "Risk: high", accent: "text-amber-400", glow: "rgba(251,191,36,0.16)" },
  medium: { label: "Risk: medium", accent: "text-jarvis-cyan", glow: "rgba(0,212,255,0.14)" },
};

function targetText(current: PendingConfirmation): string {
  const targets = current.affected_targets || [];
  if (targets.length === 0) return "ไม่ระบุเป้าหมาย";
  if (targets.length === 1) return targets[0];
  return `${targets[0]} และอีก ${targets.length - 1} รายการ`;
}

export default function ConfirmationModal({ confirmations, onRespond }: ConfirmationModalProps) {
  const current = confirmations[0] ?? null;

  const respond = useCallback((decision: ConfirmationDecision) => {
    if (current) onRespond(current.id, decision);
  }, [current, onRespond]);

  const deny = useCallback(() => respond("deny"), [respond]);

  useEffect(() => {
    if (!current) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") deny();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, deny]);

  if (!current) return null;

  const risk = (current.risk || "medium").toLowerCase();
  const config = RISK_CONFIG[risk] || RISK_CONFIG.medium;
  const canApproveAlways = risk !== "critical" && (current.allowed_decisions || []).includes("confirm_always");

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      <div
        className="relative w-full max-w-lg overflow-hidden bg-jarvis-surface/95 backdrop-blur-xl border border-white/[0.08] rounded-2xl shadow-2xl p-6"
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
            MayAss permission policy
          </span>
        </div>

        <h2 id="confirm-title" className="text-sm font-medium text-jarvis-text mb-3">
          มายกำลังจะทำ action นี้ ต้องการให้บอสยืนยันก่อน
        </h2>

        <div className="space-y-2 text-xs text-jarvis-text/75 leading-relaxed mb-5">
          <p className="font-mono break-words">
            <span className="text-jarvis-text-dim/60">Action:</span> {current.action_type || current.tool}
          </p>
          <p className="break-words">
            <span className="text-jarvis-text-dim/60">สิ่งที่จะทำ:</span> {current.summary}
          </p>
          <p className="break-words">
            <span className="text-jarvis-text-dim/60">กระทบ:</span> {targetText(current)}
          </p>
          <p>
            <span className="text-jarvis-text-dim/60">ย้อนกลับได้ไหม:</span> {current.reversible ? "ได้" : "ไม่แน่ใจ/ไม่ได้"}
          </p>
          <p className="break-words">
            <span className="text-jarvis-text-dim/60">เหตุผล:</span> {current.reason || "ต้องการยืนยันจากบอสก่อน"}
          </p>
          <p className="break-words text-jarvis-text-dim/80">
            ถ้าไม่ยืนยัน: {current.consequence_if_denied || "มายจะไม่ทำ action นี้"}
          </p>
          {risk === "critical" && (
            <p className="text-red-300/90">
              Critical action ไม่สามารถยืนยันถาวรได้ ต้องยืนยันเป็นครั้ง ๆ เท่านั้น
            </p>
          )}
        </div>

        <div className="grid gap-2.5 sm:grid-cols-3">
          <button
            onClick={() => respond("confirm_once")}
            className="py-2.5 rounded-lg text-xs font-medium text-jarvis-bg bg-jarvis-cyan hover:bg-jarvis-cyan/90 transition-colors focus:outline-none focus:ring-2 focus:ring-jarvis-cyan/40"
          >
            ยืนยันครั้งนี้
          </button>
          <button
            onClick={() => respond("confirm_always")}
            disabled={!canApproveAlways}
            className="py-2.5 rounded-lg text-xs font-medium text-jarvis-text/80 bg-white/[0.07] hover:bg-white/[0.1] disabled:opacity-35 disabled:cursor-not-allowed border border-white/[0.06] transition-colors focus:outline-none focus:ring-2 focus:ring-white/10"
          >
            ยืนยันถาวรสำหรับงานแบบนี้
          </button>
          <button
            onClick={deny}
            className="py-2.5 rounded-lg text-xs font-medium text-jarvis-text/80 bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] transition-colors focus:outline-none focus:ring-2 focus:ring-white/10"
          >
            ไม่ยืนยัน
          </button>
        </div>

        {confirmations.length > 1 && (
          <p className="mt-3 text-3xs text-jarvis-text-dim/40 text-center">
            มีอีก {confirmations.length - 1} action รออยู่
          </p>
        )}
      </div>
    </div>
  );
}
