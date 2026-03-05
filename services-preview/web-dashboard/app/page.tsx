"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LegacyChatPanel } from "@/components/LegacyChatPanel";
import { LegacyDashboardPanel } from "@/components/LegacyDashboardPanel";
import { LegacyTopbar } from "@/components/LegacyTopbar";
import {
  createSignalSocket,
  fetchApiHealth,
  fetchIndicatorRows,
  fetchIndicatorTables,
  fetchMomentum,
  fetchSignalsLatest,
  fetchTrendHistory,
  resolveRuntimeEndpoints,
  sendChatMessage
} from "@/lib/live-data";
import type { ChatMessage, IndicatorRow, MomentumSnapshot, SignalEvent, SignalViewMode, TrendPoint } from "@/types/legacy-dashboard";

const SIGNAL_WINDOW_SIZE = 60;

function formatClock(timestamp: number | null): string {
  if (!timestamp) {
    return "--";
  }
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function nowLabel(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function mergeSignalEvents(current: SignalEvent[], incoming: SignalEvent[]): SignalEvent[] {
  const map = new Map<number, SignalEvent>();
  for (const item of current) {
    map.set(item.id, item);
  }
  for (const item of incoming) {
    map.set(item.id, item);
  }
  return [...map.values()]
    .sort((a, b) => b.id - a.id)
    .slice(0, SIGNAL_WINDOW_SIZE);
}

export default function LegacyDashboardPage() {
  const endpoints = useMemo(() => resolveRuntimeEndpoints(), []);

  const [apiOk, setApiOk] = useState(false);
  const [dataOk, setDataOk] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const [momentum, setMomentum] = useState<MomentumSnapshot | null>(null);
  const [signalEvents, setSignalEvents] = useState<SignalEvent[]>([]);
  const [signalMode, setSignalMode] = useState<SignalViewMode>("events");

  const [trendInterval, setTrendInterval] = useState(endpoints.defaultInterval);
  const [trendMap, setTrendMap] = useState<Record<string, TrendPoint[]>>({});

  const [indicatorTables, setIndicatorTables] = useState<string[]>([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState(endpoints.defaultSymbol);
  const [indicatorRows, setIndicatorRows] = useState<IndicatorRow[]>([]);

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Connected. Ask about latest signal triggers, momentum changes, or indicator meaning.",
      timeLabel: nowLabel()
    }
  ]);
  const [chatPending, setChatPending] = useState(false);

  const sinceIdRef = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const refreshTimerRef = useRef<number | null>(null);
  const fallbackTimerRef = useRef<number | null>(null);
  const unmountedRef = useRef(false);

  const applySignals = useCallback((incoming: SignalEvent[]) => {
    if (incoming.length === 0) {
      return;
    }

    setSignalEvents((current) => {
      const merged = mergeSignalEvents(current, incoming);
      const maxId = merged.length > 0 ? merged[0].id : 0;
      sinceIdRef.current = Math.max(sinceIdRef.current, maxId);
      return merged;
    });

    setDataOk(true);
    setUpdatedAt(Date.now());
  }, []);

  const refreshHealthAndMomentum = useCallback(async () => {
    const [health, momentumData] = await Promise.all([
      fetchApiHealth(endpoints.apiBase),
      fetchMomentum(endpoints.apiBase, endpoints.defaultExchange)
    ]);

    if (unmountedRef.current) {
      return;
    }

    setApiOk(health);
    if (momentumData) {
      setMomentum(momentumData);
      setDataOk(true);
      if (momentumData.timestamp) {
        setUpdatedAt(momentumData.timestamp);
      } else {
        setUpdatedAt(Date.now());
      }
    }
  }, [endpoints.apiBase, endpoints.defaultExchange]);

  const refreshTrends = useCallback(async () => {
    const results = await Promise.all(
      endpoints.trendSymbols.map(async (symbol) => {
        const rows = await fetchTrendHistory(
          endpoints.apiBase,
          symbol,
          trendInterval,
          endpoints.defaultExchange,
          60
        );
        return [symbol, rows] as const;
      })
    );

    if (unmountedRef.current) {
      return;
    }

    const nextMap: Record<string, TrendPoint[]> = {};
    for (const [symbol, rows] of results) {
      nextMap[symbol] = rows;
    }
    setTrendMap(nextMap);
    if (results.some(([, rows]) => rows.length > 0)) {
      setDataOk(true);
      setUpdatedAt(Date.now());
    }
  }, [endpoints.apiBase, endpoints.defaultExchange, endpoints.trendSymbols, trendInterval]);

  const refreshIndicators = useCallback(async () => {
    if (!selectedTable) {
      setIndicatorRows([]);
      return;
    }

    const rows = await fetchIndicatorRows(endpoints.apiBase, selectedTable, selectedSymbol, trendInterval, 40);
    if (unmountedRef.current) {
      return;
    }
    setIndicatorRows(rows);
  }, [endpoints.apiBase, selectedTable, selectedSymbol, trendInterval]);

  const refreshSignalFallback = useCallback(async () => {
    const rows = await fetchSignalsLatest(endpoints.apiBase, SIGNAL_WINDOW_SIZE);
    if (unmountedRef.current) {
      return;
    }
    applySignals(rows);
  }, [applySignals, endpoints.apiBase]);

  const connectSignalWs = useCallback(() => {
    if (unmountedRef.current) {
      return;
    }

    if (socketRef.current) {
      socketRef.current.close();
    }

    const socket = createSignalSocket(
      endpoints.signalWsUrl,
      sinceIdRef.current,
      (event) => {
        applySignals([event]);
      },
      (connected) => {
        if (unmountedRef.current) {
          return;
        }
        setWsConnected(connected);
        if (!connected) {
          if (reconnectTimerRef.current) {
            window.clearTimeout(reconnectTimerRef.current);
          }
          reconnectTimerRef.current = window.setTimeout(() => {
            connectSignalWs();
          }, 2500);
        }
      }
    );

    socketRef.current = socket;
  }, [applySignals, endpoints.signalWsUrl]);

  useEffect(() => {
    void refreshTrends();
  }, [refreshTrends]);

  useEffect(() => {
    void refreshIndicators();
  }, [refreshIndicators]);

  useEffect(() => {
    unmountedRef.current = false;

    const bootstrap = async () => {
      await refreshHealthAndMomentum();
      await refreshTrends();
      const [signalRows, tables] = await Promise.all([
        fetchSignalsLatest(endpoints.apiBase, SIGNAL_WINDOW_SIZE),
        fetchIndicatorTables(endpoints.apiBase)
      ]);

      if (unmountedRef.current) {
        return;
      }

      applySignals(signalRows);

      if (tables.length > 0) {
        setIndicatorTables(tables);
        setSelectedTable((current) => current || tables[0]);
      }

      connectSignalWs();

      refreshTimerRef.current = window.setInterval(() => {
        void refreshHealthAndMomentum();
        void refreshTrends();
      }, endpoints.refreshIntervalMs);

      fallbackTimerRef.current = window.setInterval(() => {
        void refreshSignalFallback();
      }, 15000);
    };

    void bootstrap();

    return () => {
      unmountedRef.current = true;
      if (socketRef.current) {
        socketRef.current.close();
      }
      if (refreshTimerRef.current) {
        window.clearInterval(refreshTimerRef.current);
      }
      if (fallbackTimerRef.current) {
        window.clearInterval(fallbackTimerRef.current);
      }
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [
    applySignals,
    connectSignalWs,
    endpoints.apiBase,
    endpoints.refreshIntervalMs,
    refreshHealthAndMomentum,
    refreshSignalFallback,
    refreshTrends
  ]);

  const handleSendChat = useCallback(
    async (text: string) => {
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: text,
        timeLabel: nowLabel()
      };
      setChatMessages((current) => [...current, userMessage]);
      setChatPending(true);

      try {
        const reply = await sendChatMessage(endpoints.chatBase, text);
        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: reply,
          timeLabel: nowLabel()
        };
        if (!unmountedRef.current) {
          setChatMessages((current) => [...current, assistantMessage]);
        }
      } catch (error) {
        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: `Chat request failed: ${error instanceof Error ? error.message : "unknown error"}`,
          timeLabel: nowLabel()
        };
        if (!unmountedRef.current) {
          setChatMessages((current) => [...current, assistantMessage]);
        }
      } finally {
        if (!unmountedRef.current) {
          setChatPending(false);
        }
      }
    },
    [endpoints.chatBase]
  );

  return (
    <div className="legacy-shell">
      <div className="legacy-ambient" aria-hidden="true" />

      <LegacyTopbar
        apiOk={apiOk}
        dataOk={dataOk}
        wsConnected={wsConnected}
        updatedAtLabel={formatClock(updatedAt)}
      />

      <main className="legacy-layout">
        <LegacyDashboardPanel
          momentum={momentum}
          signalEvents={signalEvents}
          signalMode={signalMode}
          onSignalModeChange={setSignalMode}
          trendSymbols={endpoints.trendSymbols}
          trendInterval={trendInterval}
          onTrendIntervalChange={setTrendInterval}
          trendMap={trendMap}
          indicatorTables={indicatorTables}
          selectedTable={selectedTable}
          onSelectedTableChange={setSelectedTable}
          selectedSymbol={selectedSymbol}
          onSelectedSymbolChange={setSelectedSymbol}
          indicatorRows={indicatorRows}
          updatedAtLabel={formatClock(updatedAt)}
        />

        <LegacyChatPanel messages={chatMessages} onSend={handleSendChat} pending={chatPending} />
      </main>
    </div>
  );
}
