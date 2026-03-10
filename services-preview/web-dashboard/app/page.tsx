"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChatPanel } from "@/components/dashboard-v2/ChatPanel";
import { Header } from "@/components/dashboard-v2/Header";
import { MarketPanel } from "@/components/dashboard-v2/MarketPanel";
import { MlConsolePanel } from "@/components/dashboard-v2/MlConsolePanel";
import { SignalPanel } from "@/components/dashboard-v2/SignalPanel";
import { formatClock } from "@/components/dashboard-v2/common/format";
import {
  createSignalSocket,
  detectChatLanguage,
  type FetchMeta,
  fetchApiHealth,
  fetchIndicatorRows,
  fetchIndicatorTables,
  fetchMlCandidates,
  fetchMlDriftLatest,
  fetchMlRuntime,
  fetchMlTrainingRuns,
  fetchMlValidationSummary,
  fetchMomentum,
  fetchSignalCooldown,
  fetchSignalRules,
  fetchSignalsLatest,
  fetchTopMovers,
  fetchTrendHistory,
  localizeChatFallbackText,
  resolveRuntimeEndpoints,
  sendChatMessage
} from "@/lib/live-data";
import type {
  ChatContextState,
  ChatMessage,
  ChatResponseMode,
  CooldownItem,
  DashboardFetchState,
  IndicatorRow,
  MarketPulse,
  MlCandidateFilterStatus,
  MlCandidateRow,
  MlDriftSnapshot,
  MlFeatureCatalogItem,
  MlRuntimeState,
  MlTrainingRun,
  MlValidationStatus,
  MlValidationSummary,
  MomentumSnapshot,
  SignalBoardMode,
  SignalEvent,
  SignalRuleItem,
  TopMoverItem,
  TopMoverOrder,
  TrendPoint
} from "@/types/legacy-dashboard";

const SIGNAL_WINDOW_SIZE = 120;
const RATE_LIMIT_HOLD_MS = 30_000;
const AUTO_PAUSE_AFTER_MANUAL_REFRESH_MS = 8_000;
const TREND_STAGGER_MS = 2_500;
const ML_SHORT_STAGGER_MS = 5_500;
const ML_LONG_STAGGER_MS = 10_000;
const RETRY_FALLBACK_MS = 5_000;

type RefreshGroupKey = "core" | "trend" | "indicator" | "mlShort" | "mlLong" | "signalFallback";

const FEATURE_CATALOG: MlFeatureCatalogItem[] = [
  { name: "rsi_current", group: "RSI", description: "Current RSI14 value" },
  { name: "rsi_previous", group: "RSI", description: "Previous RSI14 value" },
  { name: "rsi_delta", group: "RSI", description: "Delta between RSI bars" },
  { name: "ema20_ema50_gap", group: "EMA", description: "EMA20 and EMA50 gap" },
  { name: "ema50_ema200_gap", group: "EMA", description: "EMA50 and EMA200 gap" },
  { name: "macd", group: "MACD", description: "MACD value" },
  { name: "signal", group: "MACD", description: "MACD signal line" },
  { name: "hist", group: "MACD", description: "MACD histogram" },
  { name: "atr14_norm", group: "Volatility", description: "Normalized ATR14" },
  { name: "ret_vol_6", group: "Volatility", description: "6-bar return volatility" },
  { name: "donchian_pos", group: "Channel", description: "Position in Donchian channel" },
  { name: "bb_width", group: "Channel", description: "Bollinger band width" },
  { name: "price_to_vwap", group: "Position", description: "Distance from VWAP" },
  { name: "price_to_cloud_top", group: "Ichimoku", description: "Distance from cloud top" },
  { name: "ret_1", group: "Returns", description: "1-bar return" },
  { name: "ret_3", group: "Returns", description: "3-bar return" },
  { name: "ret_6", group: "Returns", description: "6-bar return" },
  { name: "volume_z_6", group: "Volume", description: "Volume z-score over 6 bars" },
  { name: "direction_long", group: "Context", description: "Direction one-hot feature" },
  { name: "hour_of_day", group: "Context", description: "Hour feature" },
  { name: "day_of_week", group: "Context", description: "Weekday feature" },
  { name: "cooldown_seconds", group: "Context", description: "Rule cooldown seconds" }
];

function nowLabel(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function normalizeSymbol(raw: string): string {
  const symbol = raw.trim().toUpperCase();
  if (!symbol) {
    return "";
  }
  return symbol.endsWith("USDT") ? symbol : `${symbol}USDT`;
}

function mergeSignalEvents(current: SignalEvent[], incoming: SignalEvent[]): SignalEvent[] {
  const map = new Map<number, SignalEvent>();
  for (const item of current) {
    map.set(item.id, item);
  }
  for (const item of incoming) {
    map.set(item.id, item);
  }
  return [...map.values()]
    .sort((a, b) => b.id - a.id)
    .slice(0, SIGNAL_WINDOW_SIZE);
}

function buildMarketPulse(
  momentum: MomentumSnapshot | null,
  signalEvents: SignalEvent[],
  trendMap: Record<string, TrendPoint[]>,
  trackedSymbols: string[]
): MarketPulse {
  const breadthText = momentum ? `${momentum.upCount}/${momentum.total}` : "--";

  const directionRows = trackedSymbols
    .map((symbol) => {
      const points = trendMap[symbol] ?? [];
      if (points.length < 2) {
        return 0;
      }
      return points[points.length - 1].close - points[0].close;
    })
    .filter((value) => value !== 0);

  const positive = directionRows.filter((value) => value > 0).length;
  const alignmentPct = directionRows.length > 0 ? (positive / directionRows.length) * 100 : 0;

  let riskLabel: MarketPulse["riskLabel"] = "mixed";
  if (alignmentPct >= 66) {
    riskLabel = "risk-on";
  } else if (alignmentPct <= 33) {
    riskLabel = "risk-off";
  }

  return {
    breadthText,
    signalDensity: signalEvents.length,
    alignmentPct,
    riskLabel
  };
}

export default function DashboardV2Page() {
  const endpoints = useMemo(() => resolveRuntimeEndpoints(), []);

  const [apiOk, setApiOk] = useState(false);
  const [dataOk, setDataOk] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [mlOk, setMlOk] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [refreshingAll, setRefreshingAll] = useState(false);
  const [refreshingMl, setRefreshingMl] = useState(false);

  const [selectedSymbol, setSelectedSymbol] = useState(endpoints.defaultSymbol);
  const [trendInterval, setTrendInterval] = useState(endpoints.defaultInterval);
  const [topMoverOrder, setTopMoverOrder] = useState<TopMoverOrder>("abs");

  const [momentum, setMomentum] = useState<MomentumSnapshot | null>(null);
  const [topMovers, setTopMovers] = useState<TopMoverItem[]>([]);
  const [signalEvents, setSignalEvents] = useState<SignalEvent[]>([]);
  const [signalMode, setSignalMode] = useState<SignalBoardMode>("events");
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [signalRules, setSignalRules] = useState<SignalRuleItem[]>([]);
  const [cooldownRows, setCooldownRows] = useState<CooldownItem[]>([]);

  const [trendMap, setTrendMap] = useState<Record<string, TrendPoint[]>>({});

  const [indicatorTables, setIndicatorTables] = useState<string[]>([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [indicatorRows, setIndicatorRows] = useState<IndicatorRow[]>([]);

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "已连接。直接问我方向、关键位和失效条件就行。",
      timeLabel: nowLabel()
    }
  ]);
  const [chatPending, setChatPending] = useState(false);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);

  const [mlRuntime, setMlRuntime] = useState<MlRuntimeState | null>(null);
  const [mlSummary, setMlSummary] = useState<MlValidationSummary | null>(null);
  const [mlCandidates, setMlCandidates] = useState<MlCandidateRow[]>([]);
  const [mlTrainingRuns, setMlTrainingRuns] = useState<MlTrainingRun[]>([]);
  const [mlDriftRows, setMlDriftRows] = useState<MlDriftSnapshot[]>([]);
  const [mlStatusFilter, setMlStatusFilter] = useState<MlCandidateFilterStatus>("all");
  const [mlSymbolFilter, setMlSymbolFilter] = useState<string>(selectedSymbol);
  const [mlIntervalFilter, setMlIntervalFilter] = useState<string>(trendInterval);
  const [mlFollowSelection, setMlFollowSelection] = useState(true);

  const [fetchStates, setFetchStates] = useState<Record<string, DashboardFetchState>>({});
  const [rateLimited, setRateLimited] = useState(false);
  const [bootstrapped, setBootstrapped] = useState(false);

  const chatMessagesRef = useRef<ChatMessage[]>(chatMessages);
  const sinceIdRef = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const unmountedRef = useRef(false);
  const generationRef = useRef(0);
  const wsConnectionIdRef = useRef(0);
  const wsReconnectEnabledRef = useRef(true);
  const wsConnectedRef = useRef(false);
  const autoPauseUntilRef = useRef(0);
  const rateLimitedUntilRef = useRef(0);
  const bootstrapTimeoutsRef = useRef<number[]>([]);
  const mlRuntimeRef = useRef<MlRuntimeState | null>(null);
  const mlSummaryRef = useRef<MlValidationSummary | null>(null);
  const nextAllowedAtRef = useRef<Record<RefreshGroupKey, number>>({
    core: 0,
    trend: 0,
    indicator: 0,
    mlShort: 0,
    mlLong: 0,
    signalFallback: 0
  });
  const skipReactiveRefreshRef = useRef({
    core: true,
    trend: true,
    indicator: true,
    mlShort: true
  });
  const inFlightRef = useRef({
    core: false,
    trend: false,
    indicator: false,
    mlShort: false,
    mlLong: false,
    signalFallback: false
  });

  useEffect(() => {
    chatMessagesRef.current = chatMessages;
  }, [chatMessages]);

  useEffect(() => {
    wsConnectedRef.current = wsConnected;
  }, [wsConnected]);

  useEffect(() => {
    mlRuntimeRef.current = mlRuntime;
  }, [mlRuntime]);

  useEffect(() => {
    mlSummaryRef.current = mlSummary;
  }, [mlSummary]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (rateLimitedUntilRef.current > 0 && Date.now() >= rateLimitedUntilRef.current) {
        setRateLimited(false);
      }
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const watchSymbols = useMemo(() => {
    return [...new Set([selectedSymbol, ...endpoints.trendSymbols.map((item) => normalizeSymbol(item)).filter(Boolean)])];
  }, [endpoints.trendSymbols, selectedSymbol]);

  const symbolOptions = useMemo(() => {
    return [...new Set([...watchSymbols, ...topMovers.map((item) => item.symbol), ...signalEvents.map((item) => item.symbol)])]
      .filter(Boolean)
      .sort();
  }, [signalEvents, topMovers, watchSymbols]);

  const activeSignal = useMemo(() => {
    return signalEvents.find((event) => event.symbol === selectedSymbol && event.interval === trendInterval) ?? signalEvents[0] ?? null;
  }, [selectedSymbol, signalEvents, trendInterval]);

  const chatContext = useMemo<ChatContextState>(
    () => ({
      symbol: selectedSymbol,
      interval: trendInterval,
      activeRule: activeSignal?.ruleKey ?? null,
      mlDecision: (activeSignal?.mlValidation?.decision as MlValidationStatus | undefined) ?? null
    }),
    [activeSignal, selectedSymbol, trendInterval]
  );

  const pulse = useMemo(() => buildMarketPulse(momentum, signalEvents, trendMap, watchSymbols), [momentum, signalEvents, trendMap, watchSymbols]);

  const isGenerationActive = useCallback((generation: number) => {
    return !unmountedRef.current && generationRef.current === generation;
  }, []);

  const shouldSkipAutoRefresh = useCallback(() => Date.now() < autoPauseUntilRef.current, []);

  const shouldBackoffRefresh = useCallback((key: RefreshGroupKey) => {
    return Date.now() < nextAllowedAtRef.current[key];
  }, []);

  const applyRefreshBackoff = useCallback((key: RefreshGroupKey, retryAfterMs: number | null) => {
    const delayMs = retryAfterMs && retryAfterMs > 0 ? retryAfterMs : RETRY_FALLBACK_MS;
    nextAllowedAtRef.current[key] = Math.max(nextAllowedAtRef.current[key], Date.now() + delayMs);
  }, []);

  const pauseAutoRefresh = useCallback((durationMs = AUTO_PAUSE_AFTER_MANUAL_REFRESH_MS) => {
    autoPauseUntilRef.current = Date.now() + durationMs;
  }, []);

  const registerFetchMeta = useCallback((key: string, meta: FetchMeta) => {
    if (unmountedRef.current) {
      return;
    }

    const now = Date.now();
    setFetchStates((current) => {
      const previous = current[key];
      return {
        ...current,
        [key]: {
          rateLimited: meta.rateLimited,
          degraded: meta.degraded,
          lastSuccessAt: meta.ok ? now : previous?.lastSuccessAt ?? null,
          lastStatusCode: meta.httpStatus
        }
      };
    });

    if (meta.rateLimited) {
      rateLimitedUntilRef.current = Math.max(rateLimitedUntilRef.current, now + RATE_LIMIT_HOLD_MS);
      setRateLimited(true);
    }
  }, []);

  const applySignals = useCallback(
    (incoming: SignalEvent[], generation = generationRef.current) => {
      if (incoming.length === 0 || !isGenerationActive(generation)) {
        return;
      }

      setSignalEvents((current) => {
        const merged = mergeSignalEvents(current, incoming);
        sinceIdRef.current = Math.max(sinceIdRef.current, merged[0]?.id ?? 0);
        return merged;
      });

      setDataOk(true);
      setUpdatedAt(Date.now());
    },
    [isGenerationActive]
  );

  const refreshCoreData = useCallback(
    async (generation = generationRef.current) => {
      if (inFlightRef.current.core || shouldBackoffRefresh("core")) {
        return;
      }
      inFlightRef.current.core = true;

      let healthOk = false;
      let momentumOk = false;
      let moversOk = false;
      let rulesOk = false;
      let cooldownOk = false;
      let tableOk = false;
      let retryAfterMs: number | null = null;

      try {
        const [health, momentumData, moversData, rulesData, cooldownData, tableData] = await Promise.all([
          fetchApiHealth(endpoints.apiBase, (meta) => {
            healthOk = meta.ok;
            registerFetchMeta("health", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }),
          fetchMomentum(endpoints.apiBase, endpoints.defaultExchange, (meta) => {
            momentumOk = meta.ok;
            registerFetchMeta("momentum", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }),
          fetchTopMovers(endpoints.apiBase, topMoverOrder, endpoints.defaultExchange, 20, (meta) => {
            moversOk = meta.ok;
            registerFetchMeta("topMovers", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }),
          fetchSignalRules(endpoints.apiBase, (meta) => {
            rulesOk = meta.ok;
            registerFetchMeta("signalRules", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }),
          fetchSignalCooldown(endpoints.apiBase, 12, (meta) => {
            cooldownOk = meta.ok;
            registerFetchMeta("signalCooldown", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }),
          fetchIndicatorTables(endpoints.apiBase, (meta) => {
            tableOk = meta.ok;
            registerFetchMeta("indicatorTables", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          })
        ]);

        if (!isGenerationActive(generation)) {
          return;
        }

        setApiOk(Boolean(healthOk && health));

        if (moversOk) {
          setTopMovers(moversData);
        }
        if (rulesOk) {
          setSignalRules(rulesData);
        }
        if (cooldownOk) {
          setCooldownRows(cooldownData);
        }
        if (tableOk && tableData.length > 0) {
          setIndicatorTables(tableData);
          setSelectedTable((current) => current || tableData[0]);
        }
        if (momentumOk) {
          setMomentum(momentumData);
          if (momentumData) {
            setDataOk(true);
            setUpdatedAt(momentumData.timestamp ?? Date.now());
          }
        }
      } finally {
        if (retryAfterMs !== null) {
          applyRefreshBackoff("core", retryAfterMs);
        }
        inFlightRef.current.core = false;
      }
    },
    [applyRefreshBackoff, endpoints.apiBase, endpoints.defaultExchange, isGenerationActive, registerFetchMeta, shouldBackoffRefresh, topMoverOrder]
  );

  const refreshTrendData = useCallback(
    async (generation = generationRef.current) => {
      if (inFlightRef.current.trend || shouldBackoffRefresh("trend")) {
        return;
      }
      inFlightRef.current.trend = true;
      let retryAfterMs: number | null = null;

      try {
        const rows = await Promise.all(
          watchSymbols.map(async (symbol) => {
            let trendOk = false;
            const points = await fetchTrendHistory(endpoints.apiBase, symbol, trendInterval, endpoints.defaultExchange, 90, (meta) => {
              trendOk = meta.ok;
              registerFetchMeta("trend", meta);
              if (meta.rateLimited) {
                retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
              }
            });
            return { symbol, points, ok: trendOk };
          })
        );

        if (!isGenerationActive(generation)) {
          return;
        }

        setTrendMap((current) => {
          const nextMap = { ...current };
          for (const row of rows) {
            if (row.ok) {
              nextMap[row.symbol] = row.points;
            }
          }
          return nextMap;
        });

        if (rows.some((row) => row.ok && row.points.length > 0)) {
          setDataOk(true);
          setUpdatedAt(Date.now());
        }
      } finally {
        if (retryAfterMs !== null) {
          applyRefreshBackoff("trend", retryAfterMs);
        }
        inFlightRef.current.trend = false;
      }
    },
    [applyRefreshBackoff, endpoints.apiBase, endpoints.defaultExchange, isGenerationActive, registerFetchMeta, shouldBackoffRefresh, trendInterval, watchSymbols]
  );

  const refreshIndicatorData = useCallback(
    async (generation = generationRef.current) => {
      if (inFlightRef.current.indicator || !selectedTable || shouldBackoffRefresh("indicator")) {
        return;
      }
      inFlightRef.current.indicator = true;

      let indicatorOk = false;
      let retryAfterMs: number | null = null;
      try {
        const rows = await fetchIndicatorRows(endpoints.apiBase, selectedTable, selectedSymbol, trendInterval, 40, (meta) => {
          indicatorOk = meta.ok;
          registerFetchMeta("indicatorData", meta);
          if (meta.rateLimited) {
            retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
          }
        });

        if (!isGenerationActive(generation)) {
          return;
        }

        if (indicatorOk) {
          setIndicatorRows(rows);
        }
      } finally {
        if (retryAfterMs !== null) {
          applyRefreshBackoff("indicator", retryAfterMs);
        }
        inFlightRef.current.indicator = false;
      }
    },
    [applyRefreshBackoff, endpoints.apiBase, isGenerationActive, registerFetchMeta, selectedSymbol, selectedTable, shouldBackoffRefresh, trendInterval]
  );

  const refreshMlShortData = useCallback(
    async (generation = generationRef.current) => {
      if (inFlightRef.current.mlShort || shouldBackoffRefresh("mlShort")) {
        return;
      }
      inFlightRef.current.mlShort = true;
      setRefreshingMl(true);

      let runtimeOk = false;
      let summaryOk = false;
      let candidatesOk = false;
      let retryAfterMs: number | null = null;

      try {
        const [runtimeData, summaryData, candidateData] = await Promise.all([
          fetchMlRuntime(endpoints.apiBase, (meta) => {
            runtimeOk = meta.ok;
            registerFetchMeta("mlRuntime", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }),
          fetchMlValidationSummary(endpoints.apiBase, "7d", (meta) => {
            summaryOk = meta.ok;
            registerFetchMeta("mlSummary", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }),
          fetchMlCandidates(
            endpoints.apiBase,
            {
              limit: 24,
              status: mlStatusFilter === "all" ? undefined : mlStatusFilter,
              symbol: mlSymbolFilter === "all" ? undefined : mlSymbolFilter,
              interval: mlIntervalFilter === "all" ? undefined : mlIntervalFilter
            },
            (meta) => {
              candidatesOk = meta.ok;
              registerFetchMeta("mlCandidates", meta);
              if (meta.rateLimited) {
                retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
              }
            }
          )
        ]);

        if (!isGenerationActive(generation)) {
          return;
        }

        let runtimeForReady = mlRuntimeRef.current;
        let summaryForReady = mlSummaryRef.current;

        if (runtimeOk) {
          runtimeForReady = runtimeData;
          setMlRuntime(runtimeData);
        }
        if (summaryOk) {
          summaryForReady = summaryData;
          setMlSummary(summaryData);
        }
        if (candidatesOk) {
          setMlCandidates(candidateData);
        }

        setMlOk(Boolean(runtimeForReady) || Boolean(summaryForReady));
      } finally {
        if (isGenerationActive(generation)) {
          setRefreshingMl(false);
        }
        if (retryAfterMs !== null) {
          applyRefreshBackoff("mlShort", retryAfterMs);
        }
        inFlightRef.current.mlShort = false;
      }
    },
    [
      applyRefreshBackoff,
      endpoints.apiBase,
      isGenerationActive,
      mlIntervalFilter,
      mlStatusFilter,
      mlSymbolFilter,
      registerFetchMeta,
      shouldBackoffRefresh
    ]
  );

  const refreshMlLongData = useCallback(
    async (generation = generationRef.current) => {
      if (inFlightRef.current.mlLong || shouldBackoffRefresh("mlLong")) {
        return;
      }
      inFlightRef.current.mlLong = true;

      let runOk = false;
      let driftOk = false;
      let retryAfterMs: number | null = null;
      try {
        const [runs, drift] = await Promise.all([
          fetchMlTrainingRuns(endpoints.apiBase, 12, (meta) => {
            runOk = meta.ok;
            registerFetchMeta("mlTrainingRuns", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }),
          fetchMlDriftLatest(endpoints.apiBase, 12, (meta) => {
            driftOk = meta.ok;
            registerFetchMeta("mlDrift", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          })
        ]);

        if (!isGenerationActive(generation)) {
          return;
        }

        if (runOk) {
          setMlTrainingRuns(runs);
        }
        if (driftOk) {
          setMlDriftRows(drift);
        }
      } finally {
        if (retryAfterMs !== null) {
          applyRefreshBackoff("mlLong", retryAfterMs);
        }
        inFlightRef.current.mlLong = false;
      }
    },
    [applyRefreshBackoff, endpoints.apiBase, isGenerationActive, registerFetchMeta, shouldBackoffRefresh]
  );

  const refreshSignalFallback = useCallback(
    async (generation = generationRef.current) => {
      if (inFlightRef.current.signalFallback || shouldBackoffRefresh("signalFallback")) {
        return;
      }
      inFlightRef.current.signalFallback = true;

      let signalOk = false;
      let retryAfterMs: number | null = null;
      try {
        const rows = await fetchSignalsLatest(
          endpoints.apiBase,
          SIGNAL_WINDOW_SIZE,
          {},
          (meta) => {
            signalOk = meta.ok;
            registerFetchMeta("signalsLatest", meta);
            if (meta.rateLimited) {
              retryAfterMs = Math.max(retryAfterMs ?? 0, meta.retryAfterMs ?? RETRY_FALLBACK_MS);
            }
          }
        );
        if (signalOk) {
          applySignals(rows, generation);
        }
      } finally {
        if (retryAfterMs !== null) {
          applyRefreshBackoff("signalFallback", retryAfterMs);
        }
        inFlightRef.current.signalFallback = false;
      }
    },
    [applyRefreshBackoff, applySignals, endpoints.apiBase, registerFetchMeta, shouldBackoffRefresh]
  );

  const connectSignalWs = useCallback(
    (generation = generationRef.current) => {
      if (!isGenerationActive(generation)) {
        return;
      }

      wsReconnectEnabledRef.current = true;
      wsConnectionIdRef.current += 1;
      const connectionId = wsConnectionIdRef.current;

      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }

      const socket = createSignalSocket(
        endpoints.signalWsUrl,
        sinceIdRef.current,
        (event) => {
          if (!isGenerationActive(generation) || wsConnectionIdRef.current !== connectionId) {
            return;
          }
          applySignals([event], generation);
        },
        (connected) => {
          if (!isGenerationActive(generation) || wsConnectionIdRef.current !== connectionId) {
            return;
          }

          wsConnectedRef.current = connected;
          setWsConnected(connected);
          if (!connected && wsReconnectEnabledRef.current) {
            if (reconnectTimerRef.current) {
              window.clearTimeout(reconnectTimerRef.current);
            }
            reconnectTimerRef.current = window.setTimeout(() => {
              if (!wsReconnectEnabledRef.current || !isGenerationActive(generation)) {
                return;
              }
              connectSignalWs(generation);
            }, 2500);
          }
        }
      );

      socketRef.current = socket;
    },
    [applySignals, endpoints.signalWsUrl, isGenerationActive]
  );

  const refreshAll = useCallback(async () => {
    const generation = generationRef.current;
    pauseAutoRefresh();
    setRefreshingAll(true);
    await Promise.all([
      refreshCoreData(generation),
      refreshTrendData(generation),
      refreshIndicatorData(generation),
      refreshSignalFallback(generation),
      refreshMlShortData(generation),
      refreshMlLongData(generation)
    ]);
    if (isGenerationActive(generation)) {
      setRefreshingAll(false);
    }
  }, [isGenerationActive, pauseAutoRefresh, refreshCoreData, refreshIndicatorData, refreshMlLongData, refreshMlShortData, refreshSignalFallback, refreshTrendData]);

  useEffect(() => {
    if (!mlFollowSelection) {
      return;
    }
    setMlSymbolFilter(selectedSymbol);
  }, [mlFollowSelection, selectedSymbol]);

  useEffect(() => {
    if (!mlFollowSelection) {
      return;
    }
    setMlIntervalFilter(trendInterval);
  }, [mlFollowSelection, trendInterval]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    if (skipReactiveRefreshRef.current.core) {
      skipReactiveRefreshRef.current.core = false;
      return;
    }
    void refreshCoreData(generationRef.current);
  }, [bootstrapped, refreshCoreData, topMoverOrder]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    if (skipReactiveRefreshRef.current.trend) {
      skipReactiveRefreshRef.current.trend = false;
      return;
    }
    void refreshTrendData(generationRef.current);
  }, [bootstrapped, refreshTrendData, trendInterval, watchSymbols]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    if (skipReactiveRefreshRef.current.indicator) {
      skipReactiveRefreshRef.current.indicator = false;
      return;
    }
    void refreshIndicatorData(generationRef.current);
  }, [bootstrapped, refreshIndicatorData, selectedSymbol, selectedTable, trendInterval]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    if (skipReactiveRefreshRef.current.mlShort) {
      skipReactiveRefreshRef.current.mlShort = false;
      return;
    }
    void refreshMlShortData(generationRef.current);
  }, [bootstrapped, mlIntervalFilter, mlStatusFilter, mlSymbolFilter, refreshMlShortData]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    let intervalId: number | null = null;
    const timeoutId = window.setTimeout(() => {
      intervalId = window.setInterval(() => {
        if (shouldSkipAutoRefresh()) {
          return;
        }
        void refreshCoreData(generationRef.current);
      }, endpoints.refreshIntervalMs);
    }, 0);

    return () => {
      window.clearTimeout(timeoutId);
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [bootstrapped, endpoints.refreshIntervalMs, refreshCoreData, shouldSkipAutoRefresh]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    let intervalId: number | null = null;
    const timeoutId = window.setTimeout(() => {
      intervalId = window.setInterval(() => {
        if (shouldSkipAutoRefresh()) {
          return;
        }
        void refreshTrendData(generationRef.current);
        void refreshIndicatorData(generationRef.current);
      }, endpoints.refreshIntervalMs);
    }, TREND_STAGGER_MS);

    return () => {
      window.clearTimeout(timeoutId);
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [bootstrapped, endpoints.refreshIntervalMs, refreshIndicatorData, refreshTrendData, shouldSkipAutoRefresh]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    let intervalId: number | null = null;
    const timeoutId = window.setTimeout(() => {
      intervalId = window.setInterval(() => {
        if (shouldSkipAutoRefresh()) {
          return;
        }
        void refreshMlShortData(generationRef.current);
      }, endpoints.refreshIntervalMs);
    }, ML_SHORT_STAGGER_MS);

    return () => {
      window.clearTimeout(timeoutId);
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [bootstrapped, endpoints.refreshIntervalMs, refreshMlShortData, shouldSkipAutoRefresh]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    let intervalId: number | null = null;
    const timeoutId = window.setTimeout(() => {
      intervalId = window.setInterval(() => {
        if (shouldSkipAutoRefresh()) {
          return;
        }
        void refreshMlLongData(generationRef.current);
      }, 60000);
    }, ML_LONG_STAGGER_MS);

    return () => {
      window.clearTimeout(timeoutId);
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [bootstrapped, refreshMlLongData, shouldSkipAutoRefresh]);

  useEffect(() => {
    if (!bootstrapped) {
      return;
    }
    const intervalId = window.setInterval(() => {
      if (shouldSkipAutoRefresh() || wsConnectedRef.current) {
        return;
      }
      void refreshSignalFallback(generationRef.current);
    }, 15000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [bootstrapped, refreshSignalFallback, shouldSkipAutoRefresh]);

  useEffect(() => {
    unmountedRef.current = false;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    wsReconnectEnabledRef.current = true;
    setBootstrapped(false);
    skipReactiveRefreshRef.current = {
      core: true,
      trend: true,
      indicator: true,
      mlShort: true
    };
    for (const timeoutId of bootstrapTimeoutsRef.current) {
      window.clearTimeout(timeoutId);
    }
    bootstrapTimeoutsRef.current = [];

    const bootstrap = async () => {
      await Promise.all([refreshCoreData(generation), refreshSignalFallback(generation)]);
      if (!isGenerationActive(generation)) {
        return;
      }
      connectSignalWs(generation);
      setBootstrapped(true);

      const scheduleBootstrapRefresh = (delayMs: number, task: () => void) => {
        const timeoutId = window.setTimeout(() => {
          if (!isGenerationActive(generation)) {
            return;
          }
          task();
        }, delayMs);
        bootstrapTimeoutsRef.current.push(timeoutId);
      };

      scheduleBootstrapRefresh(TREND_STAGGER_MS, () => {
        void refreshTrendData(generation);
        void refreshIndicatorData(generation);
      });
      scheduleBootstrapRefresh(ML_SHORT_STAGGER_MS, () => {
        void refreshMlShortData(generation);
      });
      scheduleBootstrapRefresh(ML_LONG_STAGGER_MS, () => {
        void refreshMlLongData(generation);
      });
    };

    void bootstrap();

    return () => {
      unmountedRef.current = true;
      wsReconnectEnabledRef.current = false;
      wsConnectionIdRef.current += 1;
      setWsConnected(false);
      wsConnectedRef.current = false;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      for (const timeoutId of bootstrapTimeoutsRef.current) {
        window.clearTimeout(timeoutId);
      }
      bootstrapTimeoutsRef.current = [];
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      setBootstrapped(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSendChat = useCallback(
    async (text: string, mode: ChatResponseMode) => {
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: text,
        timeLabel: nowLabel()
      };
      setChatMessages((current) => [...current, userMessage]);
      setChatPending(true);

      try {
        const history = chatMessagesRef.current.slice(-8).map((item) => ({ role: item.role, content: item.content }));
        const reply = await sendChatMessage(endpoints.chatBase, text, {
          sessionId: chatSessionId ?? undefined,
          history,
          symbol: chatContext.symbol,
          interval: chatContext.interval,
          activeRule: chatContext.activeRule,
          mlDecision: chatContext.mlDecision,
          requestedMode: mode
        });

        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: reply.text,
          renderPayload: reply.renderPayload,
          degradedReason: reply.degradedReason,
          timeLabel: nowLabel()
        };

        if (!unmountedRef.current) {
          if (reply.sessionId) {
            setChatSessionId(reply.sessionId);
          }
          setChatMessages((current) => [...current, assistantMessage]);
        }
      } catch {
        const replyLanguage = detectChatLanguage(text);
        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: localizeChatFallbackText(replyLanguage, "service_unavailable"),
          degradedReason: "service_unavailable",
          timeLabel: nowLabel()
        };
        if (!unmountedRef.current) {
          setChatMessages((current) => [...current, assistantMessage]);
        }
      } finally {
        if (!unmountedRef.current) {
          setChatPending(false);
        }
      }
    },
    [chatContext, chatSessionId, endpoints.chatBase]
  );

  return (
    <div className="v2-shell">
      <div className="v2-ambient" aria-hidden="true" />

      <Header
        symbolOptions={symbolOptions}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(symbol) => {
          const normalized = normalizeSymbol(symbol);
          if (normalized) {
            setSelectedSymbol(normalized);
          }
        }}
        interval={trendInterval}
        onIntervalChange={setTrendInterval}
        apiOk={apiOk}
        dataOk={dataOk}
        wsConnected={wsConnected}
        mlOk={mlOk}
        rateLimited={rateLimited}
        updatedAtLabel={formatClock(updatedAt)}
        onRefresh={() => {
          void refreshAll();
        }}
        refreshing={refreshingAll}
      />

      <main className="v2-content">
        <section className="v2-main-grid">
          <MarketPanel
            momentum={momentum}
            pulse={pulse}
            topMovers={topMovers}
            topMoverOrder={topMoverOrder}
            onTopMoverOrderChange={setTopMoverOrder}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={setSelectedSymbol}
            trendInterval={trendInterval}
            trendSymbols={watchSymbols}
            trendMap={trendMap}
            indicatorTables={indicatorTables}
            selectedTable={selectedTable}
            onSelectedTableChange={setSelectedTable}
            indicatorRows={indicatorRows}
            updatedAtLabel={formatClock(updatedAt)}
          />

          <SignalPanel
            events={signalEvents}
            mode={signalMode}
            onModeChange={setSignalMode}
            signalRules={signalRules}
            cooldownRows={cooldownRows}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={(symbol) => {
              setSelectedSymbol(symbol);
            }}
            selectedEventId={selectedEventId}
            onSelectEventId={setSelectedEventId}
          />

          <ChatPanel messages={chatMessages} pending={chatPending} context={chatContext} onSend={handleSendChat} />
        </section>

        <MlConsolePanel
          runtime={mlRuntime}
          summary={mlSummary}
          candidates={mlCandidates}
          trainingRuns={mlTrainingRuns}
          driftRows={mlDriftRows}
          featureCatalog={FEATURE_CATALOG}
          statusFilter={mlStatusFilter}
          onStatusFilterChange={setMlStatusFilter}
          symbolFilter={mlSymbolFilter}
          onSymbolFilterChange={setMlSymbolFilter}
          intervalFilter={mlIntervalFilter}
          onIntervalFilterChange={setMlIntervalFilter}
          followSelection={mlFollowSelection}
          onFollowSelectionChange={setMlFollowSelection}
          symbolOptions={symbolOptions}
          candidateFetchState={fetchStates.mlCandidates}
          trainingFetchState={fetchStates.mlTrainingRuns}
          driftFetchState={fetchStates.mlDrift}
          onShowAllCandidates={() => {
            setMlFollowSelection(false);
            setMlStatusFilter("all");
            setMlSymbolFilter("all");
            setMlIntervalFilter("all");
          }}
          onRefresh={() => {
            void refreshMlShortData(generationRef.current);
            void refreshMlLongData(generationRef.current);
          }}
          refreshing={refreshingMl}
        />
      </main>
    </div>
  );
}
