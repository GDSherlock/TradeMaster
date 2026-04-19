"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Loader2, Play, RotateCcw, Save, SquareX } from "lucide-react";

import {
  cancelBacktestRun,
  createBacktestRun,
  createBacktestStrategy,
  fetchBacktestCatalog,
  fetchBacktestEquity,
  fetchBacktestRun,
  fetchBacktestRuns,
  fetchBacktestStrategies,
  fetchBacktestTrades,
  fetchBacktestVersions
} from "@/lib/backtest-data";
import type {
  BacktestCatalog,
  BacktestClauseSide,
  BacktestClauseType,
  BacktestEquityPoint,
  BacktestRun,
  BacktestStrategy,
  BacktestStrategyVersion,
  BacktestTrade
} from "@/types/backtest";

type ClauseFormState = {
  id: string;
  type: BacktestClauseType;
  side: BacktestClauseSide;
  ruleKey: string;
  leftIndicator: string;
  leftField: string;
  operator: string;
  rightKind: "constant" | "field";
  rightValue: string;
  rightIndicator: string;
  rightField: string;
};

type StrategyBuilderState = {
  strategyId: number | null;
  selectedVersionId: number | null;
  name: string;
  description: string;
  symbol: string;
  interval: string;
  directionMode: "long" | "short" | "both";
  entryLogic: "all" | "any";
  exitLogic: "all" | "any";
  equityPct: string;
  leverage: string;
  feeBps: string;
  slippageBps: string;
  maxTotalDrawdownPct: string;
  trailingDrawdownPct: string;
  runStart: string;
  runEnd: string;
  entryClauses: ClauseFormState[];
  exitClauses: ClauseFormState[];
};

type SaveStrategyResponse = {
  strategy_id: number;
  name: string;
  description: string;
  created_at: string | null;
  updated_at: string | null;
  version: BacktestStrategyVersion;
};

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function toLocalInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hours = `${date.getHours()}`.padStart(2, "0");
  const minutes = `${date.getMinutes()}`.padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function defaultRunWindow(): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now.getTime() - 1000 * 60 * 60 * 24 * 90);
  return {
    start: toLocalInputValue(start),
    end: toLocalInputValue(now)
  };
}

function makeClause(catalog: BacktestCatalog | null, side: BacktestClauseSide, allowAnySide: boolean): ClauseFormState {
  const firstIndicator = Object.keys(catalog?.indicator_fields ?? { ema_20: ["ema_20"] })[0] ?? "ema_20";
  const firstField = catalog?.indicator_fields[firstIndicator]?.[0] ?? "ema_20";
  const firstRule = catalog?.signal_rules[0] ?? "RSI_OVERSOLD";
  const operator = catalog?.operators[0] ?? ">";
  return {
    id: makeId(),
    type: "signal_rule",
    side: allowAnySide ? side : side === "any" ? "long" : side,
    ruleKey: firstRule,
    leftIndicator: firstIndicator,
    leftField: firstField,
    operator,
    rightKind: "constant",
    rightValue: "0",
    rightIndicator: firstIndicator,
    rightField: firstField
  };
}

function buildDefaultState(catalog: BacktestCatalog | null): StrategyBuilderState {
  const window = defaultRunWindow();
  return {
    strategyId: null,
    selectedVersionId: null,
    name: "",
    description: "",
    symbol: catalog?.symbols[0] ?? "BTCUSDT",
    interval: catalog?.intervals[3] ?? catalog?.intervals[0] ?? "1h",
    directionMode: "both",
    entryLogic: "all",
    exitLogic: "any",
    equityPct: "25",
    leverage: "2",
    feeBps: "4",
    slippageBps: "2",
    maxTotalDrawdownPct: "15",
    trailingDrawdownPct: "10",
    runStart: window.start,
    runEnd: window.end,
    entryClauses: [makeClause(catalog, "long", false)],
    exitClauses: [makeClause(catalog, "long", true)]
  };
}

function decodeClause(raw: unknown, index: number, catalog: BacktestCatalog | null, allowAnySide: boolean): ClauseFormState {
  const fallback = makeClause(catalog, allowAnySide ? "any" : "long", allowAnySide);
  if (!raw || typeof raw !== "object") {
    return { ...fallback, id: `${fallback.id}-${index}` };
  }
  const clause = raw as Record<string, unknown>;
  const type = clause.type === "indicator_compare" ? "indicator_compare" : "signal_rule";
  const sideRaw = typeof clause.side === "string" ? clause.side : fallback.side;
  const side = sideRaw === "any" ? "any" : sideRaw === "short" ? "short" : "long";
  const left = typeof clause.left === "object" && clause.left ? (clause.left as Record<string, unknown>) : {};
  const right = typeof clause.right === "object" && clause.right ? (clause.right as Record<string, unknown>) : {};
  const leftIndicator = typeof left.indicator === "string" ? left.indicator : fallback.leftIndicator;
  const leftField = typeof left.field === "string" ? left.field : catalog?.indicator_fields[leftIndicator]?.[0] ?? fallback.leftField;
  const rightIndicator = typeof right.indicator === "string" ? right.indicator : fallback.rightIndicator;
  const rightField = typeof right.field === "string" ? right.field : catalog?.indicator_fields[rightIndicator]?.[0] ?? fallback.rightField;
  return {
    id: makeId(),
    type,
    side: allowAnySide ? side : side === "any" ? "long" : side,
    ruleKey: typeof clause.rule_key === "string" ? clause.rule_key : fallback.ruleKey,
    leftIndicator,
    leftField,
    operator: typeof clause.operator === "string" ? clause.operator : fallback.operator,
    rightKind: right.kind === "field" ? "field" : "constant",
    rightValue: right.kind === "constant" && right.value != null ? String(right.value) : fallback.rightValue,
    rightIndicator,
    rightField
  };
}

function hydrateBuilder(version: BacktestStrategyVersion, catalog: BacktestCatalog | null): StrategyBuilderState {
  const defaults = buildDefaultState(catalog);
  const dsl = (version.dsl ?? {}) as Record<string, unknown>;
  const entry = (dsl.entry ?? {}) as Record<string, unknown>;
  const exit = (dsl.exit ?? {}) as Record<string, unknown>;
  const sizing = (dsl.sizing ?? {}) as Record<string, unknown>;
  const costs = (dsl.costs ?? {}) as Record<string, unknown>;
  const drawdown = (dsl.drawdown ?? {}) as Record<string, unknown>;
  return {
    ...defaults,
    strategyId: version.strategy_id,
    selectedVersionId: version.id,
    symbol: version.symbol,
    interval: version.interval,
    directionMode: sizing.direction_mode === "long" || sizing.direction_mode === "short" ? sizing.direction_mode : "both",
    entryLogic: entry.logic === "any" ? "any" : "all",
    exitLogic: exit.logic === "all" ? "all" : "any",
    equityPct: `${Number(sizing.equity_pct ?? 0.25) * 100}`,
    leverage: `${Number(sizing.leverage ?? 2)}`,
    feeBps: `${Number(costs.fee_bps ?? 4)}`,
    slippageBps: `${Number(costs.slippage_bps ?? 2)}`,
    maxTotalDrawdownPct: drawdown.max_total_drawdown_pct != null ? `${Number(drawdown.max_total_drawdown_pct) * 100}` : "",
    trailingDrawdownPct: drawdown.trailing_drawdown_pct != null ? `${Number(drawdown.trailing_drawdown_pct) * 100}` : "",
    entryClauses: Array.isArray(entry.clauses) && entry.clauses.length > 0
      ? entry.clauses.map((clause, index) => decodeClause(clause, index, catalog, false))
      : defaults.entryClauses,
    exitClauses: Array.isArray(exit.clauses) && exit.clauses.length > 0
      ? exit.clauses.map((clause, index) => decodeClause(clause, index, catalog, true))
      : [],
    name: "",
    description: ""
  };
}

function toIso(value: string): string {
  const parsed = new Date(value);
  return parsed.toISOString();
}

function buildDslPayload(builder: StrategyBuilderState) {
  return {
    entry: {
      logic: builder.entryLogic,
      clauses: builder.entryClauses.map((clause) => {
        if (clause.type === "signal_rule") {
          return {
            type: clause.type,
            side: clause.side,
            rule_key: clause.ruleKey
          };
        }
        return {
          type: clause.type,
          side: clause.side,
          left: { indicator: clause.leftIndicator, field: clause.leftField },
          operator: clause.operator,
          right:
            clause.rightKind === "field"
              ? { kind: "field", indicator: clause.rightIndicator, field: clause.rightField }
              : { kind: "constant", value: Number(clause.rightValue || 0) }
        };
      })
    },
    exit: {
      logic: builder.exitLogic,
      clauses: builder.exitClauses.map((clause) => {
        if (clause.type === "signal_rule") {
          return {
            type: clause.type,
            side: clause.side,
            rule_key: clause.ruleKey
          };
        }
        return {
          type: clause.type,
          side: clause.side,
          left: { indicator: clause.leftIndicator, field: clause.leftField },
          operator: clause.operator,
          right:
            clause.rightKind === "field"
              ? { kind: "field", indicator: clause.rightIndicator, field: clause.rightField }
              : { kind: "constant", value: Number(clause.rightValue || 0) }
        };
      })
    },
    sizing: {
      equity_pct: Number(builder.equityPct || 0) / 100,
      leverage: Number(builder.leverage || 0),
      direction_mode: builder.directionMode
    },
    costs: {
      fee_bps: Number(builder.feeBps || 0),
      slippage_bps: Number(builder.slippageBps || 0)
    },
    drawdown: {
      max_total_drawdown_pct: builder.maxTotalDrawdownPct ? Number(builder.maxTotalDrawdownPct) / 100 : null,
      trailing_drawdown_pct: builder.trailingDrawdownPct ? Number(builder.trailingDrawdownPct) / 100 : null,
      action: "flatten_and_halt"
    },
    execution: {
      fill_policy: "current_bar_close"
    }
  };
}

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  return `${(value * 100).toFixed(2)}%`;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  return value.toFixed(digits);
}

function formatDateLabel(value: string | null): string {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "--" : parsed.toLocaleString();
}

function chartDateLabel(value: string | null): string {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "" : `${parsed.getMonth() + 1}/${parsed.getDate()}`;
}

function summarizeRun(run: BacktestRun | null): Array<{ label: string; value: string; tone?: string }> {
  if (!run) {
    return [];
  }
  const summary = run.summary;
  return [
    { label: "Return", value: formatPct(summary.total_return_pct), tone: (summary.total_return_pct ?? 0) >= 0 ? "positive" : "negative" },
    { label: "Max DD", value: formatPct(summary.max_total_drawdown_pct) },
    { label: "Trailing DD", value: formatPct(summary.max_trailing_drawdown_pct) },
    { label: "Trades", value: formatNumber(summary.trade_count, 0) },
    { label: "Win Rate", value: formatPct(summary.win_rate) },
    { label: "Profit Factor", value: summary.profit_factor == null ? "--" : formatNumber(summary.profit_factor) },
    { label: "Avg Hold", value: formatNumber(summary.avg_holding_bars) },
    { label: "Halt", value: summary.halt_reason ?? "none" }
  ];
}

export default function BacktestPage() {
  const [catalog, setCatalog] = useState<BacktestCatalog | null>(null);
  const [strategies, setStrategies] = useState<BacktestStrategy[]>([]);
  const [versions, setVersions] = useState<BacktestStrategyVersion[]>([]);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null);
  const [equityPoints, setEquityPoints] = useState<BacktestEquityPoint[]>([]);
  const [trades, setTrades] = useState<BacktestTrade[]>([]);
  const [builder, setBuilder] = useState<StrategyBuilderState>(() => buildDefaultState(null));
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [cancelingRunId, setCancelingRunId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const catalogRef = useRef<BacktestCatalog | null>(null);
  const strategiesRef = useRef<BacktestStrategy[]>([]);
  const selectedRunIdRef = useRef<number | null>(null);

  const runStats = useMemo(() => summarizeRun(selectedRun), [selectedRun]);

  useEffect(() => {
    catalogRef.current = catalog;
  }, [catalog]);

  useEffect(() => {
    strategiesRef.current = strategies;
  }, [strategies]);

  useEffect(() => {
    selectedRunIdRef.current = selectedRun?.id ?? null;
  }, [selectedRun]);

  const refreshRuns = useCallback(async (preserveRunId?: number | null) => {
    const nextRuns = await fetchBacktestRuns(100);
    setRuns(nextRuns);
    const targetId = preserveRunId ?? selectedRunIdRef.current ?? nextRuns[0]?.id ?? null;
    if (targetId != null) {
      const hit = nextRuns.find((run) => run.id === targetId) ?? null;
      setSelectedRun(hit);
    } else {
      setSelectedRun(null);
    }
  }, []);

  const loadRunDetail = useCallback(async (runId: number) => {
    setDetailLoading(true);
    try {
      const [run, nextEquity, nextTrades] = await Promise.all([
        fetchBacktestRun(runId),
        fetchBacktestEquity(runId),
        fetchBacktestTrades(runId)
      ]);
      setSelectedRun(run);
      setEquityPoints(nextEquity);
      setTrades(nextTrades);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadStrategyVersions = useCallback(async (strategyId: number, strategyList?: BacktestStrategy[], catalogOverride?: BacktestCatalog | null) => {
    const [versionRows] = await Promise.all([fetchBacktestVersions(strategyId)]);
    setVersions(versionRows);
    const latest = versionRows[0] ?? null;
    const strategy = (strategyList ?? strategiesRef.current).find((item) => item.id === strategyId) ?? null;
    if (latest) {
      const hydrated = hydrateBuilder(latest, catalogOverride ?? catalogRef.current);
      hydrated.name = strategy?.name ?? "";
      hydrated.description = strategy?.description ?? "";
      hydrated.strategyId = strategyId;
      hydrated.selectedVersionId = latest.id;
      setBuilder(hydrated);
    }
  }, []);

  useEffect(() => {
    let active = true;
    async function bootstrap() {
      try {
        setLoading(true);
        const [nextCatalog, nextStrategies, nextRuns] = await Promise.all([
          fetchBacktestCatalog(),
          fetchBacktestStrategies(),
          fetchBacktestRuns(100)
        ]);
        if (!active) {
          return;
        }
        setCatalog(nextCatalog);
        setStrategies(nextStrategies);
        setRuns(nextRuns);

        const initialBuilder = buildDefaultState(nextCatalog);
        setBuilder(initialBuilder);

        if (nextStrategies[0]?.id != null) {
          await loadStrategyVersions(nextStrategies[0].id, nextStrategies, nextCatalog);
        }
        if (nextRuns[0]?.id != null) {
          await loadRunDetail(nextRuns[0].id);
        }
      } catch {
        if (active) {
          setError("Unable to load backtest workspace.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    void bootstrap();
    return () => {
      active = false;
    };
  }, [loadRunDetail, loadStrategyVersions]);

  useEffect(() => {
    if (!runs.some((run) => run.status === "queued" || run.status === "running")) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void refreshRuns(selectedRun?.id ?? null).then(async () => {
        if (selectedRun?.id != null) {
          const fresh = await fetchBacktestRun(selectedRun.id);
          setSelectedRun(fresh);
          if (fresh.status === "completed" || fresh.status === "failed" || fresh.status === "canceled") {
            const [nextEquity, nextTrades] = await Promise.all([
              fetchBacktestEquity(fresh.id),
              fetchBacktestTrades(fresh.id)
            ]);
            setEquityPoints(nextEquity);
            setTrades(nextTrades);
          }
        }
      }).catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refreshRuns, runs, selectedRun]);

  const updateClause = useCallback(
    (kind: "entryClauses" | "exitClauses", clauseId: string, patch: Partial<ClauseFormState>) => {
      setBuilder((current) => ({
        ...current,
        [kind]: current[kind].map((clause) => {
          if (clause.id !== clauseId) {
            return clause;
          }
          const next = { ...clause, ...patch };
          if (patch.leftIndicator) {
            next.leftField = catalog?.indicator_fields[patch.leftIndicator]?.[0] ?? next.leftField;
          }
          if (patch.rightIndicator) {
            next.rightField = catalog?.indicator_fields[patch.rightIndicator]?.[0] ?? next.rightField;
          }
          return next;
        })
      }));
    },
    [catalog]
  );

  const addClause = useCallback((kind: "entryClauses" | "exitClauses") => {
    const allowAnySide = kind === "exitClauses";
    setBuilder((current) => ({
      ...current,
      [kind]: [...current[kind], makeClause(catalog, allowAnySide ? "any" : "long", allowAnySide)]
    }));
  }, [catalog]);

  const removeClause = useCallback((kind: "entryClauses" | "exitClauses", clauseId: string) => {
    setBuilder((current) => ({
      ...current,
      [kind]: current[kind].filter((clause) => clause.id !== clauseId)
    }));
  }, []);

  const handleSaveStrategy = useCallback(async () => {
    try {
      setSaving(true);
      setError(null);
      const payload = {
        strategy_id: builder.strategyId ?? undefined,
        name: builder.name,
        description: builder.description,
        exchange: "binance_futures_um",
        symbol: builder.symbol,
        interval: builder.interval,
        dsl: buildDslPayload(builder)
      };
      const result = await createBacktestStrategy(payload) as SaveStrategyResponse;
      const nextStrategies = await fetchBacktestStrategies();
      setStrategies(nextStrategies);
      await loadStrategyVersions(result.strategy_id, nextStrategies);
    } catch {
      setError("Unable to save strategy version.");
    } finally {
      setSaving(false);
    }
  }, [builder, loadStrategyVersions]);

  const handleQueueRun = useCallback(async () => {
    try {
      setSubmitting(true);
      setError(null);
      const versionId = builder.selectedVersionId ?? versions[0]?.id ?? null;
      if (versionId == null) {
        setError("Save the strategy first so a version exists.");
        return;
      }
      const run = await createBacktestRun({
        strategy_version_id: versionId,
        symbol: builder.symbol,
        interval: builder.interval,
        start_ts: toIso(builder.runStart),
        end_ts: toIso(builder.runEnd)
      });
      await refreshRuns(run.id);
      await loadRunDetail(run.id);
    } catch {
      setError("Unable to queue backtest run.");
    } finally {
      setSubmitting(false);
    }
  }, [builder, loadRunDetail, refreshRuns, versions]);

  const handleCancelRun = useCallback(async (runId: number) => {
    try {
      setCancelingRunId(runId);
      await cancelBacktestRun(runId);
      await refreshRuns(runId);
      await loadRunDetail(runId);
    } catch {
      setError("Unable to cancel run.");
    } finally {
      setCancelingRunId(null);
    }
  }, [loadRunDetail, refreshRuns]);

  if (loading) {
    return (
      <div className="bt-shell">
        <div className="bt-loading">
          <Loader2 className="spin" size={18} />
          Loading backtest lab...
        </div>
      </div>
    );
  }

  return (
    <div className="bt-shell">
      <header className="v2-header bt-header">
        <div className="v2-header-main">
          <div className="v2-brand">
            <span className="v2-brand-mark">BT</span>
            <div>
              <h1>Backtest Lab</h1>
              <p>Build one-symbol drawdown-aware strategies, queue async runs, and inspect equity + trades.</p>
            </div>
          </div>
          <div className="v2-header-actions">
            <button
              type="button"
              className="v2-icon-btn"
              onClick={() => {
                setError(null);
                setBuilder(buildDefaultState(catalog));
              }}
              aria-label="Reset builder"
            >
              <RotateCcw size={16} />
            </button>
            <Link href="/" className="v2-link-btn">
              Back To Dashboard
            </Link>
          </div>
        </div>
      </header>

      <main className="bt-grid">
        <section className="v2-panel bt-panel">
          <div className="bt-panel-head">
            <div>
              <p className="v2-kicker">Strategy Builder</p>
              <h2>Signals, indicators, sizing, and drawdown controls</h2>
            </div>
            <div className="bt-actions">
              <button type="button" className="bt-primary-btn" onClick={() => void handleSaveStrategy()} disabled={saving}>
                {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
                {builder.strategyId ? "Save Version" : "Save Strategy"}
              </button>
              <button type="button" className="bt-secondary-btn" onClick={() => void handleQueueRun()} disabled={submitting}>
                {submitting ? <Loader2 size={15} className="spin" /> : <Play size={15} />}
                Queue Run
              </button>
            </div>
          </div>

          {error && <p className="bt-error">{error}</p>}

          <div className="bt-form-grid">
            <label className="v2-field">
              <span>Strategy Name</span>
              <input value={builder.name} onChange={(event) => setBuilder((current) => ({ ...current, name: event.target.value }))} />
            </label>
            <label className="v2-field">
              <span>Symbol</span>
              <select value={builder.symbol} onChange={(event) => setBuilder((current) => ({ ...current, symbol: event.target.value }))}>
                {catalog?.symbols.map((symbol) => (
                  <option key={symbol} value={symbol}>
                    {symbol}
                  </option>
                ))}
              </select>
            </label>
            <label className="v2-field">
              <span>Interval</span>
              <select value={builder.interval} onChange={(event) => setBuilder((current) => ({ ...current, interval: event.target.value }))}>
                {catalog?.intervals.map((interval) => (
                  <option key={interval} value={interval}>
                    {interval}
                  </option>
                ))}
              </select>
            </label>
            <label className="v2-field bt-description-field">
              <span>Description</span>
              <textarea value={builder.description} onChange={(event) => setBuilder((current) => ({ ...current, description: event.target.value }))} />
            </label>
          </div>

          <div className="bt-form-grid bt-metrics-grid">
            <label className="v2-field">
              <span>Direction</span>
              <select value={builder.directionMode} onChange={(event) => setBuilder((current) => ({ ...current, directionMode: event.target.value as StrategyBuilderState["directionMode"] }))}>
                <option value="both">Both</option>
                <option value="long">Long</option>
                <option value="short">Short</option>
              </select>
            </label>
            <label className="v2-field">
              <span>Equity %</span>
              <input type="number" min="1" max="100" value={builder.equityPct} onChange={(event) => setBuilder((current) => ({ ...current, equityPct: event.target.value }))} />
            </label>
            <label className="v2-field">
              <span>Leverage</span>
              <input type="number" min="1" max="50" value={builder.leverage} onChange={(event) => setBuilder((current) => ({ ...current, leverage: event.target.value }))} />
            </label>
            <label className="v2-field">
              <span>Fee (bps)</span>
              <input type="number" min="0" value={builder.feeBps} onChange={(event) => setBuilder((current) => ({ ...current, feeBps: event.target.value }))} />
            </label>
            <label className="v2-field">
              <span>Slippage (bps)</span>
              <input type="number" min="0" value={builder.slippageBps} onChange={(event) => setBuilder((current) => ({ ...current, slippageBps: event.target.value }))} />
            </label>
            <label className="v2-field">
              <span>Max Total DD %</span>
              <input type="number" min="0" max="100" value={builder.maxTotalDrawdownPct} onChange={(event) => setBuilder((current) => ({ ...current, maxTotalDrawdownPct: event.target.value }))} />
            </label>
            <label className="v2-field">
              <span>Trailing DD %</span>
              <input type="number" min="0" max="100" value={builder.trailingDrawdownPct} onChange={(event) => setBuilder((current) => ({ ...current, trailingDrawdownPct: event.target.value }))} />
            </label>
            <label className="v2-field">
              <span>Run Start</span>
              <input type="datetime-local" value={builder.runStart} onChange={(event) => setBuilder((current) => ({ ...current, runStart: event.target.value }))} />
            </label>
            <label className="v2-field">
              <span>Run End</span>
              <input type="datetime-local" value={builder.runEnd} onChange={(event) => setBuilder((current) => ({ ...current, runEnd: event.target.value }))} />
            </label>
          </div>

          <div className="bt-builder-sections">
            <div className="bt-clause-panel">
              <div className="bt-clause-head">
                <div>
                  <p className="v2-kicker">Entry Rules</p>
                  <h3>Only one position at a time</h3>
                </div>
                <div className="bt-inline-tools">
                  <select value={builder.entryLogic} onChange={(event) => setBuilder((current) => ({ ...current, entryLogic: event.target.value as "all" | "any" }))}>
                    <option value="all">all</option>
                    <option value="any">any</option>
                  </select>
                  <button type="button" className="bt-ghost-btn" onClick={() => addClause("entryClauses")}>
                    Add Clause
                  </button>
                </div>
              </div>
              <div className="bt-clause-list">
                {builder.entryClauses.map((clause) => (
                  <ClauseEditor
                    key={clause.id}
                    clause={clause}
                    catalog={catalog}
                    allowAnySide={false}
                    onChange={(patch) => updateClause("entryClauses", clause.id, patch)}
                    onRemove={() => removeClause("entryClauses", clause.id)}
                  />
                ))}
              </div>
            </div>

            <div className="bt-clause-panel">
              <div className="bt-clause-head">
                <div>
                  <p className="v2-kicker">Exit Rules</p>
                  <h3>Evaluated before drawdown and new entries</h3>
                </div>
                <div className="bt-inline-tools">
                  <select value={builder.exitLogic} onChange={(event) => setBuilder((current) => ({ ...current, exitLogic: event.target.value as "all" | "any" }))}>
                    <option value="all">all</option>
                    <option value="any">any</option>
                  </select>
                  <button type="button" className="bt-ghost-btn" onClick={() => addClause("exitClauses")}>
                    Add Clause
                  </button>
                </div>
              </div>
              <div className="bt-clause-list">
                {builder.exitClauses.map((clause) => (
                  <ClauseEditor
                    key={clause.id}
                    clause={clause}
                    catalog={catalog}
                    allowAnySide
                    onChange={(patch) => updateClause("exitClauses", clause.id, patch)}
                    onRemove={() => removeClause("exitClauses", clause.id)}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="bt-strategy-list">
            <div className="bt-clause-head">
              <div>
                <p className="v2-kicker">Saved Strategies</p>
                <h3>Immutable versions for repeatable runs</h3>
              </div>
            </div>
            <div className="bt-strategy-grid">
              {strategies.map((strategy) => (
                <button
                  key={strategy.id}
                  type="button"
                  className={`bt-strategy-card ${builder.strategyId === strategy.id ? "active" : ""}`}
                  onClick={() => void loadStrategyVersions(strategy.id)}
                >
                  <strong>{strategy.name}</strong>
                  <span>
                    {strategy.symbol ?? "--"} · {strategy.interval ?? "--"} · v{strategy.latest_version_no ?? "--"}
                  </span>
                  <p>{strategy.description || "No description."}</p>
                </button>
              ))}
            </div>
            {versions.length > 0 && (
              <div className="bt-version-strip">
                {versions.map((version) => (
                  <button
                    key={version.id}
                    type="button"
                    className={`bt-version-pill ${builder.selectedVersionId === version.id ? "active" : ""}`}
                    onClick={() => {
                      const strategy = strategies.find((item) => item.id === version.strategy_id);
                      const next = hydrateBuilder(version, catalog);
                      next.name = strategy?.name ?? "";
                      next.description = strategy?.description ?? "";
                      next.strategyId = version.strategy_id;
                      next.selectedVersionId = version.id;
                      setBuilder(next);
                    }}
                  >
                    v{version.version_no}
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="v2-panel bt-panel">
          <div className="bt-panel-head">
            <div>
              <p className="v2-kicker">Run Queue / History</p>
              <h2>Queued, running, completed, failed, canceled</h2>
            </div>
            <button type="button" className="bt-ghost-btn" onClick={() => void refreshRuns(selectedRun?.id ?? null)}>
              Refresh
            </button>
          </div>

          <div className="bt-run-list">
            {runs.length === 0 ? (
              <p className="bt-empty">No backtest runs yet.</p>
            ) : (
              runs.map((run) => (
                <article key={run.id} className={`bt-run-card ${selectedRun?.id === run.id ? "active" : ""}`}>
                  <button type="button" className="bt-run-main" onClick={() => void loadRunDetail(run.id)}>
                    <div>
                      <strong>
                        #{run.id} {run.strategy_name ?? "Unnamed strategy"}
                      </strong>
                      <p>
                        {run.symbol} · {run.interval} · v{run.version_no ?? "--"}
                      </p>
                      <p>
                        {formatDateLabel(run.start_ts)} to {formatDateLabel(run.end_ts)}
                      </p>
                    </div>
                    <div className="bt-run-meta">
                      <span className={`bt-status ${run.status}`}>{run.status}</span>
                      <span>{formatPct(run.summary.total_return_pct)}</span>
                    </div>
                  </button>
                  <div className="bt-run-foot">
                    <span>Queued {formatDateLabel(run.queued_at)}</span>
                    {(run.status === "queued" || run.status === "running") && (
                      <button
                        type="button"
                        className="bt-inline-btn"
                        onClick={() => void handleCancelRun(run.id)}
                        disabled={cancelingRunId === run.id}
                      >
                        {cancelingRunId === run.id ? <Loader2 size={14} className="spin" /> : <SquareX size={14} />}
                        Cancel
                      </button>
                    )}
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="v2-panel bt-panel">
          <div className="bt-panel-head">
            <div>
              <p className="v2-kicker">Result Viewer</p>
              <h2>Equity, drawdown, trades, and halt diagnostics</h2>
            </div>
            {detailLoading && (
              <div className="bt-inline-tools">
                <Loader2 size={15} className="spin" />
                Loading...
              </div>
            )}
          </div>

          {!selectedRun ? (
            <p className="bt-empty">Select a run to inspect metrics and trade details.</p>
          ) : (
            <>
              <div className="bt-stat-grid">
                {runStats.map((item) => (
                  <div key={item.label} className={`bt-stat-card ${item.tone ?? ""}`}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>

              <div className="bt-chart-stack">
                <div className="bt-chart-card">
                  <div className="bt-chart-head">
                    <strong>Equity Curve</strong>
                    <span>Current-bar close fills, mark-to-market at close</span>
                  </div>
                  <div className="bt-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={equityPoints}>
                        <CartesianGrid stroke="var(--v2-chart-grid)" strokeDasharray="3 3" />
                        <XAxis dataKey="ts" tickFormatter={chartDateLabel} stroke="var(--v2-muted)" />
                        <YAxis stroke="var(--v2-muted)" domain={["auto", "auto"]} />
                        <Tooltip
                          contentStyle={{
                            background: "var(--v2-chart-tooltip-bg)",
                            border: "1px solid var(--v2-chart-tooltip-border)",
                            borderRadius: 12
                          }}
                          labelFormatter={(value) => formatDateLabel(String(value))}
                        />
                        <Line type="monotone" dataKey="equity" stroke="var(--v2-chart-line)" strokeWidth={2.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="bt-chart-card">
                  <div className="bt-chart-head">
                    <strong>Trailing Drawdown</strong>
                    <span>Peak-to-trough drawdown percentage per bar</span>
                  </div>
                  <div className="bt-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart
                        data={equityPoints.map((point) => ({
                          ...point,
                          trailing_drawdown_pct: point.trailing_drawdown_pct * 100
                        }))}
                      >
                        <CartesianGrid stroke="var(--v2-chart-grid)" strokeDasharray="3 3" />
                        <XAxis dataKey="ts" tickFormatter={chartDateLabel} stroke="var(--v2-muted)" />
                        <YAxis stroke="var(--v2-muted)" />
                        <Tooltip
                          contentStyle={{
                            background: "var(--v2-chart-tooltip-bg)",
                            border: "1px solid var(--v2-chart-tooltip-border)",
                            borderRadius: 12
                          }}
                          labelFormatter={(value) => formatDateLabel(String(value))}
                        />
                        <Area type="monotone" dataKey="trailing_drawdown_pct" stroke="#ff6b6b" fill="rgba(255, 107, 107, 0.22)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              <div className="bt-result-footer">
                <div className="bt-run-summary">
                  <p>
                    <strong>Status:</strong> {selectedRun.status}
                  </p>
                  <p>
                    <strong>Final Equity:</strong> {formatNumber(selectedRun.summary.final_equity)}
                  </p>
                  <p>
                    <strong>Halted At:</strong> {formatDateLabel(selectedRun.summary.halted_at ?? null)}
                  </p>
                  {selectedRun.error_message && (
                    <p className="bt-error-inline">
                      <strong>Error:</strong> {selectedRun.error_message}
                    </p>
                  )}
                </div>

                <div className="bt-trade-table-wrap">
                  <table className="bt-trade-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Side</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>Bars</th>
                        <th>Net PnL</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.length === 0 ? (
                        <tr>
                          <td colSpan={7}>No trades recorded yet.</td>
                        </tr>
                      ) : (
                        trades.map((trade) => (
                          <tr key={trade.id}>
                            <td>{trade.trade_no}</td>
                            <td>{trade.side}</td>
                            <td>{formatNumber(trade.entry_price)}</td>
                            <td>{formatNumber(trade.exit_price)}</td>
                            <td>{trade.bars_held}</td>
                            <td className={trade.net_pnl >= 0 ? "positive" : "negative"}>{formatNumber(trade.net_pnl)}</td>
                            <td>{trade.exit_reason}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}

function ClauseEditor({
  clause,
  catalog,
  allowAnySide,
  onChange,
  onRemove
}: {
  clause: ClauseFormState;
  catalog: BacktestCatalog | null;
  allowAnySide: boolean;
  onChange: (patch: Partial<ClauseFormState>) => void;
  onRemove: () => void;
}) {
  const leftFields = catalog?.indicator_fields[clause.leftIndicator] ?? [clause.leftField];
  const rightFields = catalog?.indicator_fields[clause.rightIndicator] ?? [clause.rightField];

  return (
    <div className="bt-clause-card">
      <div className="bt-clause-grid">
        <label className="v2-field">
          <span>Side</span>
          <select value={clause.side} onChange={(event) => onChange({ side: event.target.value as ClauseFormState["side"] })}>
            {!allowAnySide ? null : <option value="any">any</option>}
            <option value="long">long</option>
            <option value="short">short</option>
          </select>
        </label>
        <label className="v2-field">
          <span>Type</span>
          <select
            value={clause.type}
            onChange={(event) =>
              onChange({
                type: event.target.value as ClauseFormState["type"],
                rightKind: event.target.value === "signal_rule" ? "constant" : clause.rightKind
              })
            }
          >
            <option value="signal_rule">signal_rule</option>
            <option value="indicator_compare">indicator_compare</option>
          </select>
        </label>

        {clause.type === "signal_rule" ? (
          <label className="v2-field bt-clause-wide">
            <span>Rule</span>
            <select value={clause.ruleKey} onChange={(event) => onChange({ ruleKey: event.target.value })}>
              {catalog?.signal_rules.map((rule) => (
                <option key={rule} value={rule}>
                  {rule}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <label className="v2-field">
              <span>Left Indicator</span>
              <select value={clause.leftIndicator} onChange={(event) => onChange({ leftIndicator: event.target.value })}>
                {Object.keys(catalog?.indicator_fields ?? {}).map((indicator) => (
                  <option key={indicator} value={indicator}>
                    {indicator}
                  </option>
                ))}
              </select>
            </label>
            <label className="v2-field">
              <span>Left Field</span>
              <select value={clause.leftField} onChange={(event) => onChange({ leftField: event.target.value })}>
                {leftFields.map((field) => (
                  <option key={field} value={field}>
                    {field}
                  </option>
                ))}
              </select>
            </label>
            <label className="v2-field">
              <span>Operator</span>
              <select value={clause.operator} onChange={(event) => onChange({ operator: event.target.value })}>
                {catalog?.operators.map((operator) => (
                  <option key={operator} value={operator}>
                    {operator}
                  </option>
                ))}
              </select>
            </label>
            <label className="v2-field">
              <span>Right Kind</span>
              <select value={clause.rightKind} onChange={(event) => onChange({ rightKind: event.target.value as ClauseFormState["rightKind"] })}>
                <option value="constant">constant</option>
                <option value="field">field</option>
              </select>
            </label>
            {clause.rightKind === "constant" ? (
              <label className="v2-field bt-clause-wide">
                <span>Right Value</span>
                <input value={clause.rightValue} onChange={(event) => onChange({ rightValue: event.target.value })} />
              </label>
            ) : (
              <>
                <label className="v2-field">
                  <span>Right Indicator</span>
                  <select value={clause.rightIndicator} onChange={(event) => onChange({ rightIndicator: event.target.value })}>
                    {Object.keys(catalog?.indicator_fields ?? {}).map((indicator) => (
                      <option key={indicator} value={indicator}>
                        {indicator}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="v2-field">
                  <span>Right Field</span>
                  <select value={clause.rightField} onChange={(event) => onChange({ rightField: event.target.value })}>
                    {rightFields.map((field) => (
                      <option key={field} value={field}>
                        {field}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
          </>
        )}
      </div>
      <button type="button" className="bt-inline-btn danger" onClick={onRemove}>
        Remove
      </button>
    </div>
  );
}
