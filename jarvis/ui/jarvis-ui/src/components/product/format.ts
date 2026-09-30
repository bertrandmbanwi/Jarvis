export function formatDuration(value?: number) {
  if (typeof value !== "number") return "0 ms";
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.max(0, Math.round(value))} ms`;
}

export function formatPercent(value?: number) {
  if (typeof value !== "number") return "0%";
  return `${Math.round(value * 100)}%`;
}

export function formatCost(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value) || value <= 0) return "$0";
  return value < 0.01 ? `$${value.toFixed(6)}` : `$${value.toFixed(4)}`;
}

export function formatTimestamp(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value) || value <= 0) return "unknown";
  return new Date(value * 1000).toLocaleString();
}

export function formatTraceValue(value: unknown) {
  if (value === undefined || value === null || value === "") return "none";
  if (typeof value === "string") return value.length > 180 ? `${value.slice(0, 180)}...` : value;
  try {
    const text = JSON.stringify(value);
    return text.length > 180 ? `${text.slice(0, 180)}...` : text;
  } catch {
    return String(value);
  }
}
