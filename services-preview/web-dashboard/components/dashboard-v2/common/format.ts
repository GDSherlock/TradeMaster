export function formatCompactNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) {
    return "--";
  }
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(digits)}B`;
  }
  if (abs >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(digits)}M`;
  }
  if (abs >= 1_000) {
    return `${(value / 1_000).toFixed(digits)}K`;
  }
  return value.toFixed(digits);
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) {
    return "--";
  }
  return `${value.toFixed(digits)}%`;
}

export function formatProbability(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return "--";
  }
  return `${Math.round(value * 100)}%`;
}

export function formatDateTime(value: string | number | null | undefined): string {
  if (value == null || value === "") {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function formatClock(value: string | number | null | undefined): string {
  if (value == null || value === "") {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

export function directionTone(direction: string): "long" | "short" | "neutral" {
  const normalized = direction.toLowerCase();
  if (normalized.includes("long") || normalized.includes("bull")) {
    return "long";
  }
  if (normalized.includes("short") || normalized.includes("bear")) {
    return "short";
  }
  return "neutral";
}
