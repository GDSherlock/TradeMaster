"use client";

import { IndicatorList } from "@/components/IndicatorList";
import { SignalFlowList } from "@/components/SignalFlowList";
import { TrendGrid } from "@/components/TrendGrid";
import type { IndicatorRow, MomentumSnapshot, SignalEvent, SignalViewMode, TrendPoint } from "@/types/legacy-dashboard";

type LegacyDashboardPanelProps = {
  momentum: MomentumSnapshot | null;
  signalEvents: SignalEvent[];
  signalMode: SignalViewMode;
  onSignalModeChange: (mode: SignalViewMode) => void;
  trendSymbols: string[];
  trendInterval: string;
  onTrendIntervalChange: (interval: string) => void;
  trendMap: Record<string, TrendPoint[]>;
  indicatorTables: string[];
  selectedTable: string;
  onSelectedTableChange: (table: string) => void;
  selectedSymbol: string;
  onSelectedSymbolChange: (symbol: string) => void;
  indicatorRows: IndicatorRow[];
  updatedAtLabel: string;
};

export function LegacyDashboardPanel({
  momentum,
  signalEvents,
  signalMode,
  onSignalModeChange,
  trendSymbols,
  trendInterval,
  onTrendIntervalChange,
  trendMap,
  indicatorTables,
  selectedTable,
  onSelectedTableChange,
  selectedSymbol,
  onSelectedSymbolChange,
  indicatorRows,
  updatedAtLabel
}: LegacyDashboardPanelProps) {
  const signalDensity = signalEvents.length;
  const breadthText = momentum ? `${momentum.upCount}/${momentum.total}` : "--";
  const dominantVolume = trendSymbols
    .map((symbol) => (trendMap[symbol] && trendMap[symbol].length > 0 ? trendMap[symbol][trendMap[symbol].length - 1].close : 0))
    .reduce((sum, value) => sum + value, 0);

  return (
    <section className="legacy-panel" id="dashboard">
      <div className="legacy-panel-head">
        <h1>Market Overview</h1>
        <p>Realtime snapshots, trendlines, signal flow, and indicator feeds.</p>
      </div>

      <div className="legacy-kpi-grid">
        <article className="legacy-kpi-card">
          <p className="legacy-kpi-label">Market Breadth</p>
          <p className="legacy-kpi-value">{breadthText}</p>
          <p className="legacy-kpi-foot">Advancers / total pairs</p>
        </article>
        <article className="legacy-kpi-card">
          <p className="legacy-kpi-label">Reference Price Sum</p>
          <p className="legacy-kpi-value">{dominantVolume > 0 ? dominantVolume.toFixed(0) : "--"}</p>
          <p className="legacy-kpi-foot">Last close across tracked symbols</p>
        </article>
        <article className="legacy-kpi-card">
          <p className="legacy-kpi-label">Signal Density</p>
          <p className="legacy-kpi-value">{signalDensity}</p>
          <p className="legacy-kpi-foot">Latest event window</p>
        </article>
      </div>

      <div className="legacy-content-grid">
        <TrendGrid symbols={trendSymbols} interval={trendInterval} onIntervalChange={onTrendIntervalChange} trendMap={trendMap} />

        <SignalFlowList events={signalEvents} mode={signalMode} onModeChange={onSignalModeChange} />

        <IndicatorList
          tables={indicatorTables}
          selectedTable={selectedTable}
          onTableChange={onSelectedTableChange}
          symbols={trendSymbols}
          selectedSymbol={selectedSymbol}
          onSymbolChange={onSelectedSymbolChange}
          rows={indicatorRows}
        />

        <section className="legacy-card">
          <div className="legacy-card-head">
            <h2>Market Momentum</h2>
            <span className="legacy-chip">24H</span>
          </div>
          <div className="legacy-momentum-grid">
            <article className="legacy-momentum-item up">
              <p>Up</p>
              <strong>{momentum ? momentum.upCount : "--"}</strong>
            </article>
            <article className="legacy-momentum-item down">
              <p>Down</p>
              <strong>{momentum ? momentum.downCount : "--"}</strong>
            </article>
            <article className="legacy-momentum-item flat">
              <p>Flat</p>
              <strong>{momentum ? momentum.flatCount : "--"}</strong>
            </article>
          </div>
          <p className="legacy-foot">Updated: {updatedAtLabel}</p>
        </section>
      </div>
    </section>
  );
}
