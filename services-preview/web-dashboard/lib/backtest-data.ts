import type {
  BacktestCatalog,
  BacktestEquityPoint,
  BacktestRun,
  BacktestStrategy,
  BacktestStrategyVersion,
  BacktestTrade
} from "@/types/backtest";

type ApiEnvelope<T> = {
  data?: T;
  success?: boolean;
  code?: string;
};

async function unwrap<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as ApiEnvelope<T>;
  if (!response.ok || payload.success === false || payload.code && payload.code !== "0") {
    throw new Error(typeof payload?.code === "string" ? payload.code : "request_failed");
  }
  return (payload.data ?? null) as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/trademaster/backtest${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  return unwrap<T>(response);
}

export function fetchBacktestCatalog(): Promise<BacktestCatalog> {
  return request<BacktestCatalog>("/catalog");
}

export function fetchBacktestStrategies(): Promise<BacktestStrategy[]> {
  return request<BacktestStrategy[]>("/strategies");
}

export function createBacktestStrategy(payload: Record<string, unknown>): Promise<{
  strategy_id: number;
  name: string;
  description: string;
  created_at: string | null;
  updated_at: string | null;
  version: BacktestStrategyVersion;
}> {
  return request("/strategies", { method: "POST", body: JSON.stringify(payload) });
}

export function fetchBacktestStrategy(strategyId: number): Promise<BacktestStrategy> {
  return request<BacktestStrategy>(`/strategies/${strategyId}`);
}

export function fetchBacktestVersions(strategyId: number): Promise<BacktestStrategyVersion[]> {
  return request<BacktestStrategyVersion[]>(`/strategies/${strategyId}/versions`);
}

export function createBacktestRun(payload: Record<string, unknown>): Promise<BacktestRun> {
  return request<BacktestRun>("/runs", { method: "POST", body: JSON.stringify(payload) });
}

export function fetchBacktestRuns(limit = 100): Promise<BacktestRun[]> {
  return request<BacktestRun[]>(`/runs?limit=${limit}`);
}

export function fetchBacktestRun(runId: number): Promise<BacktestRun> {
  return request<BacktestRun>(`/runs/${runId}`);
}

export function fetchBacktestEquity(runId: number): Promise<BacktestEquityPoint[]> {
  return request<BacktestEquityPoint[]>(`/runs/${runId}/equity`);
}

export function fetchBacktestTrades(runId: number): Promise<BacktestTrade[]> {
  return request<BacktestTrade[]>(`/runs/${runId}/trades`);
}

export function cancelBacktestRun(runId: number): Promise<BacktestRun> {
  return request<BacktestRun>(`/runs/${runId}/cancel`, { method: "POST" });
}
