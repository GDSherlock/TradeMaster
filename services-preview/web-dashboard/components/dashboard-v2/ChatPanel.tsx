"use client";

import { useMemo, useState } from "react";

import { ChatResponseCard } from "@/components/dashboard-v2/ChatResponseCard";
import type { ChatContextState, ChatMessage, ChatResponseMode } from "@/types/legacy-dashboard";

type ChatPanelProps = {
  messages: ChatMessage[];
  pending: boolean;
  context: ChatContextState;
  onSend: (text: string, mode: ChatResponseMode) => Promise<void>;
};

export function ChatPanel({ messages, pending, context, onSend }: ChatPanelProps) {
  const [value, setValue] = useState("");
  const [mode, setMode] = useState<ChatResponseMode>("standard");

  const templates = useMemo(
    () => [
      `解释 ${context.symbol} ${context.interval} 当前信号是否冲突，并给出判定优先级。`,
      `基于 ${context.symbol} ${context.interval}，给出保守与激进两套行动方案。`,
      `列出 ${context.symbol} 接下来 2 小时最关键的观察条件与失效条件。`
    ],
    [context.interval, context.symbol]
  );

  async function submit(text: string) {
    const cleaned = text.trim();
    if (!cleaned || pending) {
      return;
    }
    setValue("");
    await onSend(cleaned, mode);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submit(value);
  }

  return (
    <section className="v2-panel v2-chat-panel" aria-label="Strategy chat">
      <div className="v2-panel-head">
        <div>
          <p className="v2-kicker">Strategy Chat</p>
          <h2>Ask, Compare, Decide</h2>
        </div>
      </div>

      <div className="v2-chip-row" aria-label="chat context">
        <span className="v2-chip">symbol: {context.symbol}</span>
        <span className="v2-chip">interval: {context.interval}</span>
        <span className="v2-chip">rule: {context.activeRule ?? "--"}</span>
        <span className="v2-chip">ml: {context.mlDecision ?? "--"}</span>
      </div>

      <div className="v2-switch v2-chat-mode-switch" role="tablist" aria-label="response mode">
        <button type="button" className={mode === "compact" ? "active" : ""} onClick={() => setMode("compact")}>
          Compact
        </button>
        <button type="button" className={mode === "standard" ? "active" : ""} onClick={() => setMode("standard")}>
          Standard
        </button>
        <button type="button" className={mode === "deep" ? "active" : ""} onClick={() => setMode("deep")}>
          Deep
        </button>
      </div>

      <div className="v2-template-row">
        {templates.map((item) => (
          <button key={item} type="button" onClick={() => void submit(item)} disabled={pending}>
            {item}
          </button>
        ))}
      </div>

      <div className="v2-chat-log">
        {messages.map((message) => (
          <article key={message.id} className={`v2-chat-bubble ${message.role}`}>
            {message.role === "assistant" && message.renderPayload ? (
              <ChatResponseCard payload={message.renderPayload} degradedReason={message.degradedReason} />
            ) : (
              <p>{message.content}</p>
            )}
            <span>{message.timeLabel}</span>
          </article>
        ))}
        {pending && <p className="v2-chat-pending">TradeMaster is building the market view...</p>}
      </div>

      <form className="v2-chat-input" onSubmit={handleSubmit}>
        <label htmlFor="v2-chat-input" className="sr-only">
          Send market question
        </label>
        <input
          id="v2-chat-input"
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Ask: Why is this signal high confidence?"
        />
        <button type="submit" disabled={pending}>
          Send
        </button>
      </form>

      <p className="v2-footnote">Chat stays on the backend path only. No API token is exposed in the browser.</p>
    </section>
  );
}
