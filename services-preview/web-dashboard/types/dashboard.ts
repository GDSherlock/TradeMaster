export type DataSourceMode = "mock" | "live" | "mock-fallback";

export interface LandingModule {
  name: string;
  metric: string;
  description: string;
  sparkline: number[];
}

export interface MarketTicker {
  symbol: string;
  price: number;
  change24h: number;
  volume24h: number;
}

export interface MoverRow {
  symbol: string;
  price: number;
  change24h: number;
  volume24h: number;
}

export interface SignalItem {
  id: string;
  symbol: string;
  timeframe: string;
  direction: "long" | "short" | "neutral";
  confidence: number;
  rationale: string[];
  createdAt: string;
}

export interface PortfolioSlice {
  name: string;
  value: number;
  color: string;
}

export interface RiskMetric {
  var95: number;
  maxDrawdown: number;
  warnings: string[];
}

export interface NewsItem {
  id: string;
  headline: string;
  source: string;
  tag: string;
  sentiment: "bullish" | "bearish" | "neutral";
  publishedAt: string;
}

export interface DashboardDataBundle {
  source: DataSourceMode;
  tickers: MarketTicker[];
  movers: MoverRow[];
  signals: SignalItem[];
  portfolio: {
    allocation: PortfolioSlice[];
    pnlToday: number;
    pnl30d: number;
    exposure: number;
  };
  risk: RiskMetric;
  news: NewsItem[];
}
