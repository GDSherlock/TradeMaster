"use client";

import { AlarmClockCheck, ListChecks, Microscope, Radar } from "lucide-react";

import { directionTone, formatDateTime, formatProbability } from "@/components/dashboard-v2/common/format";
import type { CooldownItem, SignalBoardMode, SignalEvent, SignalRuleItem } from "@/types/legacy-dashboard";

type SignalPanelProps = {
  events: SignalEvent[];
  mode: SignalBoardMode;
  onModeChange: (mode: SignalBoardMode) => void;
  signalRules: SignalRuleItem[];
  cooldownRows: CooldownItem[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  selectedEventId: number | null;
  onSelectEventId: (id: number | null) => void;
};

type GroupRow = {
  key: string;
  label: string;
  count: number;
  latest: SignalEvent;
};

function toTone(direction: string): "long" | "short" | "neutral" {
  return directionTone(direction);
}

function summarizeBySymbol(events: SignalEvent[]): GroupRow[] {
  const map = new Map<string, GroupRow>();
  for (const event of events) {
    const current = map.get(event.symbol);
    if (!current) {
      map.set(event.symbol, {
        key: event.symbol,
        label: `${event.symbol} (${event.interval})`,
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

function summarizeByRule(events: SignalEvent[]): GroupRow[] {
  const map = new Map<string, GroupRow>();
  for (const event of events) {
    const current = map.get(event.ruleKey);
    if (!current) {
      map.set(event.ruleKey, {
        key: event.ruleKey,
        label: event.ruleKey,
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

function modeLabel(mode: SignalBoardMode): string {
  switch (mode) {
    case "bySymbol":
      return "By Symbol";
    case "byRule":
      return "By Rule";
    default:
      return "Events";
  }
}

export function SignalPanel({
  events,
  mode,
  onModeChange,
  signalRules,
  cooldownRows,
  selectedSymbol,
  onSelectSymbol,
  selectedEventId,
  onSelectEventId
}: SignalPanelProps) {
  const bySymbol = summarizeBySymbol(events);
  const byRule = summarizeByRule(events);
  const selectedEvent = events.find((item) => item.id === selectedEventId) ?? null;

  return (
    <section className="v2-panel v2-signal-panel">
      <div className="v2-panel-head">
        <div>
          <p className="v2-kicker">Signal Intelligence</p>
          <h2>Signal Flow and Rule Health</h2>
        </div>
        <span className="v2-footnote">{modeLabel(mode)}</span>
      </div>

      <div className="v2-switch">
        <button type="button" className={mode === "events" ? "active" : ""} onClick={() => onModeChange("events")}>
          Events
        </button>
        <button type="button" className={mode === "bySymbol" ? "active" : ""} onClick={() => onModeChange("bySymbol")}>
          By Symbol
        </button>
        <button type="button" className={mode === "byRule" ? "active" : ""} onClick={() => onModeChange("byRule")}>
          By Rule
        </button>
      </div>

      <div className="v2-scroll-list">
        {mode === "events" &&
          (events.length === 0 ? (
            <p className="v2-empty">No signal events.</p>
          ) : (
            events.map((event) => (
              <button
                type="button"
                key={event.id}
                className={`v2-signal-item ${event.id === selectedEventId ? "selected" : ""}`}
                onClick={() => {
                  onSelectEventId(event.id);
                  onSelectSymbol(event.symbol);
                }}
              >
                <div>
                  <strong>
                    {event.symbol} <span>{event.interval}</span>
                  </strong>
                  <p>{event.ruleKey}</p>
                  <p>{event.detail || "No detail"}</p>
                  {event.mlValidation && (
                    <p>
                      ML {event.mlValidation.decision} · {formatProbability(event.mlValidation.probability)} · v
                      {event.mlValidation.modelVersion || "n/a"}
                    </p>
                  )}
                </div>
                <div className="v2-signal-meta">
                  <span className={`v2-badge ${toTone(event.direction)}`}>{event.direction || "neutral"}</span>
                  <span>score {event.score.toFixed(2)}</span>
                  <span>cooldown {event.cooldownLeftSeconds ?? 0}s</span>
                </div>
              </button>
            ))
          ))}

        {mode === "bySymbol" &&
          (bySymbol.length === 0 ? (
            <p className="v2-empty">No symbol aggregates.</p>
          ) : (
            bySymbol.map((row) => (
              <button
                type="button"
                key={row.key}
                className={`v2-signal-item ${row.latest.symbol === selectedSymbol ? "selected" : ""}`}
                onClick={() => {
                  onSelectSymbol(row.latest.symbol);
                  onSelectEventId(row.latest.id);
                }}
              >
                <div>
                  <strong>{row.label}</strong>
                  <p>{row.count} events in window</p>
                  <p>Latest rule: {row.latest.ruleKey}</p>
                </div>
                <div className="v2-signal-meta">
                  <span className={`v2-badge ${toTone(row.latest.direction)}`}>{row.latest.direction || "neutral"}</span>
                </div>
              </button>
            ))
          ))}

        {mode === "byRule" &&
          (byRule.length === 0 ? (
            <p className="v2-empty">No rule aggregates.</p>
          ) : (
            byRule.map((row) => (
              <button
                type="button"
                key={row.key}
                className="v2-signal-item"
                onClick={() => {
                  onSelectSymbol(row.latest.symbol);
                  onSelectEventId(row.latest.id);
                }}
              >
                <div>
                  <strong>{row.label}</strong>
                  <p>{row.count} hits in window</p>
                  <p>
                    Latest: {row.latest.symbol} {row.latest.interval}
                  </p>
                </div>
                <div className="v2-signal-meta">
                  <span className={`v2-badge ${toTone(row.latest.direction)}`}>{row.latest.direction || "neutral"}</span>
                </div>
              </button>
            ))
          ))}
      </div>

      {selectedEvent && (
        <article className="v2-detail-card">
          <div className="v2-subpanel-head">
            <h3>
              <Microscope size={16} />
              Signal Detail #{selectedEvent.id}
            </h3>
            <button type="button" onClick={() => onSelectEventId(null)} className="v2-text-btn">
              Close
            </button>
          </div>
          <dl>
            <div>
              <dt>Symbol / Interval</dt>
              <dd>
                {selectedEvent.symbol} / {selectedEvent.interval}
              </dd>
            </div>
            <div>
              <dt>Rule</dt>
              <dd>{selectedEvent.ruleKey}</dd>
            </div>
            <div>
              <dt>Detected At</dt>
              <dd>{formatDateTime(selectedEvent.detectedAt)}</dd>
            </div>
            <div>
              <dt>Direction</dt>
              <dd>{selectedEvent.direction}</dd>
            </div>
            <div>
              <dt>Score</dt>
              <dd>{selectedEvent.score.toFixed(3)}</dd>
            </div>
            <div>
              <dt>Cooldown Left</dt>
              <dd>{selectedEvent.cooldownLeftSeconds ?? 0}s</dd>
            </div>
          </dl>
          <p>{selectedEvent.detail || "No signal detail."}</p>
          {selectedEvent.mlValidation && (
            <div className="v2-ml-inline">
              <span className={`v2-badge ${selectedEvent.mlValidation.decision}`}>{selectedEvent.mlValidation.decision}</span>
              <span>prob {formatProbability(selectedEvent.mlValidation.probability)}</span>
              <span>threshold {formatProbability(selectedEvent.mlValidation.threshold)}</span>
              <span>model {selectedEvent.mlValidation.modelVersion || "n/a"}</span>
            </div>
          )}
        </article>
      )}

      <div className="v2-signal-bottom-grid">
        <article className="v2-subpanel">
          <div className="v2-subpanel-head">
            <h3>
              <ListChecks size={16} />
              Signal Rule Health
            </h3>
          </div>
          <div className="v2-table-wrap">
            <table className="v2-table compact">
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Cooldown</th>
                </tr>
              </thead>
              <tbody>
                {signalRules.length === 0 ? (
                  <tr>
                    <td colSpan={4}>No rule config</td>
                  </tr>
                ) : (
                  signalRules.slice(0, 10).map((rule) => (
                    <tr key={rule.ruleKey}>
                      <td>{rule.ruleKey}</td>
                      <td>
                        <span className={`v2-badge ${rule.enabled ? "passed" : "review"}`}>{rule.enabled ? "enabled" : "disabled"}</span>
                      </td>
                      <td>{rule.priority}</td>
                      <td>{rule.cooldownSeconds}s</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="v2-subpanel">
          <div className="v2-subpanel-head">
            <h3>
              <Radar size={16} />
              Cooldown Watch
            </h3>
          </div>
          <ul className="v2-compact-list">
            {cooldownRows.length === 0 ? (
              <li className="v2-empty">No cooldown rows.</li>
            ) : (
              cooldownRows.slice(0, 8).map((row) => (
                <li key={`${row.symbol}-${row.interval}-${row.ruleKey}`}>
                  <div>
                    <strong>
                      {row.symbol} <span>{row.interval}</span>
                    </strong>
                    <p>{row.ruleKey}</p>
                    <p>
                      <AlarmClockCheck size={12} /> {row.cooldownLeftSeconds}s left
                    </p>
                  </div>
                </li>
              ))
            )}
          </ul>
        </article>
      </div>
    </section>
  );
}
