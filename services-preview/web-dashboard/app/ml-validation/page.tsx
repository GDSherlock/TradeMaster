"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  fetchMlCandidates,
  fetchMlDriftLatest,
  fetchMlRuntime,
  fetchMlTrainingRuns,
  fetchMlValidationSummary,
  resolveRuntimeEndpoints
} from "@/lib/live-data";
import type {
  MlCandidateRow,
  MlDriftSnapshot,
  MlFeatureCatalogItem,
  MlRuntimeState,
  MlTrainingRun,
  MlValidationStatus
} from "@/types/legacy-dashboard";

const FEATURE_CATALOG: MlFeatureCatalogItem[] = [
  { name: "rsi_current", group: "RSI", description: "当前 RSI14 值" },
  { name: "rsi_previous", group: "RSI", description: "上一根 RSI14 值" },
  { name: "rsi_delta", group: "RSI", description: "RSI 变动幅度" },
  { name: "ema20_ema50_gap", group: "EMA", description: "EMA20 与 EMA50 相对价差" },
  { name: "ema50_ema200_gap", group: "EMA", description: "EMA50 与 EMA200 相对价差" },
  { name: "macd", group: "MACD", description: "MACD 值" },
  { name: "signal", group: "MACD", description: "MACD signal 值" },
  { name: "hist", group: "MACD", description: "MACD 柱值" },
  { name: "atr14_norm", group: "波动", description: "ATR14 归一化" },
  { name: "ret_vol_6", group: "波动", description: "6 bars 对数收益波动" },
  { name: "donchian_pos", group: "通道", description: "价格在 Donchian 通道中的位置" },
  { name: "bb_width", group: "通道", description: "布林带宽" },
  { name: "price_to_vwap", group: "通道", description: "价格相对 VWAP 偏离" },
  { name: "price_to_cloud_top", group: "云图", description: "价格相对云图上沿偏离" },
  { name: "ret_1", group: "收益", description: "1 bar 收益" },
  { name: "ret_3", group: "收益", description: "3 bars 收益" },
  { name: "ret_6", group: "收益", description: "6 bars 收益" },
  { name: "volume_z_6", group: "量能", description: "成交量 Z-Score(6)" },
  { name: "direction_long", group: "上下文", description: "方向 one-hot(long=1)" },
  { name: "hour_of_day", group: "上下文", description: "小时特征" },
  { name: "day_of_week", group: "上下文", description: "星期特征" },
  { name: "cooldown_seconds", group: "上下文", description: "规则冷却秒数" }
];

function formatNumber(value: number, digits = 4): string {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return value.toFixed(digits);
}

function statusClass(status: MlValidationStatus): string {
  return `mlv-badge ${status}`;
}

export default function MlValidationPage() {
  const endpoints = useMemo(() => resolveRuntimeEndpoints(), []);

  const [runtime, setRuntime] = useState<MlRuntimeState | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [candidates, setCandidates] = useState<MlCandidateRow[]>([]);
  const [runs, setRuns] = useState<MlTrainingRun[]>([]);
  const [drift, setDrift] = useState<MlDriftSnapshot[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    const [runtimeData, summaryData, candidateData, runData, driftData] = await Promise.all([
      fetchMlRuntime(endpoints.apiBase),
      fetchMlValidationSummary(endpoints.apiBase, "7d"),
      fetchMlCandidates(endpoints.apiBase, { limit: 30, interval: endpoints.defaultInterval }),
      fetchMlTrainingRuns(endpoints.apiBase, 10),
      fetchMlDriftLatest(endpoints.apiBase, 10)
    ]);

    setRuntime(runtimeData);
    setSummary(summaryData);
    setCandidates(candidateData);
    setRuns(runData);
    setDrift(driftData);
    setLoading(false);
  }, [endpoints.apiBase, endpoints.defaultInterval]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, endpoints.refreshIntervalMs);
    return () => {
      window.clearInterval(timer);
    };
  }, [endpoints.refreshIntervalMs, refresh]);

  const passRatio = Number(summary?.pass_ratio ?? 0);
  const avgProb = Number(summary?.avg_probability ?? 0);
  const queueLag = runtime?.queueLagScoped ?? runtime?.queueLag ?? 0;
  const runtimeInterval = runtime?.runtimeInterval ?? endpoints.defaultInterval;
  const trainStatus = runtime?.lastTrainStatus ?? "--";

  return (
    <main className="mlv-shell">
      <header className="mlv-head">
        <div>
          <h1>ML Validation Console</h1>
          <p>训练、验证、漂移监控与特征解释统一视图。</p>
        </div>
        <div className="mlv-head-actions">
          <Link href="/">返回主看板</Link>
          <button type="button" className="mlv-refresh-btn" onClick={() => void refresh()} disabled={loading}>
            {loading ? "刷新中..." : "立即刷新"}
          </button>
        </div>
      </header>

      <section className="mlv-grid">
        <article className="mlv-card">
          <p>Champion</p>
          <strong>{runtime?.championVersion ?? "--"}</strong>
        </article>
        <article className="mlv-card">
          <p>Queue Lag</p>
          <strong>{queueLag}</strong>
          <small className="mlv-inline-note">scope: {runtimeInterval}</small>
        </article>
        <article className="mlv-card">
          <p>7D Pass Ratio</p>
          <strong>{formatNumber(passRatio * 100, 2)}%</strong>
        </article>
        <article className="mlv-card">
          <p>7D Avg Probability</p>
          <strong>{formatNumber(avgProb * 100, 2)}%</strong>
        </article>
        <article className="mlv-card">
          <p>Train Status</p>
          <strong>{trainStatus}</strong>
          <small className="mlv-inline-note">
            samples: {runtime?.lastTrainSampleCount ?? 0} · pos {formatNumber((runtime?.lastTrainPositiveRatio ?? 0) * 100, 2)}%
          </small>
          <small className="mlv-inline-note">
            attempt: {runtime?.lastTrainAttemptAt ?? "--"}
          </small>
          {runtime?.lastTrainError ? <small className="mlv-inline-note">{runtime.lastTrainError}</small> : null}
        </article>
      </section>

      <section className="mlv-layout">
        <div className="mlv-stack">
          <article className="mlv-panel">
            <h2>Candidates (latest)</h2>
            <div className="mlv-table-wrap">
              <table className="mlv-table">
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
                  {candidates.length === 0 ? (
                    <tr>
                      <td colSpan={7}>No candidates</td>
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
                          <span className={statusClass(row.validationStatus)}>{row.validationStatus}</span>
                        </td>
                        <td>{row.mlValidation ? `${Math.round(row.mlValidation.probability * 100)}%` : "--"}</td>
                        <td>{row.mlValidation?.modelVersion ?? "--"}</td>
                        <td>
                          {row.mlValidation?.topFeatures.length
                            ? row.mlValidation.topFeatures
                                .slice(0, 2)
                                .map((item) => item.name)
                                .join(", ")
                            : "--"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <article className="mlv-panel">
            <h2>Training Runs</h2>
            <div className="mlv-table-wrap">
              <table className="mlv-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Version</th>
                    <th>Type</th>
                    <th>Promoted</th>
                    <th>Threshold</th>
                    <th>Samples</th>
                    <th>Test Precision</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.length === 0 ? (
                    <tr>
                      <td colSpan={7}>No runs</td>
                    </tr>
                  ) : (
                    runs.map((run) => {
                      const testMetrics = (run.metrics?.test as Record<string, unknown>) ?? {};
                      return (
                        <tr key={run.id}>
                          <td>{run.id}</td>
                          <td>{run.modelVersion}</td>
                          <td>{run.runType}</td>
                          <td>{run.promoted ? "yes" : "no"}</td>
                          <td>{formatNumber(run.threshold, 3)}</td>
                          <td>{run.sampleCount}</td>
                          <td>{formatNumber(Number(testMetrics.precision ?? 0), 4)}</td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </div>

        <aside className="mlv-stack">
          <article className="mlv-panel">
            <h2>Drift Checks</h2>
            <div className="mlv-table-wrap">
              <table className="mlv-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Max PSI</th>
                    <th>Triggered</th>
                  </tr>
                </thead>
                <tbody>
                  {drift.length === 0 ? (
                    <tr>
                      <td colSpan={3}>No drift data</td>
                    </tr>
                  ) : (
                    drift.map((row) => (
                      <tr key={row.id}>
                        <td>{row.id}</td>
                        <td>{formatNumber(row.maxFeaturePsi, 4)}</td>
                        <td>{row.triggeredRetrain ? "yes" : "no"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </article>

          <article className="mlv-panel">
            <h2>Feature Catalog</h2>
            <div className="mlv-table-wrap">
              <table className="mlv-table">
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Group</th>
                  </tr>
                </thead>
                <tbody>
                  {FEATURE_CATALOG.map((item) => (
                    <tr key={item.name}>
                      <td title={item.description}>{item.name}</td>
                      <td>{item.group}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </aside>
      </section>
    </main>
  );
}
