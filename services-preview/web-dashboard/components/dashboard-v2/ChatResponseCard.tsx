"use client";

import type { ChatConfidenceBand, ChatRenderPayload, ChatStance } from "@/types/legacy-dashboard";

type ChatResponseCardProps = {
  payload: ChatRenderPayload;
  degradedReason?: string | null;
};

const LABELS = {
  en: {
    note: "Note",
    risk: "If this is wrong",
    watch: "What matters",
    why: "More detail",
    confidence: "Conviction",
    quality: "Data Quality",
    fallback: "Fallback",
    bands: {
      high: "High",
      medium: "Medium",
      low: "Low"
    },
    stances: {
      bullish: "Bullish",
      bearish: "Bearish",
      neutral: "Neutral",
      conflicted: "Conflicted",
      no_trade: "No Trade"
    }
  },
  zh: {
    note: "补充",
    risk: "如果错了，会怎么错",
    watch: "重点看",
    why: "展开补充",
    confidence: "判断强度",
    quality: "数据质量",
    fallback: "回退模式",
    bands: {
      high: "高",
      medium: "中",
      low: "低"
    },
    stances: {
      bullish: "看多",
      bearish: "看空",
      neutral: "中性",
      conflicted: "分歧",
      no_trade: "不交易"
    }
  }
} as const;

function joinParts(language: "en" | "zh", values: Array<string | undefined | null>): string | null {
  const parts = values.map((item) => item?.trim()).filter((item): item is string => Boolean(item));
  if (parts.length === 0) {
    return null;
  }
  return language === "zh" ? parts.join("；") : parts.join("; ");
}

function stanceTone(stance: ChatStance): string {
  switch (stance) {
    case "bullish":
      return "long";
    case "bearish":
      return "short";
    case "conflicted":
      return "review";
    case "no_trade":
      return "unavailable";
    default:
      return "neutral";
  }
}

function confidenceTone(band: ChatConfidenceBand): string {
  switch (band) {
    case "high":
      return "passed";
    case "medium":
      return "review";
    default:
      return "pending";
  }
}

function fallbackLabel(language: "en" | "zh", degradedReason: string): string {
  if (language === "zh") {
    switch (degradedReason) {
      case "structured_response_unavailable":
        return "结构化输出不可用，当前内容来自确定性回退。";
      case "service_unavailable":
        return "服务暂时不可用。";
      default:
        return degradedReason;
    }
  }
  switch (degradedReason) {
    case "structured_response_unavailable":
      return "Structured output was unavailable, so this card is using the deterministic fallback.";
    case "service_unavailable":
      return "Service is temporarily unavailable.";
    default:
      return degradedReason;
  }
}

export function ChatResponseCard({ payload, degradedReason }: ChatResponseCardProps) {
  const label = LABELS[payload.language];
  const watchText = joinParts(payload.language, payload.watchpoints ?? []);
  const riskText = joinParts(payload.language, payload.riskFlags ?? []);
  const noteText = joinParts(payload.language, [payload.actionPosture, payload.marketContext]);
  const detailText = joinParts(payload.language, [
    payload.expandableDetail?.thesis,
    ...(payload.expandableDetail?.evidence ?? []),
    ...(payload.expandableDetail?.scenarioMap ?? []),
    payload.expandableDetail?.mlContext
  ]);

  return (
    <div className="v2-chat-card">
      <div className="v2-chat-card-head">
        <p className="v2-chat-title">{payload.title}</p>
        <div className="v2-chat-chip-row">
          <span className={`v2-badge ${stanceTone(payload.stance)}`}>{label.stances[payload.stance]}</span>
          <span className={`v2-badge ${confidenceTone(payload.confidence.band)}`}>
            {label.bands[payload.confidence.band]}
          </span>
        </div>
      </div>

      <p className="v2-chat-summary">{payload.summary}</p>

      {payload.keyLevels && payload.keyLevels.length > 0 && (
        <div className="v2-chat-level-strip" aria-label="key levels">
          {payload.keyLevels.map((level) => (
            <div key={`${payload.title}-${level.kind}-${level.label}`} className="v2-chat-level-pill">
              <span>{level.label}</span>
              <strong>{level.value}</strong>
            </div>
          ))}
        </div>
      )}

      <div className="v2-chat-blocks">
        {watchText && (
          <section className="v2-chat-block">
            <h4>{label.watch}</h4>
            <p>{watchText}</p>
          </section>
        )}
        {riskText && (
          <section className="v2-chat-block critical">
            <h4>{label.risk}</h4>
            <p>{riskText}</p>
          </section>
        )}
        {noteText && (
          <section className="v2-chat-block subtle">
            <h4>{label.note}</h4>
            <p>{noteText}</p>
          </section>
        )}
      </div>

      {(detailText || payload.confidence.reason || payload.dataQuality?.note || payload.complianceNote || degradedReason) && (
        <details className="v2-chat-details">
          <summary>{label.why}</summary>
          <div className="v2-chat-details-body">
            <p>
              <strong>{label.confidence}:</strong> {payload.confidence.reason}
            </p>
            {detailText && <p>{detailText}</p>}
            {payload.dataQuality?.note && (
              <p>
                <strong>{label.quality}:</strong> {payload.dataQuality.note}
              </p>
            )}
            {degradedReason && (
              <p>
                <strong>{label.fallback}:</strong> {fallbackLabel(payload.language, degradedReason)}
              </p>
            )}
            {payload.complianceNote && <p>{payload.complianceNote}</p>}
          </div>
        </details>
      )}
    </div>
  );
}
