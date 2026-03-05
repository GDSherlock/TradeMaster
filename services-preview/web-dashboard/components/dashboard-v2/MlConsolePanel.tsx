"use client";

import { Bot, Filter, GitBranch, Radar, RefreshCcw, Workflow } from "lucide-react";

import { formatCompactNumber, formatDateTime, formatPercent, formatProbability } from "@/components/dashboard-v2/common/format";
import type {
  DashboardFetchState,
  MlCandidateFilterStatus,
  MlCandidateRow,
  MlDriftSnapshot,
  MlFeatureCatalogItem,
  MlRuntimeState,
  MlTrainingRun,
  MlValidationSummary
} from "@/types/legacy-dashboard";

type MlConsolePanelProps = {
  runtime: MlRuntimeState | null;
  summary: MlValidationSummary | null;
  candidates: MlCandidateRow[];
  trainingRuns: MlTrainingRun[];
  driftRows: MlDriftSnapshot[];
  featureCatalog: MlFeatureCatalogItem[];
  statusFilter: MlCandidateFilterStatus;
  onStatusFilterChange: (status: MlCandidateFilterStatus) => void;
  symbolFilter: string;
  onSymbolFilterChange: (symbol: string) => void;
  intervalFilter: string;
  onIntervalFilterChange: (interval: string) => void;
  followSelection: boolean;
  onFollowSelectionChange: (follow: boolean) => void;
  symbolOptions: string[];
  candidateFetchState?: DashboardFetchState;
  trainingFetchState?: DashboardFetchState;
  driftFetchState?: DashboardFetchState;
  onShowAllCandidates: () => void;
  onRefresh: () => void;
  refreshing: boolean;
};

const STATUS_OPTIONS: MlCandidateFilterStatus[] = ["all", "pending", "passed", "review", "rejected", "unavailable"];
const INTERVAL_OPTIONS = ["all", "1m", "5m", "15m", "1h", "4h", "1d"];

export function MlConsolePanel({
  runtime,
  summary,
  candidates,
  trainingRuns,
  driftRows,
  featureCatalog,
  statusFilter,
  onStatusFilterChange,
  symbolFilter,
  onSymbolFilterChange,
  intervalFilter,
  onIntervalFilterChange,
  followSelection,
  onFollowSelectionChange,
  symbolOptions,
  candidateFetchState,
  trainingFetchState,
  driftFetchState,
  onShowAllCandidates,
  onRefresh,
  refreshing
}: MlConsolePanelProps) {
  const isCandidateFilterActive = statusFilter !== "all" || symbolFilter !== "all" || intervalFilter !== "all";
  const queueLag = runtime?.queueLagScoped ?? runtime?.queueLag ?? 0;

  return (
    <section className="v2-panel v2-ml-panel" id="ml-console">
      <div className="v2-panel-head">
        <div>
          <p className="v2-kicker">ML Control Console</p>
          <h2>Runtime, Validation, Training, Drift</h2>
        </div>
        <button type="button" className="v2-icon-btn" onClick={onRefresh} disabled={refreshing} aria-label="Refresh ML console">
          <RefreshCcw size={16} className={refreshing ? "spin" : ""} />
        </button>
      </div>

      <div className="v2-ml-kpi-grid">
        <article className="v2-pulse-card">
          <p>Champion Version</p>
          <strong>{runtime?.championVersion ?? "--"}</strong>
          <span>
            {runtime?.championVersion
              ? `Queue lag ${queueLag}`
              : `No promoted model yet · Queue lag ${queueLag}`}
          </span>
        </article>
        <article className="v2-pulse-card">
          <p>Validation Pass Ratio</p>
          <strong>{summary ? formatPercent(summary.passRatio * 100, 2) : "--"}</strong>
          <span>{summary ? `${summary.passed}/${summary.total}` : "No summary"}</span>
        </article>
        <article className="v2-pulse-card">
          <p>Average Probability</p>
          <strong>{summary ? formatProbability(summary.avgProbability) : "--"}</strong>
          <span>Review {summary?.review ?? 0} · Rejected {summary?.rejected ?? 0}</span>
        </article>
        <article className="v2-pulse-card">
          <p>Last Drift Check</p>
          <strong>{runtime?.lastDriftCheckAt ? formatDateTime(runtime.lastDriftCheckAt) : "--"}</strong>
          <span>Last train {runtime?.lastTrainAt ? formatDateTime(runtime.lastTrainAt) : "--"}</span>
        </article>
      </div>

      <div className="v2-ml-layout">
        <article className="v2-subpanel">
          <div className="v2-subpanel-head v2-subpanel-head-stack">
            <h3>
              <Filter size={16} />
              Candidates
            </h3>
            <div className="v2-ml-filters">
              <label>
                Status
                <select value={statusFilter} onChange={(event) => onStatusFilterChange(event.target.value as MlCandidateFilterStatus)}>
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Symbol
                <select value={symbolFilter} onChange={(event) => onSymbolFilterChange(event.target.value)}>
                  <option value="all">all</option>
                  {symbolOptions.map((symbol) => (
                    <option key={symbol} value={symbol}>
                      {symbol}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Interval
                <select value={intervalFilter} onChange={(event) => onIntervalFilterChange(event.target.value)}>
                  {INTERVAL_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="v2-inline-checkbox">
                <input type="checkbox" checked={followSelection} onChange={(event) => onFollowSelectionChange(event.target.checked)} />
                Follow global context
              </label>

              {isCandidateFilterActive && (
                <button type="button" className="v2-text-btn" onClick={onShowAllCandidates}>
                  Show all candidates
                </button>
              )}
            </div>
          </div>

          <div className="v2-table-wrap">
            <table className="v2-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Symbol</th>
                  <th>Rule</th>
                  <th>Status</th>
                  <th>Prob</th>
                  <th>Model</th>
                  <th>Top Features</th>
                </tr>
              </thead>
              <tbody>
                {candidateFetchState?.rateLimited ? (
                  <tr>
                    <td colSpan={7}>Rate limited. Retrying automatically.</td>
                  </tr>
                ) : candidateFetchState?.degraded ? (
                  <tr>
                    <td colSpan={7}>Candidate feed is temporarily unavailable.</td>
                  </tr>
                ) : candidates.length === 0 ? (
                  <tr>
                    <td colSpan={7}>
                      {isCandidateFilterActive ? "No candidates under current filters. Try Show all candidates." : "No candidates in current window."}
                    </td>
                  </tr>
                ) : (
                  candidates.map((row) => (
                    <tr key={row.id}>
                      <td>{row.id}</td>
                      <td>
                        {row.symbol} {row.interval}
                      </td>
                      <td>{row.ruleKey}</td>
                      <td>
                        <span className={`v2-badge ${row.validationStatus}`}>{row.validationStatus}</span>
                      </td>
                      <td>{row.mlValidation ? formatProbability(row.mlValidation.probability) : "--"}</td>
                      <td>{row.mlValidation?.modelVersion ?? "--"}</td>
                      <td>
                        {row.mlValidation?.topFeatures.length
                          ? row.mlValidation.topFeatures
                              .slice(0, 2)
                              .map((item) => `${item.name}:${item.value.toFixed(3)}`)
                              .join(" | ")
                          : "--"}
                      </td>
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
              <Workflow size={16} />
              Training Runs
            </h3>
          </div>
          <div className="v2-table-wrap">
            <table className="v2-table compact">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Version</th>
                  <th>Promoted</th>
                  <th>Threshold</th>
                  <th>Samples</th>
                </tr>
              </thead>
              <tbody>
                {trainingFetchState?.rateLimited ? (
                  <tr>
                    <td colSpan={5}>Rate limited. Retrying automatically.</td>
                  </tr>
                ) : trainingFetchState?.degraded ? (
                  <tr>
                    <td colSpan={5}>Training runs are temporarily unavailable.</td>
                  </tr>
                ) : trainingRuns.length === 0 ? (
                  <tr>
                    <td colSpan={5}>No training runs yet in storage.</td>
                  </tr>
                ) : (
                  trainingRuns.slice(0, 8).map((run) => (
                    <tr key={run.id}>
                      <td>{run.id}</td>
                      <td>{run.modelVersion}</td>
                      <td>{run.promoted ? "yes" : "no"}</td>
                      <td>{run.threshold.toFixed(3)}</td>
                      <td>{formatCompactNumber(run.sampleCount, 0)}</td>
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
              Drift Checks
            </h3>
          </div>
          <div className="v2-table-wrap">
            <table className="v2-table compact">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Max PSI</th>
                  <th>Triggered</th>
                  <th>Version</th>
                </tr>
              </thead>
              <tbody>
                {driftFetchState?.rateLimited ? (
                  <tr>
                    <td colSpan={4}>Rate limited. Retrying automatically.</td>
                  </tr>
                ) : driftFetchState?.degraded ? (
                  <tr>
                    <td colSpan={4}>Drift checks are temporarily unavailable.</td>
                  </tr>
                ) : driftRows.length === 0 ? (
                  <tr>
                    <td colSpan={4}>No drift records yet in storage.</td>
                  </tr>
                ) : (
                  driftRows.slice(0, 8).map((row) => (
                    <tr key={row.id}>
                      <td>{row.id}</td>
                      <td>{row.maxFeaturePsi.toFixed(4)}</td>
                      <td>{row.triggeredRetrain ? "yes" : "no"}</td>
                      <td>{row.modelVersion}</td>
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
              <GitBranch size={16} />
              Feature Catalog
            </h3>
          </div>
          <div className="v2-table-wrap">
            <table className="v2-table compact">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Group</th>
                </tr>
              </thead>
              <tbody>
                {featureCatalog.map((item) => (
                  <tr key={item.name}>
                    <td title={item.description}>{item.name}</td>
                    <td>{item.group}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </div>

      <div className="v2-ml-footer">
        <span>
          <Bot size={14} /> Runtime Queue Lag: {queueLag}
        </span>
        <span>Interval Scope: {runtime?.runtimeInterval ?? "1h"}</span>
        <span>Latest Validation: {summary?.latestValidatedAt ? formatDateTime(summary.latestValidatedAt) : "--"}</span>
      </div>
    </section>
  );
}
