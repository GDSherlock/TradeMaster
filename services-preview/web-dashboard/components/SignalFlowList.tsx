"use client";

import type { SignalEvent, SignalViewMode } from "@/types/legacy-dashboard";

type SignalFlowListProps = {
  events: SignalEvent[];
  mode: SignalViewMode;
  onModeChange: (mode: SignalViewMode) => void;
};

type SignalSummaryItem = {
  key: string;
  symbol: string;
  interval: string;
  count: number;
  latest: SignalEvent;
};

function buildSummary(events: SignalEvent[]): SignalSummaryItem[] {
  const map = new Map<string, SignalSummaryItem>();
  for (const event of events) {
    const key = `${event.symbol}:${event.interval}`;
    const current = map.get(key);
    if (!current) {
      map.set(key, {
        key,
        symbol: event.symbol,
        interval: event.interval,
        count: 1,
        latest: event
      });
      continue;
    }

    current.count += 1;
    if (event.id > current.latest.id) {
      current.latest = event;
    }
  }

  return [...map.values()].sort((a, b) => b.latest.id - a.latest.id);
}

function directionClass(direction: string): string {
  const normalized = direction.toLowerCase();
  if (normalized.includes("long") || normalized.includes("bull")) {
    return "up";
  }
  if (normalized.includes("short") || normalized.includes("bear")) {
    return "down";
  }
  return "flat";
}

function formatMlDecision(decision: string): string {
  switch (decision) {
    case "passed":
      return "ML Passed";
    case "review":
      return "ML Review";
    case "rejected":
      return "ML Rejected";
    case "unavailable":
      return "ML Offline";
    default:
      return "ML Pending";
  }
}

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return `${Math.round(value * 100)}%`;
}

export function SignalFlowList({ events, mode, onModeChange }: SignalFlowListProps) {
  const summary = buildSummary(events);

  return (
    <section className="legacy-card">
      <div className="legacy-card-head">
        <h2>Signal Flow</h2>
        <div className="legacy-mode-switch" role="tablist" aria-label="signal view">
          <button
            type="button"
            className={mode === "events" ? "active" : ""}
            onClick={() => onModeChange("events")}
            role="tab"
            aria-selected={mode === "events"}
          >
            Events
          </button>
          <button
            type="button"
            className={mode === "summary" ? "active" : ""}
            onClick={() => onModeChange("summary")}
            role="tab"
            aria-selected={mode === "summary"}
          >
            Summary
          </button>
        </div>
      </div>

      {mode === "events" ? (
        <ul className="legacy-list" aria-label="signal events">
          {events.length === 0 ? (
            <li className="legacy-empty">No signal events yet.</li>
          ) : (
            events.map((event) => (
              <li key={event.id} className="legacy-list-item">
                <div>
                  <p className="legacy-list-title">
                    {event.symbol} <span>{event.interval}</span>
                  </p>
                  <p className="legacy-list-meta">{event.ruleKey}</p>
                  <p className="legacy-list-detail">{event.detail || "No detail"}</p>
                  {event.mlValidation && (
                    <>
                      <p className="legacy-list-detail">
                        {formatMlDecision(event.mlValidation.decision)} · {formatPercent(event.mlValidation.probability)} · v
                        {event.mlValidation.modelVersion || "n/a"}
                      </p>
                      <p className="legacy-list-detail">
                        Threshold {formatPercent(event.mlValidation.threshold)} · {event.mlValidation.reason || "n/a"}
                      </p>
                      {event.mlValidation.topFeatures.length > 0 && (
                        <details className="legacy-ml-details">
                          <summary>Top Features</summary>
                          <ul>
                            {event.mlValidation.topFeatures.slice(0, 4).map((item) => (
                              <li key={`${event.id}-${item.name}`}>
                                <span>{item.name}</span>
                                <span>{item.value.toFixed(4)}</span>
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </>
                  )}
                </div>
                <div className={`legacy-pill ${directionClass(event.direction)}`}>{event.direction || "neutral"}</div>
              </li>
            ))
          )}
        </ul>
      ) : (
        <ul className="legacy-list" aria-label="signal summary">
          {summary.length === 0 ? (
            <li className="legacy-empty">No summary yet.</li>
          ) : (
            summary.map((item) => (
              <li key={item.key} className="legacy-list-item">
                <div>
                  <p className="legacy-list-title">
                    {item.symbol} <span>{item.interval}</span>
                  </p>
                  <p className="legacy-list-meta">{item.count} events in window</p>
                  <p className="legacy-list-detail">Latest: {item.latest.ruleKey}</p>
                </div>
                <div className={`legacy-pill ${directionClass(item.latest.direction)}`}>{item.latest.direction || "neutral"}</div>
              </li>
            ))
          )}
        </ul>
      )}
    </section>
  );
}
