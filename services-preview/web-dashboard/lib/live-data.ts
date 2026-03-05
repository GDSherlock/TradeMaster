import type { IndicatorRow, MomentumSnapshot, RuntimeEndpoints, SignalEvent, TrendPoint } from "@/types/legacy-dashboard";

type ApiEnvelope<T> = {
  success?: boolean;
  code?: string;
  data?: T;
};

function unwrapEnvelope<T>(payload: unknown): T | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const maybeWrapped = payload as ApiEnvelope<T>;
  if (Object.prototype.hasOwnProperty.call(maybeWrapped, "data")) {
    if (maybeWrapped.success === false) {
      return null;
    }
    if (maybeWrapped.code && maybeWrapped.code !== "0") {
      return null;
    }
    return maybeWrapped.data ?? null;
  }
  return payload as T;
}

export function resolveRuntimeEndpoints(): RuntimeEndpoints {
  const rawHost = typeof window !== "undefined" ? window.location.hostname : "localhost";
  const host = rawHost && rawHost !== "0.0.0.0" ? rawHost : "localhost";

  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? `http://${host}:8000/api`;
  const chatBase = process.env.NEXT_PUBLIC_CHAT_BASE_URL ?? `http://${host}:8001`;
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

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as unknown;
    return unwrapEnvelope<T>(payload);
  } catch {
    return null;
  }
}

export async function fetchApiHealth(apiBase: string): Promise<boolean> {
  const data = await fetchJson<Record<string, unknown>>(`${apiBase}/health`);
  return Boolean(data?.status);
}

export async function fetchMomentum(apiBase: string, exchange: string): Promise<MomentumSnapshot | null> {
  const data = await fetchJson<Record<string, unknown>>(`${apiBase}/markets/momentum?exchange=${encodeURIComponent(exchange)}`);
  if (!data) {
    return null;
  }
  return {
    upCount: Number(data.up_count ?? 0),
    downCount: Number(data.down_count ?? 0),
    flatCount: Number(data.flat_count ?? 0),
    total: Number(data.total ?? 0),
    timestamp: data.timestamp ? Number(data.timestamp) : null
  };
}

export async function fetchSignalsLatest(apiBase: string, limit = 60): Promise<SignalEvent[]> {
  const rows = await fetchJson<Array<Record<string, unknown>>>(`${apiBase}/signal/events/latest?limit=${limit}`);
  if (!rows) {
    return [];
  }
  return rows
    .map((row) => ({
      id: Number(row.id ?? 0),
      symbol: String(row.symbol ?? "UNKNOWN"),
      interval: String(row.interval ?? "1h"),
      ruleKey: String(row.rule_key ?? "unlabeled"),
      direction: String(row.direction ?? "neutral"),
      score: Number(row.score ?? 0),
      detail: String(row.detail ?? ""),
      detectedAt: String(row.detected_at ?? "")
    }))
    .filter((row) => row.id > 0)
    .sort((a, b) => b.id - a.id)
    .slice(0, limit);
}

export async function fetchTrendHistory(
  apiBase: string,
  symbol: string,
  interval: string,
  exchange: string,
  limit = 60
): Promise<TrendPoint[]> {
  const rows = await fetchJson<Array<Record<string, unknown>>>(
    `${apiBase}/futures/ohlc/history?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&exchange=${encodeURIComponent(exchange)}&limit=${limit}`
  );
  if (!rows) {
    return [];
  }

  return rows
    .map((row) => ({
      time: Number(row.time ?? 0),
      close: Number(row.close ?? 0)
    }))
    .filter((row) => Number.isFinite(row.time) && Number.isFinite(row.close));
}

export async function fetchIndicatorTables(apiBase: string): Promise<string[]> {
  const rows = await fetchJson<string[]>(`${apiBase}/indicator/list`);
  return rows ?? [];
}

const INDICATOR_META_KEYS = new Set(["symbol", "interval", "time", "indicator", "stale", "交易对", "周期", "数据时间"]);

export async function fetchIndicatorRows(
  apiBase: string,
  table: string,
  symbol: string,
  interval: string,
  limit = 30
): Promise<IndicatorRow[]> {
  const rows = await fetchJson<Array<Record<string, unknown>>>(
    `${apiBase}/indicator/data?table=${encodeURIComponent(table)}&symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&limit=${limit}`
  );
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
      time: Number(row.time ?? 0),
      payload
    };
  });
}

export async function sendChatMessage(chatBase: string, message: string): Promise<string> {
  const response = await fetch(`${chatBase}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      message,
      symbol: "BTCUSDT",
      interval: "1h"
    })
  });

  if (!response.ok) {
    throw new Error(`chat request failed: ${response.status}`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
  const text = payload.reply ?? payload.answer ?? payload.content;
  if (typeof text !== "string" || !text.trim()) {
    return "No response content.";
  }
  return text.trim();
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
      const normalized: SignalEvent = {
        id: Number(data.id ?? 0),
        symbol: String(data.symbol ?? "UNKNOWN"),
        interval: String(data.interval ?? "1h"),
        ruleKey: String(data.rule_key ?? "unlabeled"),
        direction: String(data.direction ?? "neutral"),
        score: Number(data.score ?? 0),
        detail: String(data.detail ?? ""),
        detectedAt: String(data.detected_at ?? "")
      };

      if (normalized.id > 0) {
        onSignal(normalized);
      }
    } catch {
      // no-op
    }
  };

  return socket;
}
