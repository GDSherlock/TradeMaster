export type SignalViewMode = "events" | "summary";

export type SignalEvent = {
  id: number;
  symbol: string;
  interval: string;
  ruleKey: string;
  direction: string;
  score: number;
  detail: string;
  detectedAt: string;
};

export type MomentumSnapshot = {
  upCount: number;
  downCount: number;
  flatCount: number;
  total: number;
  timestamp: number | null;
};

export type TrendPoint = {
  time: number;
  close: number;
};

export type IndicatorRow = {
  symbol: string;
  interval: string;
  indicator: string;
  time: number;
  payload: Record<string, unknown>;
};

export type DashboardHealth = {
  apiOk: boolean;
  dataOk: boolean;
  updatedAt: number | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timeLabel: string;
};

export type RuntimeEndpoints = {
  apiBase: string;
  chatBase: string;
  signalWsUrl: string;
  defaultExchange: string;
  defaultInterval: string;
  defaultSymbol: string;
  trendSymbols: string[];
  refreshIntervalMs: number;
};
