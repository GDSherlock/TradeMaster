import type {
  CooldownItem,
  IndicatorRow,
  MlCandidateRow,
  MlDriftSnapshot,
  MlRuntimeState,
  MlTrainingRun,
  MlValidationBadge,
  MlValidationStatus,
  MlValidationSummary,
  MomentumSnapshot,
  RuntimeEndpoints,
  SignalEvent,
  SignalRuleItem,
  TopMoverItem,
  TopMoverOrder,
  TrendPoint
} from "@/types/legacy-dashboard";

type ApiEnvelope<T> = {
  success?: boolean;
  code?: string;
  data?: T;
};

export type FetchMeta = {
  ok: boolean;
  httpStatus: number | null;
  rateLimited: boolean;
  degraded: boolean;
  retryAfterMs: number | null;
};

type FetchPayload<T> = {
  data: T | null;
  meta: FetchMeta;
};

type FetchMetaListener = (meta: FetchMeta) => void;

const VALID_ML_STATUS: Set<MlValidationStatus> = new Set(["pending", "passed", "review", "rejected", "unavailable"]);

function unwrapEnvelope<T>(payload: unknown): { ok: boolean; data: T | null } {
  if (!payload || typeof payload !== "object") {
    return { ok: false, data: null };
  }
  const maybeWrapped = payload as ApiEnvelope<T>;
  if (Object.prototype.hasOwnProperty.call(maybeWrapped, "data")) {
    if (maybeWrapped.success === false) {
      return { ok: false, data: null };
    }
    if (maybeWrapped.code && maybeWrapped.code !== "0") {
      return { ok: false, data: null };
    }
    return { ok: true, data: maybeWrapped.data ?? null };
  }
  return { ok: true, data: payload as T };
}

function parseRetryAfterMs(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const numeric = Number(value);
  if (Number.isFinite(numeric) && numeric >= 0) {
    return Math.round(numeric * 1000);
  }
  const dateTs = Date.parse(value);
  if (Number.isNaN(dateTs)) {
    return null;
  }
  return Math.max(0, dateTs - Date.now());
}

function toNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toNullableNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toMlStatus(value: unknown): MlValidationStatus {
  const normalized = String(value ?? "pending") as MlValidationStatus;
  return VALID_ML_STATUS.has(normalized) ? normalized : "pending";
}

function normalizeMlValidation(raw: unknown): MlValidationBadge | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const row = raw as Record<string, unknown>;
  return {
    modelName: String(row.model_name ?? ""),
    modelVersion: String(row.model_version ?? ""),
    probability: toNumber(row.probability, 0),
    threshold: toNumber(row.threshold, 0),
    decision: toMlStatus(row.decision),
    reason: String(row.reason ?? ""),
    topFeatures: Array.isArray(row.top_features)
      ? row.top_features
          .map((item) => {
            if (!item || typeof item !== "object") {
              return null;
            }
            const feature = item as Record<string, unknown>;
            return {
              name: String(feature.name ?? ""),
              value: toNumber(feature.value, 0)
            };
          })
          .filter((item): item is { name: string; value: number } => Boolean(item?.name))
      : [],
    validatedAt: row.validated_at ? String(row.validated_at) : null
  };
}

function normalizeSignalEvent(row: Record<string, unknown>): SignalEvent {
  return {
    id: toNumber(row.id, 0),
    symbol: String(row.symbol ?? "UNKNOWN"),
    interval: String(row.interval ?? "1h"),
    ruleKey: String(row.rule_key ?? "unlabeled"),
    direction: String(row.direction ?? "neutral"),
    score: toNumber(row.score, 0),
    detail: String(row.detail ?? ""),
    detectedAt: String(row.detected_at ?? ""),
    cooldownSeconds: toNumber(row.cooldown_seconds, 0),
    cooldownLeftSeconds: toNumber(row.cooldown_left_seconds, 0),
    mlValidation: normalizeMlValidation(row.ml_validation)
  };
}

export function resolveRuntimeEndpoints(): RuntimeEndpoints {
  const rawHost = typeof window !== "undefined" ? window.location.hostname : "localhost";
  const host = rawHost && rawHost !== "0.0.0.0" ? rawHost : "localhost";

  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/trademaster";
  const chatBase = process.env.NEXT_PUBLIC_CHAT_BASE_URL ?? "/api/trademaster";
  const signalWsUrl = process.env.NEXT_PUBLIC_SIGNAL_WS_URL ?? `ws://${host}:8000/ws/signal`;

  return {
    apiBase,
    chatBase,
    signalWsUrl,
    defaultExchange: process.env.NEXT_PUBLIC_DEFAULT_EXCHANGE ?? "binance_futures_um",
    defaultInterval: process.env.NEXT_PUBLIC_DEFAULT_INTERVAL ?? "1h",
    defaultSymbol: process.env.NEXT_PUBLIC_DEFAULT_SYMBOL ?? "BTCUSDT",
    trendSymbols: (process.env.NEXT_PUBLIC_TREND_SYMBOLS ?? "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    refreshIntervalMs: Number(process.env.NEXT_PUBLIC_REFRESH_INTERVAL_MS ?? 15000)
  };
}

async function fetchJson<T>(url: string): Promise<FetchPayload<T>> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    const retryAfterMs = parseRetryAfterMs(response.headers.get("retry-after"));
    if (!response.ok) {
      return {
        data: null,
        meta: {
          ok: false,
          httpStatus: response.status,
          rateLimited: response.status === 429,
          degraded: true,
          retryAfterMs
        }
      };
    }
    const payload = (await response.json()) as unknown;
    const unwrapped = unwrapEnvelope<T>(payload);
    return {
      data: unwrapped.data,
      meta: {
        ok: unwrapped.ok,
        httpStatus: response.status,
        rateLimited: false,
        degraded: !unwrapped.ok,
        retryAfterMs
      }
    };
  } catch {
    return {
      data: null,
      meta: {
        ok: false,
        httpStatus: null,
        rateLimited: false,
        degraded: true,
        retryAfterMs: null
      }
    };
  }
}

export async function fetchApiHealth(apiBase: string, onMeta?: FetchMetaListener): Promise<boolean> {
  const payload = await fetchJson<Record<string, unknown>>(`${apiBase}/health`);
  onMeta?.(payload.meta);
  const data = payload.data;
  return Boolean(data?.status);
}

export async function fetchMomentum(
  apiBase: string,
  exchange: string,
  onMeta?: FetchMetaListener
): Promise<MomentumSnapshot | null> {
  const payload = await fetchJson<Record<string, unknown>>(`${apiBase}/markets/momentum?exchange=${encodeURIComponent(exchange)}`);
  onMeta?.(payload.meta);
  const data = payload.data;
  if (!data) {
    return null;
  }
  return {
    upCount: toNumber(data.up_count, 0),
    downCount: toNumber(data.down_count, 0),
    flatCount: toNumber(data.flat_count, 0),
    total: toNumber(data.total, 0),
    timestamp: data.timestamp ? toNumber(data.timestamp, 0) : null
  };
}

export async function fetchTopMovers(
  apiBase: string,
  order: TopMoverOrder,
  exchange: string,
  limit = 16,
  onMeta?: FetchMetaListener
): Promise<TopMoverItem[]> {
  const payload = await fetchJson<Array<Record<string, unknown>>>(
    `${apiBase}/markets/top-movers?order=${encodeURIComponent(order)}&limit=${limit}&exchange=${encodeURIComponent(exchange)}`
  );
  onMeta?.(payload.meta);
  const rows = payload.data;
  if (!rows) {
    return [];
  }

  return rows.map((row) => ({
    symbol: String(row.symbol ?? "UNKNOWN"),
    lastClose: toNullableNumber(row.last_close),
    prevClose: toNullableNumber(row.prev_close),
    timestamp: toNullableNumber(row.timestamp),
    volume24h: toNumber(row.volume_24h, 0),
    quoteVolume24h: toNumber(row.quote_volume_24h, 0),
    changePct: row.change_pct == null ? null : toNumber(row.change_pct, 0)
  }));
}

export async function fetchSignalsLatest(
  apiBase: string,
  limit = 80,
  filters: { symbol?: string; interval?: string; ruleKey?: string } = {},
  onMeta?: FetchMetaListener
): Promise<SignalEvent[]> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("include_ml", "true");
  if (filters.symbol) {
    params.set("symbol", filters.symbol);
  }
  if (filters.interval) {
    params.set("interval", filters.interval);
  }
  if (filters.ruleKey) {
    params.set("rule_key", filters.ruleKey);
  }

  const payload = await fetchJson<Array<Record<string, unknown>>>(`${apiBase}/signal/events/latest?${params.toString()}`);
  onMeta?.(payload.meta);
  const rows = payload.data;
  if (!rows) {
    return [];
  }

  return rows
    .map((row) => normalizeSignalEvent(row))
    .filter((row) => row.id > 0)
    .sort((a, b) => b.id - a.id)
    .slice(0, limit);
}

export async function fetchSignalRules(apiBase: string, onMeta?: FetchMetaListener): Promise<SignalRuleItem[]> {
  const payload = await fetchJson<Array<Record<string, unknown>>>(`${apiBase}/signal/rules`);
  onMeta?.(payload.meta);
  const rows = payload.data;
  if (!rows) {
    return [];
  }

  return rows.map((row) => ({
    ruleKey: String(row.rule_key ?? "unknown"),
    enabled: Boolean(row.enabled),
    priority: toNumber(row.priority, 0),
    cooldownSeconds: toNumber(row.cooldown_seconds, 0),
    params: row.params && typeof row.params === "object" ? (row.params as Record<string, unknown>) : {},
    scopeSymbols: Array.isArray(row.scope_symbols) ? row.scope_symbols.map((item) => String(item)) : [],
    scopeIntervals: Array.isArray(row.scope_intervals) ? row.scope_intervals.map((item) => String(item)) : [],
    updatedAt: row.updated_at ? String(row.updated_at) : null
  }));
}

export async function fetchSignalCooldown(apiBase: string, limit = 12, onMeta?: FetchMetaListener): Promise<CooldownItem[]> {
  const payload = await fetchJson<Array<Record<string, unknown>>>(`${apiBase}/signal/cooldown?limit=${limit}`);
  onMeta?.(payload.meta);
  const rows = payload.data;
  if (!rows) {
    return [];
  }

  return rows.map((row) => ({
    symbol: String(row.symbol ?? "UNKNOWN"),
    interval: String(row.interval ?? "1h"),
    ruleKey: String(row.rule_key ?? "unlabeled"),
    direction: String(row.direction ?? "neutral"),
    cooldownSeconds: toNumber(row.cooldown_seconds, 0),
    cooldownLeftSeconds: toNumber(row.cooldown_left_seconds, 0),
    detectedAt: String(row.detected_at ?? "")
  }));
}

export async function fetchMlRuntime(apiBase: string, onMeta?: FetchMetaListener): Promise<MlRuntimeState | null> {
  const payload = await fetchJson<Record<string, unknown>>(`${apiBase}/ml/runtime`);
  onMeta?.(payload.meta);
  const data = payload.data;
  if (!data) {
    return null;
  }
  return {
    championVersion: data.champion_version ? String(data.champion_version) : null,
    lastProcessedEventId: toNumber(data.last_processed_event_id, 0),
    lastTrainRunId: data.last_train_run_id == null ? null : toNumber(data.last_train_run_id, 0),
    lastTrainAt: data.last_train_at ? String(data.last_train_at) : null,
    lastDriftCheckAt: data.last_drift_check_at ? String(data.last_drift_check_at) : null,
    queueLag: toNumber(data.queue_lag, 0),
    queueLagScoped: data.queue_lag_scoped == null ? undefined : toNumber(data.queue_lag_scoped, 0),
    queueLagTotal: data.queue_lag_total == null ? undefined : toNumber(data.queue_lag_total, 0),
    runtimeInterval: data.runtime_interval ? String(data.runtime_interval) : undefined
  };
}

export async function fetchMlTrainingRuns(
  apiBase: string,
  limit = 20,
  onMeta?: FetchMetaListener
): Promise<MlTrainingRun[]> {
  const payload = await fetchJson<Array<Record<string, unknown>>>(`${apiBase}/ml/training/runs?limit=${limit}`);
  onMeta?.(payload.meta);
  const rows = payload.data;
  if (!rows) {
    return [];
  }
  return rows.map((row) => ({
    id: toNumber(row.id, 0),
    modelName: String(row.model_name ?? ""),
    modelVersion: String(row.model_version ?? ""),
    runType: String(row.run_type ?? "train"),
    promoted: Boolean(row.promoted),
    threshold: toNumber(row.threshold, 0),
    sampleCount: toNumber(row.sample_count, 0),
    featuresUsed: Array.isArray(row.features_used) ? row.features_used.map((v) => String(v)) : [],
    featureImportance: Array.isArray(row.feature_importance)
      ? row.feature_importance.reduce<Array<{ name: string; coef?: number; absCoef?: number }>>((acc, item) => {
          if (!item || typeof item !== "object") {
            return acc;
          }
          const data = item as Record<string, unknown>;
          acc.push({
            name: String(data.name ?? ""),
            coef: data.coef == null ? undefined : toNumber(data.coef, 0),
            absCoef: data.abs_coef == null ? undefined : toNumber(data.abs_coef, 0)
          });
          return acc;
        }, [])
      : [],
    metrics: row.metrics && typeof row.metrics === "object" ? (row.metrics as Record<string, unknown>) : {},
    createdAt: row.created_at ? String(row.created_at) : null
  }));
}

export async function fetchMlDriftLatest(
  apiBase: string,
  limit = 20,
  onMeta?: FetchMetaListener
): Promise<MlDriftSnapshot[]> {
  const payload = await fetchJson<Array<Record<string, unknown>>>(`${apiBase}/ml/drift/latest?limit=${limit}`);
  onMeta?.(payload.meta);
  const rows = payload.data;
  if (!rows) {
    return [];
  }
  return rows.map((row) => ({
    id: toNumber(row.id, 0),
    modelVersion: String(row.model_version ?? ""),
    sampleCount: toNumber(row.sample_count, 0),
    overallPsi: toNumber(row.overall_psi, 0),
    maxFeaturePsi: toNumber(row.max_feature_psi, 0),
    threshold: toNumber(row.threshold, 0),
    triggeredRetrain: Boolean(row.triggered_retrain),
    triggeredRunId: row.triggered_run_id == null ? null : toNumber(row.triggered_run_id, 0),
    createdAt: row.created_at ? String(row.created_at) : null,
    driftFeatures: Array.isArray(row.drift_features)
      ? row.drift_features
          .map((item) => {
            if (!item || typeof item !== "object") {
              return null;
            }
            const data = item as Record<string, unknown>;
            return {
              feature: String(data.feature ?? ""),
              psi: toNumber(data.psi, 0)
            };
          })
          .filter((item): item is { feature: string; psi: number } => Boolean(item?.feature))
      : []
  }));
}

export async function fetchMlValidationSummary(
  apiBase: string,
  window: "1d" | "7d" | "30d" = "7d",
  onMeta?: FetchMetaListener
): Promise<MlValidationSummary | null> {
  const payload = await fetchJson<Record<string, unknown>>(`${apiBase}/ml/validation/summary?window=${window}`);
  onMeta?.(payload.meta);
  const data = payload.data;
  if (!data) {
    return null;
  }
  return {
    window,
    since: String(data.since ?? ""),
    total: toNumber(data.total, 0),
    passed: toNumber(data.passed, 0),
    review: toNumber(data.review, 0),
    rejected: toNumber(data.rejected, 0),
    unavailable: toNumber(data.unavailable, 0),
    passRatio: toNumber(data.pass_ratio, 0),
    avgProbability: toNumber(data.avg_probability, 0),
    latestValidatedAt: data.latest_validated_at ? String(data.latest_validated_at) : null
  };
}

export async function fetchMlCandidates(
  apiBase: string,
  options: {
    symbol?: string;
    interval?: string;
    status?: MlValidationStatus;
    limit?: number;
  } = {},
  onMeta?: FetchMetaListener
): Promise<MlCandidateRow[]> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 50));
  if (options.symbol) {
    params.set("symbol", options.symbol);
  }
  if (options.interval) {
    params.set("interval", options.interval);
  }
  if (options.status) {
    params.set("status", options.status);
  }

  const payload = await fetchJson<{ items?: Array<Record<string, unknown>> }>(`${apiBase}/ml/validation/candidates?${params.toString()}`);
  onMeta?.(payload.meta);
  const rows = payload.data?.items ?? [];
  return rows.map((row) => ({
    id: toNumber(row.id, 0),
    symbol: String(row.symbol ?? "UNKNOWN"),
    interval: String(row.interval ?? "1h"),
    ruleKey: String(row.rule_key ?? "unlabeled"),
    direction: String(row.direction ?? "neutral"),
    score: toNumber(row.score, 0),
    detail: String(row.detail ?? ""),
    detectedAt: String(row.detected_at ?? ""),
    validationStatus: toMlStatus(row.validation_status),
    mlValidation: normalizeMlValidation(row.ml_validation)
  }));
}

export async function fetchTrendHistory(
  apiBase: string,
  symbol: string,
  interval: string,
  exchange: string,
  limit = 60,
  onMeta?: FetchMetaListener
): Promise<TrendPoint[]> {
  const payload = await fetchJson<Array<Record<string, unknown>>>(
    `${apiBase}/futures/ohlc/history?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&exchange=${encodeURIComponent(exchange)}&limit=${limit}`
  );
  onMeta?.(payload.meta);
  const rows = payload.data;
  if (!rows) {
    return [];
  }

  return rows
    .map((row) => ({
      time: toNumber(row.time, 0),
      close: toNumber(row.close, 0)
    }))
    .filter((row) => Number.isFinite(row.time) && Number.isFinite(row.close));
}

export async function fetchIndicatorTables(apiBase: string, onMeta?: FetchMetaListener): Promise<string[]> {
  const payload = await fetchJson<string[]>(`${apiBase}/indicator/list`);
  onMeta?.(payload.meta);
  const rows = payload.data;
  return rows ?? [];
}

const INDICATOR_META_KEYS = new Set(["symbol", "interval", "time", "indicator", "stale", "交易对", "周期", "数据时间"]);

export async function fetchIndicatorRows(
  apiBase: string,
  table: string,
  symbol: string,
  interval: string,
  limit = 30,
  onMeta?: FetchMetaListener
): Promise<IndicatorRow[]> {
  const payload = await fetchJson<Array<Record<string, unknown>>>(
    `${apiBase}/indicator/data?table=${encodeURIComponent(table)}&symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`
  );
  onMeta?.(payload.meta);
  const rows = payload.data;
  if (!rows) {
    return [];
  }

  return rows.map((row) => {
    const payload: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(row)) {
      if (!INDICATOR_META_KEYS.has(key)) {
        payload[key] = value;
      }
    }

    return {
      symbol: String(row.symbol ?? row["交易对"] ?? symbol),
      interval: String(row.interval ?? row["周期"] ?? interval),
      indicator: String(row.indicator ?? table),
      time: toNumber(row.time, 0),
      payload
    };
  });
}

export type ChatSendOptions = {
  sessionId?: string;
  history?: Array<{ role: "user" | "assistant"; content: string }>;
  symbol?: string;
  interval?: string;
  activeRule?: string | null;
  mlDecision?: string | null;
};

export type ChatReply = {
  text: string;
  sessionId: string | null;
  model: string | null;
  timestampMs: number | null;
  degraded: boolean;
  rateLimited: boolean;
  retryAfterMs: number | null;
  httpStatus: number | null;
};

function buildChatPrompt(message: string, options: ChatSendOptions): string {
  const contextRows = [
    options.symbol ? `symbol=${options.symbol}` : null,
    options.interval ? `interval=${options.interval}` : null,
    options.activeRule ? `active_rule=${options.activeRule}` : null,
    options.mlDecision ? `ml_decision=${options.mlDecision}` : null
  ].filter(Boolean);

  const contextBlock = contextRows.length > 0 ? `Context: ${contextRows.join("; ")}\n` : "";
  const strategyFormat =
    "Please answer in four sections with Chinese headings: 结论, 依据, 风险, 下一步. Keep each section concise and actionable.";

  return `${contextBlock}${message}\n\n${strategyFormat}`;
}

export async function sendChatMessage(chatBase: string, message: string, options: ChatSendOptions = {}): Promise<ChatReply> {
  const payload: Record<string, unknown> = {
    message: buildChatPrompt(message, options)
  };

  if (options.sessionId) {
    payload.session_id = options.sessionId;
  }
  if (options.history && options.history.length > 0) {
    payload.history = options.history.map((item) => ({ role: item.role, content: item.content }));
  }

  try {
    const response = await fetch(`${chatBase}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload),
      cache: "no-store"
    });

    const retryAfterMs = parseRetryAfterMs(response.headers.get("retry-after"));
    if (!response.ok) {
      const rateLimited = response.status === 429;
      const text = rateLimited
        ? "Chat is rate limited now. Please retry shortly."
        : "Chat service is temporarily unavailable. Please retry in a moment.";
      return {
        text,
        sessionId: null,
        model: null,
        timestampMs: null,
        degraded: true,
        rateLimited,
        retryAfterMs,
        httpStatus: response.status
      };
    }

    const result = (await response.json()) as Record<string, unknown>;
    const text = result.reply ?? result.answer ?? result.content;
    return {
      text: typeof text === "string" && text.trim() ? text.trim() : "No response content.",
      sessionId: result.session_id ? String(result.session_id) : null,
      model: result.model ? String(result.model) : null,
      timestampMs: result.timestamp_ms == null ? null : toNumber(result.timestamp_ms, 0),
      degraded: false,
      rateLimited: false,
      retryAfterMs,
      httpStatus: response.status
    };
  } catch {
    return {
      text: "Chat service is temporarily unavailable. Please retry in a moment.",
      sessionId: null,
      model: null,
      timestampMs: null,
      degraded: true,
      rateLimited: false,
      retryAfterMs: null,
      httpStatus: null
    };
  }
}

export function createSignalSocket(
  wsUrl: string,
  sinceId: number,
  onSignal: (event: SignalEvent) => void,
  onState: (connected: boolean) => void
): WebSocket {
  const socket = new WebSocket(`${wsUrl}?since_id=${Math.max(0, sinceId)}`);

  socket.onopen = () => {
    onState(true);
  };

  socket.onclose = () => {
    onState(false);
  };

  socket.onerror = () => {
    onState(false);
  };

  socket.onmessage = (event) => {
    try {
      const parsed = JSON.parse(String(event.data)) as Record<string, unknown>;
      if (parsed.event !== "signal") {
        return;
      }
      const data = parsed.data as Record<string, unknown>;
      const normalized = normalizeSignalEvent(data);
      if (normalized.id > 0) {
        onSignal(normalized);
      }
    } catch {
      // no-op
    }
  };

  return socket;
}
