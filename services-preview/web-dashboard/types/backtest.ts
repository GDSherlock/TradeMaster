export type BacktestClauseType = "signal_rule" | "indicator_compare";
export type BacktestGroupLogic = "all" | "any";
export type BacktestTradeSide = "long" | "short" | "both";
export type BacktestClauseSide = "long" | "short" | "any";

export type BacktestCatalog = {
  symbols: string[];
  intervals: string[];
  signal_rules: string[];
  indicator_fields: Record<string, string[]>;
  operators: string[];
  direction_modes: BacktestTradeSide[];
  clause_sides: BacktestClauseSide[];
  defaults: Record<string, unknown>;
};

export type BacktestStrategy = {
  id: number;
  name: string;
  description: string;
  latest_version_id: number | null;
  latest_version_no: number | null;
  exchange: string | null;
  symbol: string | null;
  interval: string | null;
  dsl: Record<string, unknown>;
  latest_version_created_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type BacktestStrategyVersion = {
  id: number;
  strategy_id: number;
  version_no: number;
  exchange: string;
  symbol: string;
  interval: string;
  dsl: Record<string, unknown>;
  created_at: string | null;
};

export type BacktestRunSummary = {
  initial_equity: number;
  final_equity: number;
  trade_count: number;
  halted_by_drawdown: boolean;
  halted_at: string | null;
  halt_reason: string | null;
  bankrupt: boolean;
  total_return_pct: number;
  max_total_drawdown_pct: number;
  max_trailing_drawdown_pct: number;
  win_rate: number;
  profit_factor: number | null;
  avg_holding_bars: number;
};

export type BacktestRun = {
  id: number;
  strategy_id: number;
  strategy_version_id: number;
  version_no: number | null;
  strategy_name: string | null;
  strategy_description: string;
  exchange: string;
  symbol: string;
  interval: string;
  start_ts: string | null;
  end_ts: string | null;
  status: "queued" | "running" | "completed" | "failed" | "canceled";
  run_params: Record<string, unknown>;
  summary: Partial<BacktestRunSummary>;
  error_code: string | null;
  error_message: string | null;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  canceled_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type BacktestEquityPoint = {
  point_no: number;
  ts: string | null;
  close_price: number;
  equity: number;
  cash_balance: number;
  peak_equity: number;
  total_drawdown_pct: number;
  trailing_drawdown_pct: number;
  position_side: string | null;
  position_notional: number;
  position_quantity: number;
};

export type BacktestTrade = {
  id: number;
  trade_no: number;
  side: "long" | "short";
  entry_ts: string | null;
  exit_ts: string | null;
  entry_price: number;
  exit_price: number;
  notional: number;
  quantity: number;
  leverage: number;
  gross_pnl: number;
  net_pnl: number;
  fees_paid: number;
  slippage_paid: number;
  bars_held: number;
  exit_reason: string;
  meta: Record<string, unknown>;
};
