import type { WorkflowTimelineEntry } from "./types";
import { formatDuration, formatCost, formatTraceValue } from "./format";

export function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/[0.04] bg-white/[0.015] px-3 py-3">
      <div className="text-2xs uppercase tracking-wider text-jarvis-text-dim/45">{label}</div>
      <div className="text-lg text-jarvis-text/75 font-mono mt-1">{value}</div>
    </div>
  );
}

export function TimelineEntryView({ entry, index }: { entry: WorkflowTimelineEntry; index: number }) {
  const output = entry.output || {};
  const input = entry.input || {};
  const outputText = output.response || output.message || output.error || "none";
  const stepCost = entry.cost?.cost_usd ?? output.cost?.cost_usd;
  return (
    <div className="rounded-md border border-white/[0.05] bg-white/[0.02] px-3 py-3 space-y-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <span className="jarvis-badge">Step {index + 1}</span>
          <span className="text-sm text-jarvis-text/75">{entry.title || entry.type}</span>
          <span className="text-2xs text-jarvis-text-dim/45">{entry.type.replaceAll("_", " ")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xs font-mono text-jarvis-text-dim/45">{formatCost(stepCost)}</span>
          <span className="text-2xs font-mono text-jarvis-text-dim/45">{formatDuration(entry.duration_ms)}</span>
          <span className="jarvis-badge">{entry.status}</span>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <TraceRow label="Input" value={input.prompt || input.message || input.provider || input.mailbox || input.condition || input.type} />
        <TraceRow label="Output" value={outputText} />
      </div>
      {entry.attempts && entry.attempts.length > 0 && (
        <div className="space-y-1">
          {entry.attempts.map((attempt) => (
            <div key={attempt.attempt} className="flex items-center justify-between gap-3 rounded-md border border-white/[0.04] bg-black/20 px-2 py-1">
              <span className="text-2xs text-jarvis-text/60">Attempt {attempt.attempt}</span>
              <span className="text-2xs text-jarvis-text-dim/45">{attempt.error || attempt.status} · {formatDuration(attempt.duration_ms)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TraceRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded-md border border-white/[0.04] bg-black/20 px-2 py-2">
      <div className="text-2xs text-jarvis-text-dim/45 uppercase tracking-wider">{label}</div>
      <div className="text-xs text-jarvis-text/60 mt-1 break-words">{formatTraceValue(value)}</div>
    </div>
  );
}

export function PolicyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-2xs text-jarvis-text-dim/45">{label}</span>
      <span className="text-2xs font-mono text-jarvis-text/55 tabular-nums">{value}</span>
    </div>
  );
}
