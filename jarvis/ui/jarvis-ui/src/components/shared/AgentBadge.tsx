"use client";

interface AgentBadgeProps {
  agentType?: string;
  tierUsed?: string;
}

const AGENT_CONFIG: Record<string, {
  label: string;
  colorClass: string;
  bgClass: string;
  borderClass: string;
  iconPath: string;
}> = {
  planner: {
    label: "Planner",
    colorClass: "text-jarvis-cyan/60",
    bgClass: "bg-jarvis-cyan/6",
    borderClass: "border-jarvis-cyan/10",
    iconPath: "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2",
  },
  browser: {
    label: "Browser",
    colorClass: "text-blue-400/60",
    bgClass: "bg-blue-400/6",
    borderClass: "border-blue-400/10",
    iconPath: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20",
  },
  coder: {
    label: "Coder",
    colorClass: "text-green-400/60",
    bgClass: "bg-green-400/6",
    borderClass: "border-green-400/10",
    iconPath: "M16 18l6-6-6-6M8 6l-6 6 6 6",
  },
  system: {
    label: "System",
    colorClass: "text-amber-400/60",
    bgClass: "bg-amber-400/6",
    borderClass: "border-amber-400/10",
    iconPath: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  },
  executor: {
    label: "Executor",
    colorClass: "text-purple-400/60",
    bgClass: "bg-purple-400/6",
    borderClass: "border-purple-400/10",
    iconPath: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  },
};

const TIER_CONFIG: Record<string, {
  label: string;
  colorClass: string;
  bgClass: string;
  borderClass: string;
  iconPath: string;
}> = {
  fast: {
    label: "Fast",
    colorClass: "text-green-400/50",
    bgClass: "bg-green-400/5",
    borderClass: "border-green-400/8",
    iconPath: "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  },
  brain: {
    label: "Brain",
    colorClass: "text-jarvis-cyan/50",
    bgClass: "bg-jarvis-cyan/5",
    borderClass: "border-jarvis-cyan/8",
    iconPath: "M12 2a8 8 0 0 0-8 8c0 3.4 2.1 6.3 5 7.5V20h6v-2.5c2.9-1.2 5-4.1 5-7.5a8 8 0 0 0-8-8zM10 22h4",
  },
  deep: {
    label: "Deep",
    colorClass: "text-jarvis-gold/50",
    bgClass: "bg-jarvis-gold/5",
    borderClass: "border-jarvis-gold/8",
    iconPath: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  },
};

export default function AgentBadge({ agentType, tierUsed }: AgentBadgeProps) {
  let config = null;

  if (agentType) {
    const key = agentType.toLowerCase();
    config = AGENT_CONFIG[key];
  }

  if (!config && tierUsed) {
    const key = tierUsed.toLowerCase();
    config = TIER_CONFIG[key];
  }

  if (!config) return null;

  return (
    <span
      className={`
        inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md
        ${config.bgClass} ${config.borderClass} border
        transition-colors duration-200
      `}
      title={`Handled by: ${config.label}`}
    >
      <svg
        width="8"
        height="8"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={config.colorClass}
      >
        <path d={config.iconPath} />
      </svg>
      <span className={`text-3xs font-mono ${config.colorClass}`}>
        {config.label}
      </span>
    </span>
  );
}
