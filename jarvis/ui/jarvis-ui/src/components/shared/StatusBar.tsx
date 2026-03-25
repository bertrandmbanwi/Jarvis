"use client";

import { ViewMode, ConnectionStatus } from "@/lib/types";

interface StatusBarProps {
  viewMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  connectionStatus: ConnectionStatus;
  sessionCost?: number;
}

const statusLabels: Record<ConnectionStatus, string> = {
  connected: "Online",
  connecting: "Connecting",
  disconnected: "Offline",
  error: "Error",
};

const tabs: { mode: ViewMode; label: string; iconPaths: string[] }[] = [
  {
    mode: "cinematic",
    label: "Voice",
    iconPaths: [
      "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z",
      "M12 6a6 6 0 1 0 0 12 6 6 0 0 0 0-12z",
    ],
  },
  {
    mode: "chat",
    label: "Chat",
    iconPaths: [
      "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
    ],
  },
  {
    mode: "dashboard",
    label: "System",
    iconPaths: [
      "M3 3h7v7H3z",
      "M14 3h7v7h-7z",
      "M3 14h7v7H3z",
      "M14 14h7v7h-7z",
    ],
  },
];

export default function StatusBar({
  viewMode,
  onModeChange,
  connectionStatus,
  sessionCost = 0.0,
}: StatusBarProps) {
  return (
    <div className="w-full bg-jarvis-surface/80 backdrop-blur-xl border-b border-white/[0.04] px-3 sm:px-6 py-2 sm:py-2.5 flex-shrink-0">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="w-1.5 h-1.5 rounded-full bg-jarvis-cyan/60 hidden sm:block"
               style={{ boxShadow: '0 0 6px rgba(0,212,255,0.4)' }} />
          <span className="text-sm sm:text-base font-semibold jarvis-glow-subtle tracking-[0.18em] sm:tracking-[0.25em]">
            J.A.R.V.I.S.
          </span>
          <span className="text-3xs text-jarvis-text-dim/30 font-mono hidden sm:inline">
            v0.2.0
          </span>
        </div>

        <div className="flex items-center gap-2 sm:gap-4">
          <div className="flex items-center gap-1.5 sm:gap-2">
            <div className={`status-dot ${connectionStatus}`} />
            <span className="text-3xs sm:text-2xs text-jarvis-text-dim/60 font-mono hidden sm:inline">
              {statusLabels[connectionStatus]}
            </span>
          </div>

          <div className="flex items-center jarvis-glass-subtle p-0.5 gap-0.5">
            {tabs.map(({ mode, label, iconPaths }) => {
              const isActive = viewMode === mode;
              return (
                <button
                  key={mode}
                  onClick={() => onModeChange(mode)}
                  className={`
                    relative flex items-center gap-1.5 px-2.5 sm:px-3.5 py-1.5 rounded-lg
                    transition-all duration-200 ease-out
                    text-2xs font-medium uppercase tracking-[0.08em]
                    ${isActive
                      ? "bg-jarvis-cyan/10 text-jarvis-cyan border border-jarvis-cyan/15"
                      : "text-jarvis-text-dim/40 hover:text-jarvis-text-dim/70 hover:bg-white/[0.03] border border-transparent"
                    }
                  `}
                  aria-label={label}
                  >
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`transition-opacity duration-200 ${isActive ? 'opacity-100' : 'opacity-60'}`}
                  >
                    {iconPaths.map((d, i) => (
                      <path key={i} d={d} />
                    ))}
                  </svg>
                  <span className="hidden sm:inline">{label}</span>
                  {isActive && (
                    <span className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-3 h-[2px] rounded-full bg-jarvis-cyan/50" />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        <div className="text-right hidden sm:flex flex-col items-end">
          <div className="text-3xs text-jarvis-text-dim/35 uppercase tracking-[0.12em]">
            Session
          </div>
          <div className="text-sm font-mono text-jarvis-cyan/70 tabular-nums">
            ${sessionCost.toFixed(4)}
          </div>
        </div>

        <div className="sm:hidden">
          <div className="text-2xs font-mono text-jarvis-cyan/50 tabular-nums">
            ${sessionCost.toFixed(2)}
          </div>
        </div>
      </div>
    </div>
  );
}
