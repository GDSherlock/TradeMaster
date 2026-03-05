"use client";

import type { IndicatorRow } from "@/types/legacy-dashboard";

type IndicatorListProps = {
  tables: string[];
  selectedTable: string;
  onTableChange: (table: string) => void;
  symbols: string[];
  selectedSymbol: string;
  onSymbolChange: (symbol: string) => void;
  rows: IndicatorRow[];
};

function formatValue(value: unknown): string {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(4) : "--";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return "--";
}

export function IndicatorList({
  tables,
  selectedTable,
  onTableChange,
  symbols,
  selectedSymbol,
  onSymbolChange,
  rows
}: IndicatorListProps) {
  return (
    <section className="legacy-card">
      <div className="legacy-card-head">
        <h2>Indicators</h2>
        <span className="legacy-chip">Latest</span>
      </div>

      <div className="legacy-toolbar">
        <label>
          Table
          <select value={selectedTable} onChange={(event) => onTableChange(event.target.value)}>
            {tables.map((table) => (
              <option key={table} value={table}>
                {table}
              </option>
            ))}
          </select>
        </label>
        <label>
          Symbol
          <select value={selectedSymbol} onChange={(event) => onSymbolChange(event.target.value)}>
            {symbols.map((symbol) => (
              <option key={symbol} value={symbol}>
                {symbol}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ul className="legacy-list" aria-label="indicator rows">
        {rows.length === 0 ? (
          <li className="legacy-empty">No indicator values.</li>
        ) : (
          rows.slice(0, 12).map((row, index) => {
            const entries = Object.entries(row.payload).slice(0, 3);
            return (
              <li key={`${row.indicator}-${row.time}-${index}`} className="legacy-list-item">
                <div>
                  <p className="legacy-list-title">
                    {row.symbol} <span>{row.interval}</span>
                  </p>
                  <p className="legacy-list-meta">{row.indicator}</p>
                  <p className="legacy-list-detail">
                    {entries.length === 0
                      ? "No payload fields"
                      : entries.map(([key, value]) => `${key}: ${formatValue(value)}`).join(" | ")}
                  </p>
                </div>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
