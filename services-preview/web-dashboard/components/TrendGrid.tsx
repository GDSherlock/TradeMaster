"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TrendPoint } from "@/types/legacy-dashboard";

type TrendGridProps = {
  symbols: string[];
  interval: string;
  onIntervalChange: (interval: string) => void;
  trendMap: Record<string, TrendPoint[]>;
};

const INTERVAL_OPTIONS = ["1m", "5m", "15m", "1h", "4h", "1d"];

function formatPrice(value: number): string {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function TrendGrid({ symbols, interval, onIntervalChange, trendMap }: TrendGridProps) {
  return (
    <section className="legacy-card">
      <div className="legacy-card-head">
        <h2>Trendlines</h2>
        <div className="legacy-intervals" role="tablist" aria-label="intervals">
          {INTERVAL_OPTIONS.map((item) => (
            <button
              type="button"
              key={item}
              className={interval === item ? "active" : ""}
              onClick={() => onIntervalChange(item)}
              role="tab"
              aria-selected={interval === item}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="legacy-trend-grid">
        {symbols.map((symbol) => {
          const points = trendMap[symbol] ?? [];
          return (
            <article key={symbol} className="legacy-trend-item">
              <div className="legacy-trend-head">
                <h3>{symbol}</h3>
                <span>{interval}</span>
              </div>
              <div className="legacy-trend-chart">
                {points.length === 0 ? (
                  <div className="legacy-empty">No candles.</div>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={points}>
                      <XAxis dataKey="time" hide />
                      <YAxis hide domain={["dataMin", "dataMax"]} />
                      <Tooltip formatter={(value: number) => [formatPrice(Number(value)), "Close"]} labelFormatter={() => symbol} />
                      <Line type="monotone" dataKey="close" stroke="#2f7d6d" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
