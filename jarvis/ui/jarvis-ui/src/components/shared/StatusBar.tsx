"use client";

import { ViewMode, ConnectionStatus } from "@/lib/types";

interface StatusBarProps {
  viewMode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  connectionStatus: ConnectionStatus;
  sessionCost?: number;
  version?: string;
  settingsOpen?: boolean;
  onSettingsClick?: () => void;
}

const statusLabels: Record<ConnectionStatus, string> = {
  connected: "Online",
  connecting: "Connecting",
  disconnected: "Offline",
  error: "Error",
};

const tabs: { mode: ViewMode; label: string; icon: "orb" | "chat" | "system" | "flows" }[] = [
  { mode: "cinematic", label: "Voice", icon: "orb" },
  { mode: "chat", label: "Chat", icon: "chat" },
  { mode: "dashboard", label: "Command", icon: "system" },
  { mode: "product", label: "Automations", icon: "flows" },
];

export default function StatusBar({
  viewMode,
  onModeChange,
  connectionStatus,
  sessionCost = 0.0,
  version = "0.3.0",
  settingsOpen = false,
  onSettingsClick,
}: StatusBarProps) {
  return (
    <div className="w-full jarvis-command-bar px-3 sm:px-5 py-2.5 flex-shrink-0">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="hidden sm:flex w-8 h-8 rounded-xl items-center justify-center border border-jarvis-cyan/20 bg-jarvis-cyan/10 text-jarvis-cyan/80"
            style={{ boxShadow: "0 0 22px rgba(0, 212, 255, 0.13)" }}
          >
            <Icon name="orb" />
          </div>
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-sm sm:text-base font-semibold jarvis-glow-subtle tracking-[0.18em]">
                Jarvis
              </span>
              <span className="text-3xs text-jarvis-text-dim/55 font-mono hidden sm:inline">
                v{version}
              </span>
            </div>
            <div className="hidden sm:flex items-center gap-2 mt-0.5">
              <span className={`status-dot ${connectionStatus}`} />
              <span className="text-[10px] text-jarvis-text-dim/75 font-medium">
                {statusLabels[connectionStatus]}
              </span>
            </div>
          </div>
        </div>

        <div className="jarvis-nav-shell flex items-center p-1 gap-1 justify-self-center">
          {tabs.map(({ mode, label, icon }) => {
            const isActive = viewMode === mode;
            return (
              <button
                key={mode}
                onClick={() => onModeChange(mode)}
                className={`
                  jarvis-nav-tab relative flex items-center gap-2 px-2.5 sm:px-4
                  transition-all duration-200 ease-out border text-2xs font-semibold
                  ${isActive
                    ? "jarvis-nav-tab-active text-jarvis-cyan"
                    : "text-jarvis-text-dim/70 border-transparent hover:text-jarvis-text hover:bg-white/[0.04]"
                  }
                `}
                aria-label={label}
              >
                <Icon name={icon} />
                <span className="hidden md:inline">{label}</span>
              </button>
            );
          })}
        </div>

        <div className="justify-self-end hidden sm:flex items-center gap-3">
          <div className="text-right">
            <div className="text-[10px] text-jarvis-text-dim/65 font-medium">
              Session cost
            </div>
            <div className="text-sm font-mono text-jarvis-cyan/85 tabular-nums">
              ${sessionCost.toFixed(4)}
            </div>
          </div>
          <button
            type="button"
            onClick={onSettingsClick}
            className={`quiet-icon-button ${settingsOpen ? "quiet-icon-button-active" : ""}`}
            aria-label={settingsOpen ? "Close settings" : "Open settings"}
            title={settingsOpen ? "Close settings" : "Settings"}
          >
            <Icon name="settings" />
          </button>
        </div>

        <div className="sm:hidden justify-self-end flex items-center gap-2">
          <span className={`status-dot ${connectionStatus}`} />
          <div className="text-2xs font-mono text-jarvis-cyan/80 tabular-nums">
            ${sessionCost.toFixed(2)}
          </div>
          <button
            type="button"
            onClick={onSettingsClick}
            className={`quiet-icon-button w-8 h-8 ${settingsOpen ? "quiet-icon-button-active" : ""}`}
            aria-label={settingsOpen ? "Close settings" : "Open settings"}
          >
            <Icon name="settings" />
          </button>
        </div>
      </div>
    </div>
  );
}

function Icon({ name }: { name: "orb" | "chat" | "system" | "flows" | "settings" }) {
  const common = {
    width: 15,
    height: 15,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (name === "chat") {
    return (
      <svg {...common}>
        <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
      </svg>
    );
  }

  if (name === "system") {
    return (
      <svg {...common}>
        <path d="M4 7h16" />
        <path d="M4 12h16" />
        <path d="M4 17h10" />
        <circle cx="18" cy="17" r="2" />
      </svg>
    );
  }

  if (name === "flows") {
    return (
      <svg {...common}>
        <path d="M6 4v6a2 2 0 0 0 2 2h8" />
        <path d="M18 8l4 4-4 4" />
        <path d="M6 20v-4" />
        <circle cx="6" cy="4" r="2" />
        <circle cx="6" cy="20" r="2" />
      </svg>
    );
  }

  if (name === "settings") {
    return (
      <svg {...common}>
        <path d="M4 7h16" />
        <path d="M7 12h10" />
        <path d="M10 17h4" />
        <circle cx="17" cy="7" r="1.8" />
        <circle cx="9" cy="12" r="1.8" />
        <circle cx="13" cy="17" r="1.8" />
      </svg>
    );
  }

  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
      <path d="M4 12h3" />
      <path d="M17 12h3" />
    </svg>
  );
}
