"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { ProactiveSuggestion, ProactiveCategory } from "@/lib/types";

interface ProactiveToastProps {
  suggestions: ProactiveSuggestion[];
  onDismiss: (id: string) => void;
}

const DISMISS_DELAYS: Record<number, number> = {
  0: 8000,
  1: 12000,
  2: 18000,
};

const CATEGORY_CONFIG: Record<ProactiveCategory, {
  icon: string[];
  accentClass: string;
  glowColor: string;
  label: string;
}> = {
  calendar: {
    icon: [
      "M8 2v4", "M16 2v4",
      "M3 10h18",
      "M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
    ],
    accentClass: "text-jarvis-cyan",
    glowColor: "rgba(0,212,255,0.15)",
    label: "Calendar",
  },
  email: {
    icon: [
      "M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z",
      "M22 6l-10 7L2 6",
    ],
    accentClass: "text-blue-400",
    glowColor: "rgba(96,165,250,0.15)",
    label: "Email",
  },
  greeting: {
    icon: [
      "M12 2L2 7l10 5 10-5-10-5z",
      "M2 17l10 5 10-5",
      "M2 12l10 5 10-5",
    ],
    accentClass: "text-jarvis-gold",
    glowColor: "rgba(255,215,0,0.12)",
    label: "Briefing",
  },
  reminder: {
    icon: [
      "M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9",
      "M13.73 21a2 2 0 0 1-3.46 0",
    ],
    accentClass: "text-amber-400",
    glowColor: "rgba(251,191,36,0.12)",
    label: "Reminder",
  },
};

function ToastItem({
  suggestion,
  onDismiss,
}: {
  suggestion: ProactiveSuggestion;
  onDismiss: (id: string) => void;
}) {
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const config = CATEGORY_CONFIG[suggestion.category] || CATEGORY_CONFIG.reminder;
  const dismissDelay = DISMISS_DELAYS[suggestion.priority] || DISMISS_DELAYS[1];

  const handleDismiss = useCallback(() => {
    setExiting(true);
    setTimeout(() => onDismiss(suggestion.id), 300);
  }, [onDismiss, suggestion.id]);

  useEffect(() => {
    const enterTimer = setTimeout(() => setVisible(true), 20);
    return () => clearTimeout(enterTimer);
  }, []);

  useEffect(() => {
    timerRef.current = setTimeout(handleDismiss, dismissDelay);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [dismissDelay, handleDismiss]);

  return (
    <div
      className={`
        relative w-80 max-w-[calc(100vw-2rem)]
        transition-all duration-300 ease-out
        ${visible && !exiting
          ? "opacity-100 translate-x-0"
          : "opacity-0 translate-x-8"
        }
      `}
      role="status"
      aria-live="polite"
    >
      <div
        className="
          relative overflow-hidden
          bg-jarvis-surface/90 backdrop-blur-xl
          border border-white/[0.06] rounded-xl
          shadow-lg
          p-3.5
          transition-all duration-200
          hover:border-white/[0.1]
          group
        "
        style={{
          boxShadow: `0 4px 24px ${config.glowColor}, 0 1px 3px rgba(0,0,0,0.3)`,
        }}
      >
        <div
          className={`absolute top-0 left-0 right-0 h-[2px] ${config.accentClass}`}
          style={{
            background: `linear-gradient(90deg, transparent, ${config.glowColor.replace("0.1", "0.6")}, transparent)`,
          }}
        />

        <div className="flex items-start gap-3">
          <div
            className={`
              flex-shrink-0 w-8 h-8 rounded-lg
              flex items-center justify-center
              ${config.accentClass} bg-white/[0.04]
              border border-white/[0.06]
            `}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {config.icon.map((d, i) => (
                <path key={i} d={d} />
              ))}
            </svg>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 mb-1">
              <span className={`text-3xs font-medium uppercase tracking-[0.12em] ${config.accentClass}/70`}>
                {config.label}
              </span>
              {suggestion.priority >= 2 && (
                <span className="text-3xs font-mono text-amber-400/60 uppercase">
                  urgent
                </span>
              )}
            </div>
            <p className="text-xs text-jarvis-text/70 leading-relaxed line-clamp-3">
              {suggestion.message}
            </p>
          </div>

          <button
            onClick={handleDismiss}
            className="
              flex-shrink-0 w-6 h-6 rounded-md
              flex items-center justify-center
              text-jarvis-text-dim/25 hover:text-jarvis-text-dim/60
              hover:bg-white/[0.05]
              transition-all duration-150
              opacity-0 group-hover:opacity-100
              focus:opacity-100 focus:outline-none focus:ring-1 focus:ring-jarvis-cyan/20
            "
            aria-label="Dismiss notification"
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18" />
              <path d="M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-white/[0.03]">
          <div
            className={`h-full ${config.accentClass}/30 rounded-full`}
            style={{
              animation: `toast-progress ${dismissDelay}ms linear forwards`,
              background: config.glowColor.replace("0.1", "0.4"),
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default function ProactiveToast({ suggestions, onDismiss }: ProactiveToastProps) {
  const visible = suggestions.filter((s) => !s.dismissed).slice(0, 3);

  if (visible.length === 0) return null;

  return (
    <>
      <style jsx global>{`
        @keyframes toast-progress {
          from { width: 100%; }
          to { width: 0%; }
        }
      `}</style>

      <div
        className="fixed top-16 right-4 z-50 flex flex-col gap-2.5 pointer-events-auto"
        aria-label="Notifications"
      >
        {visible.map((suggestion) => (
          <ToastItem
            key={suggestion.id}
            suggestion={suggestion}
            onDismiss={onDismiss}
          />
        ))}
      </div>
    </>
  );
}
