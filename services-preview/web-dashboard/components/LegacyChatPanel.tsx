"use client";

import { useState } from "react";

import type { ChatMessage } from "@/types/legacy-dashboard";

type LegacyChatPanelProps = {
  messages: ChatMessage[];
  onSend: (text: string) => Promise<void>;
  pending: boolean;
};

export function LegacyChatPanel({ messages, onSend, pending }: LegacyChatPanelProps) {
  const [value, setValue] = useState("");

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = value.trim();
    if (!text || pending) {
      return;
    }
    setValue("");
    await onSend(text);
  }

  return (
    <section className="legacy-panel legacy-chat" aria-label="Signal chatbox">
      <div className="legacy-panel-head">
        <h1>Signal Chatbox</h1>
        <p>Ask for signal rationale, indicator context, and risk notes.</p>
      </div>

      <div className="legacy-chat-shell">
        <div className="legacy-chat-messages">
          {messages.map((message) => (
            <article key={message.id} className={`legacy-chat-msg ${message.role === "user" ? "user" : "assistant"}`}>
              <p>{message.content}</p>
              <span>{message.timeLabel}</span>
            </article>
          ))}
          {pending && <p className="legacy-chat-pending">Assistant is thinking...</p>}
        </div>

        <form className="legacy-chat-input" onSubmit={handleSubmit}>
          <label htmlFor="chat-text" className="sr-only">
            Ask a market question
          </label>
          <input
            id="chat-text"
            type="text"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Ask: Why did ETH trigger breakout?"
          />
          <button type="submit" disabled={pending}>
            Send
          </button>
        </form>

        <p className="legacy-chat-note">Chat is served by chat-service. Keys are kept in backend only.</p>
      </div>
    </section>
  );
}
