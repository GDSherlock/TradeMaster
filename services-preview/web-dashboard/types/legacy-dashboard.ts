export type SignalViewMode = "events" | "summary";

export type SignalBoardMode = "events" | "bySymbol" | "byRule";

export type MlValidationStatus = "pending" | "passed" | "review" | "rejected" | "unavailable";

export type MlCandidateFilterStatus = "all" | MlValidationStatus;

export type MlValidationBadge = {
  modelName: string;
  modelVersion: string;
  probability: number;
  threshold: number;
  decision: MlValidationStatus;
  reason: string;
  topFeatures: Array<{ name: string; value: number }>;
  validatedAt: string | null;
};

export type SignalEvent = {
  id: number;
  symbol: string;
  interval: string;
  ruleKey: string;
  direction: string;
  score: number;
  detail: string;
  detectedAt: string;
  cooldownSeconds?: number;
  cooldownLeftSeconds?: number;
  mlValidation?: MlValidationBadge | null;
};

export type MomentumSnapshot = {
  upCount: number;
  downCount: number;
  flatCount: number;
  total: number;
  timestamp: number | null;
};

export type MarketPulse = {
  breadthText: string;
  signalDensity: number;
  alignmentPct: number;
  riskLabel: "risk-on" | "risk-off" | "mixed";
};

export type TopMoverOrder = "abs" | "desc" | "asc";

export type TopMoverItem = {
  symbol: string;
  lastClose: number | null;
  prevClose: number | null;
  timestamp: number | null;
  volume24h: number;
  quoteVolume24h: number;
  changePct: number | null;
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

export type SignalRuleItem = {
  ruleKey: string;
  enabled: boolean;
  priority: number;
  cooldownSeconds: number;
  params: Record<string, unknown>;
  scopeSymbols: string[];
  scopeIntervals: string[];
  updatedAt: string | null;
};

export type CooldownItem = {
  symbol: string;
  interval: string;
  ruleKey: string;
  direction: string;
  cooldownSeconds: number;
  cooldownLeftSeconds: number;
  detectedAt: string;
};

export type DashboardHealth = {
  apiOk: boolean;
  dataOk: boolean;
  updatedAt: number | null;
};

export type DashboardFetchState = {
  rateLimited: boolean;
  degraded: boolean;
  lastSuccessAt: number | null;
  lastStatusCode: number | null;
};

export type ChatStrategyCard = {
  summary: string;
  evidence: string;
  risk: string;
  nextActions: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timeLabel: string;
  strategy?: ChatStrategyCard;
};

export type ChatContextState = {
  symbol: string;
  interval: string;
  activeRule: string | null;
  mlDecision: MlValidationStatus | null;
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

export type MlCandidateRow = {
  id: number;
  symbol: string;
  interval: string;
  ruleKey: string;
  direction: string;
  score: number;
  detail: string;
  detectedAt: string;
  validationStatus: MlValidationStatus;
  mlValidation: MlValidationBadge | null;
};

export type MlCandidateDetail = MlCandidateRow & {
  payload: Record<string, unknown>;
  featureSnapshot: Record<string, number>;
  labelHorizonBars: number;
  labelDueAt: string | null;
  yRsiRevert: number | null;
  realizedReturnBps: number;
};

export type MlValidationSummary = {
  window: "1d" | "7d" | "30d";
  since: string;
  total: number;
  passed: number;
  review: number;
  rejected: number;
  unavailable: number;
  passRatio: number;
  avgProbability: number;
  latestValidatedAt: string | null;
};

export type MlMetricsSnapshot = {
  window: "1d" | "7d" | "30d";
  since: string;
  currentModel: {
    id: number | null;
    modelName: string | null;
    modelVersion: string | null;
    threshold: number | null;
    metrics: Record<string, unknown>;
    promoted: boolean;
    createdAt: string | null;
  };
  liveStats: {
    total: number;
    passed: number;
    review: number;
    rejected: number;
    passRatio: number;
    avgProbability: number;
  };
};

export type MlTrainingRun = {
  id: number;
  modelName: string;
  modelVersion: string;
  runType: string;
  promoted: boolean;
  threshold: number;
  sampleCount: number;
  featuresUsed: string[];
  featureImportance: Array<{ name: string; coef?: number; absCoef?: number }>;
  metrics: Record<string, unknown>;
  createdAt: string | null;
};

export type MlRuntimeState = {
  championVersion: string | null;
  lastProcessedEventId: number;
  lastTrainRunId: number | null;
  lastTrainAt: string | null;
  lastTrainAttemptAt: string | null;
  lastTrainStatus: string;
  lastTrainError: string | null;
  lastTrainSampleCount: number;
  lastTrainPositiveRatio: number;
  lastDriftCheckAt: string | null;
  queueLag: number;
  queueLagScoped?: number;
  queueLagTotal?: number;
  runtimeInterval?: string;
};

export type MlDriftSnapshot = {
  id: number;
  modelVersion: string;
  sampleCount: number;
  overallPsi: number;
  maxFeaturePsi: number;
  threshold: number;
  triggeredRetrain: boolean;
  triggeredRunId: number | null;
  createdAt: string | null;
  driftFeatures: Array<{ feature: string; psi: number }>;
};

export type MlFeatureCatalogItem = {
  name: string;
  group: string;
  description: string;
};

export type MlDashboardBundle = {
  runtime: MlRuntimeState | null;
  summary: MlValidationSummary | null;
  candidates: MlCandidateRow[];
  runs: MlTrainingRun[];
  drift: MlDriftSnapshot[];
};
