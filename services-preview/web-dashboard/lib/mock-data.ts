import type { DashboardDataBundle, LandingModule, NewsItem, SignalItem } from "@/types/dashboard";

const LANDING_MODULES: LandingModule[] = [
  {
    name: "Market Overview",
    metric: "$1.89T Market Cap",
    description: "Macro heatmap and liquidity pulse in one panel.",
    sparkline: [42, 48, 45, 54, 58, 61, 64, 69]
  },
  {
    name: "Signal Lab",
    metric: "31 Active Signals",
    description: "Ranked setups with confidence and contextual notes.",
    sparkline: [34, 39, 37, 44, 49, 46, 52, 57]
  },
  {
    name: "Portfolio & Risk",
    metric: "+8.6% 30D PnL",
    description: "Allocation, drawdown and exposure snapshots.",
    sparkline: [58, 54, 56, 60, 62, 64, 67, 70]
  },
  {
    name: "Alerts & Automation",
    metric: "12 Rule Automations",
    description: "Dispatch custom alerts to your channels in real time.",
    sparkline: [22, 26, 31, 29, 34, 37, 43, 47]
  }
];

const SIGNALS: SignalItem[] = [
  {
    id: "sg-01",
    symbol: "BTCUSDT",
    timeframe: "1h",
    direction: "long",
    confidence: 84,
    rationale: ["EMA20 crossed above EMA50", "Volume expansion above 20d average", "Funding remains neutral"],
    createdAt: "2m ago"
  },
  {
    id: "sg-02",
    symbol: "ETHUSDT",
    timeframe: "4h",
    direction: "long",
    confidence: 73,
    rationale: ["RSI reclaimed 50", "Range breakout with retest hold", "On-chain netflow cooled"],
    createdAt: "12m ago"
  },
  {
    id: "sg-03",
    symbol: "SOLUSDT",
    timeframe: "1h",
    direction: "short",
    confidence: 66,
    rationale: ["Momentum divergence", "VWAP rejection", "Open interest rising on sell pressure"],
    createdAt: "25m ago"
  }
];

const NEWS: NewsItem[] = [
  {
    id: "nw-1",
    headline: "ETF net inflows remain steady as volatility compresses",
    source: "Desk Brief",
    tag: "Macro",
    sentiment: "bullish",
    publishedAt: "8m ago"
  },
  {
    id: "nw-2",
    headline: "Derivatives basis cools after sharp weekend move",
    source: "Market Wire",
    tag: "Derivatives",
    sentiment: "neutral",
    publishedAt: "18m ago"
  },
  {
    id: "nw-3",
    headline: "Layer-1 tokens pull back as BTC dominance rises",
    source: "Signals Desk",
    tag: "Rotation",
    sentiment: "bearish",
    publishedAt: "33m ago"
  }
];

export function getLandingModules(): LandingModule[] {
  return LANDING_MODULES;
}

export function getDashboardData(): DashboardDataBundle {
  return {
    source: "mock",
    tickers: [
      { symbol: "BTC", price: 68422.12, change24h: 2.31, volume24h: 38.5 },
      { symbol: "ETH", price: 3728.34, change24h: 1.64, volume24h: 21.7 }
    ],
    movers: [
      { symbol: "SOL", price: 198.24, change24h: 5.8, volume24h: 7.4 },
      { symbol: "AVAX", price: 48.77, change24h: 4.6, volume24h: 3.9 },
      { symbol: "LINK", price: 20.12, change24h: -2.1, volume24h: 2.2 },
      { symbol: "BNB", price: 614.84, change24h: 1.3, volume24h: 5.1 }
    ],
    signals: SIGNALS,
    portfolio: {
      allocation: [
        { name: "BTC", value: 46, color: "#147a68" },
        { name: "ETH", value: 29, color: "#2d9e88" },
        { name: "SOL", value: 15, color: "#76c7b6" },
        { name: "Cash", value: 10, color: "#cdeee6" }
      ],
      pnlToday: 1.92,
      pnl30d: 8.61,
      exposure: 78
    },
    risk: {
      var95: 4.3,
      maxDrawdown: 11.8,
      warnings: [
        "Concentration in beta assets exceeds internal limit (65%).",
        "Correlation cluster: BTC/ETH/SOL currently elevated.",
        "Funding spike watch for perpetuals exposure."
      ]
    },
    news: NEWS
  };
}
