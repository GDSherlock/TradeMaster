"use client";

import { Activity, ArrowDown, ArrowUp, Blend, CandlestickChart } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatClock, formatCompactNumber, formatPercent } from "@/components/dashboard-v2/common/format";
import type { IndicatorRow, MarketPulse, MomentumSnapshot, TopMoverItem, TopMoverOrder, TrendPoint } from "@/types/legacy-dashboard";

type MarketPanelProps = {
  momentum: MomentumSnapshot | null;
  pulse: MarketPulse;
  topMovers: TopMoverItem[];
  topMoverOrder: TopMoverOrder;
  onTopMoverOrderChange: (order: TopMoverOrder) => void;
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  trendInterval: string;
  trendSymbols: string[];
  trendMap: Record<string, TrendPoint[]>;
  indicatorTables: string[];
  selectedTable: string;
  onSelectedTableChange: (table: string) => void;
  indicatorRows: IndicatorRow[];
  updatedAtLabel: string;
};

function toneClass(changePct: number | null): string {
  if (changePct == null) {
    return "flat";
  }
  if (changePct > 0) {
    return "up";
  }
  if (changePct < 0) {
    return "down";
  }
  return "flat";
}

function renderIndicatorPayload(row: IndicatorRow): string {
  const entries = Object.entries(row.payload).slice(0, 3);
  if (entries.length === 0) {
    return "No payload";
  }
  return entries
    .map(([key, value]) => {
      if (typeof value === "number") {
        return `${key}: ${value.toFixed(4)}`;
      }
      return `${key}: ${String(value)}`;
    })
    .join(" | ");
}

function formatAxisValue(value: number): string {
  return formatCompactNumber(value, 0);
}

export function MarketPanel({
  momentum,
  pulse,
  topMovers,
  topMoverOrder,
  onTopMoverOrderChange,
  selectedSymbol,
  onSelectSymbol,
  trendInterval,
  trendSymbols,
  trendMap,
  indicatorTables,
  selectedTable,
  onSelectedTableChange,
  indicatorRows,
  updatedAtLabel
}: MarketPanelProps) {
  const selectedTrend = trendMap[selectedSymbol] ?? [];
  const miniSymbols = trendSymbols.filter((item) => item !== selectedSymbol).slice(0, 4);

  return (
    <section className="v2-panel v2-market-panel">
      <div className="v2-panel-head">
        <div>
          <p className="v2-kicker">Market Intelligence</p>
          <h2>Current Market Structure</h2>
        </div>
        <span className="v2-footnote">Updated {updatedAtLabel}</span>
      </div>

      <div className="v2-pulse-grid">
        <article className="v2-pulse-card">
          <p>Market Breadth</p>
          <strong>{pulse.breadthText}</strong>
          <span>{momentum ? `${momentum.upCount} up / ${momentum.downCount} down` : "No momentum snapshot"}</span>
        </article>
        <article className="v2-pulse-card">
          <p>Signal Density</p>
          <strong>{pulse.signalDensity}</strong>
          <span>Rolling signal window activity</span>
        </article>
        <article className="v2-pulse-card">
          <p>Mainstream Alignment</p>
          <strong>{formatPercent(pulse.alignmentPct, 1)}</strong>
          <span className={`v2-tone ${pulse.riskLabel}`}>{pulse.riskLabel.toUpperCase()}</span>
        </article>
      </div>

      <div className="v2-market-split">
        <article className="v2-subpanel">
          <div className="v2-subpanel-head">
            <h3>
              <CandlestickChart size={16} />
              {selectedSymbol} Trend
            </h3>
            <span>{trendInterval}</span>
          </div>
          <div className="v2-main-chart">
            {selectedTrend.length === 0 ? (
              <p className="v2-empty">No trend data.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={selectedTrend}>
                  <XAxis dataKey="time" hide />
                  <YAxis
                    domain={["dataMin", "dataMax"]}
                    width={56}
                    axisLine={false}
                    tickLine={false}
                    tickMargin={6}
                    tickFormatter={formatAxisValue}
                    tick={{ fill: "var(--v2-muted)", fontSize: 12 }}
                  />
                  <CartesianGrid vertical={false} stroke="var(--v2-chart-grid)" strokeDasharray="4 4" />
                  <Tooltip
                    cursor={{ stroke: "var(--v2-chart-grid)", strokeWidth: 1 }}
                    contentStyle={{
                      backgroundColor: "var(--v2-chart-tooltip-bg)",
                      borderColor: "var(--v2-chart-tooltip-border)",
                      borderRadius: "10px",
                      color: "var(--v2-chart-tooltip-text)"
                    }}
                    labelStyle={{ color: "var(--v2-chart-tooltip-text)" }}
                    itemStyle={{ color: "var(--v2-chart-tooltip-text)" }}
                    formatter={(value: number) => [formatCompactNumber(Number(value), 2), "Close"]}
                    labelFormatter={(value) => formatClock(Number(value))}
                  />
                  <Line
                    type="monotone"
                    dataKey="close"
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 1, stroke: "var(--v2-chart-tooltip-border)" }}
                    strokeWidth={2.8}
                    stroke="var(--v2-chart-line)"
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="v2-mini-trends">
            {miniSymbols.map((symbol) => {
              const points = trendMap[symbol] ?? [];
              const last = points.length > 0 ? points[points.length - 1].close : null;
              const prev = points.length > 1 ? points[points.length - 2].close : null;
              const deltaPct = last != null && prev != null && prev !== 0 ? ((last - prev) / prev) * 100 : null;
              return (
                <button key={symbol} type="button" className="v2-mini-trend" onClick={() => onSelectSymbol(symbol)}>
                  <div>
                    <strong>{symbol}</strong>
                    <span>{formatCompactNumber(last, 2)}</span>
                  </div>
                  <span className={`v2-badge ${toneClass(deltaPct)}`}>
                    {deltaPct == null ? "--" : `${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(2)}%`}
                  </span>
                </button>
              );
            })}
          </div>
        </article>

        <article className="v2-subpanel">
          <div className="v2-subpanel-head v2-subpanel-head-stack">
            <h3>
              <Blend size={16} />
              Top Movers
            </h3>
            <div className="v2-switch">
              <button
                type="button"
                className={topMoverOrder === "abs" ? "active" : ""}
                onClick={() => onTopMoverOrderChange("abs")}
              >
                Abs
              </button>
              <button
                type="button"
                className={topMoverOrder === "desc" ? "active" : ""}
                onClick={() => onTopMoverOrderChange("desc")}
              >
                Gainers
              </button>
              <button
                type="button"
                className={topMoverOrder === "asc" ? "active" : ""}
                onClick={() => onTopMoverOrderChange("asc")}
              >
                Losers
              </button>
            </div>
          </div>

          <div className="v2-table-wrap">
            <table className="v2-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>24h %</th>
                  <th>Quote Vol</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {topMovers.length === 0 ? (
                  <tr>
                    <td colSpan={4}>No mover data</td>
                  </tr>
                ) : (
                  topMovers.map((item) => (
                    <tr
                      key={item.symbol}
                      className={item.symbol === selectedSymbol ? "selected" : ""}
                      onClick={() => onSelectSymbol(item.symbol)}
                    >
                      <td>{item.symbol}</td>
                      <td>
                        <span className={`v2-badge ${toneClass(item.changePct)}`}>
                          {item.changePct == null
                            ? "--"
                            : `${item.changePct >= 0 ? "+" : ""}${item.changePct.toFixed(2)}%`}
                        </span>
                      </td>
                      <td>{formatCompactNumber(item.quoteVolume24h, 2)}</td>
                      <td>{formatClock(item.timestamp)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <article className="v2-subpanel">
        <div className="v2-subpanel-head v2-subpanel-head-stack">
          <h3>
            <Activity size={16} />
            Indicator Snapshot
          </h3>
          <label className="v2-inline-field">
            <span>Table</span>
            <select value={selectedTable} onChange={(event) => onSelectedTableChange(event.target.value)}>
              {indicatorTables.map((table) => (
                <option key={table} value={table}>
                  {table}
                </option>
              ))}
            </select>
          </label>
        </div>

        <ul className="v2-compact-list">
          {indicatorRows.length === 0 ? (
            <li className="v2-empty">No indicator values.</li>
          ) : (
            indicatorRows.slice(0, 8).map((row, index) => (
              <li key={`${row.indicator}-${row.time}-${index}`}>
                <div>
                  <strong>
                    {row.symbol} <span>{row.interval}</span>
                  </strong>
                  <p>{row.indicator}</p>
                  <p>{renderIndicatorPayload(row)}</p>
                </div>
              </li>
            ))
          )}
        </ul>
      </article>

      <div className="v2-market-footer">
        <span>
          <ArrowUp size={14} /> Up {momentum ? momentum.upCount : "--"}
        </span>
        <span>
          <ArrowDown size={14} /> Down {momentum ? momentum.downCount : "--"}
        </span>
        <span>Flat {momentum ? momentum.flatCount : "--"}</span>
      </div>
    </section>
  );
}
