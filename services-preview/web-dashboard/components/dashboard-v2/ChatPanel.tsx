"use client";

import { useMemo, useState } from "react";

import type { ChatContextState, ChatMessage } from "@/types/legacy-dashboard";

type ChatPanelProps = {
  messages: ChatMessage[];
  pending: boolean;
  context: ChatContextState;
  onSend: (text: string) => Promise<void>;
};

export function ChatPanel({ messages, pending, context, onSend }: ChatPanelProps) {
  const [value, setValue] = useState("");

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
    await onSend(cleaned);
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
            <p>{message.content}</p>
            {message.strategy && (
              <div className="v2-strategy-card">
                <section>
                  <h4>结论</h4>
                  <p>{message.strategy.summary}</p>
                </section>
                <section>
                  <h4>依据</h4>
                  <p>{message.strategy.evidence}</p>
                </section>
                <section>
                  <h4>风险</h4>
                  <p>{message.strategy.risk}</p>
                </section>
                <section>
                  <h4>下一步</h4>
                  <p>{message.strategy.nextActions}</p>
                </section>
              </div>
            )}
            <span>{message.timeLabel}</span>
          </article>
        ))}
        {pending && <p className="v2-chat-pending">Assistant is preparing strategy cards...</p>}
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

      <p className="v2-footnote">Chat is proxied to backend only. No API token is exposed in browser.</p>
    </section>
  );
}
