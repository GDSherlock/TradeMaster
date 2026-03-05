"use client";
import { Activity, Bot, RefreshCcw, Wifi, WifiOff } from "lucide-react";

type DashboardHeaderProps = {
  symbolOptions: string[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  interval: string;
  onIntervalChange: (interval: string) => void;
  apiOk: boolean;
  dataOk: boolean;
  wsConnected: boolean;
  mlOk: boolean;
  rateLimited: boolean;
  updatedAtLabel: string;
  onRefresh: () => void;
  refreshing: boolean;
};

const INTERVAL_OPTIONS = ["1m", "5m", "15m", "1h", "4h", "1d"];

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`v2-status-dot ${ok ? "ok" : "fail"}`} aria-hidden="true" />;
}

export function Header({
  symbolOptions,
  selectedSymbol,
  onSelectSymbol,
  interval,
  onIntervalChange,
  apiOk,
  dataOk,
  wsConnected,
  mlOk,
  rateLimited,
  updatedAtLabel,
  onRefresh,
  refreshing
}: DashboardHeaderProps) {
  return (
    <header className="v2-header">
      <div className="v2-header-main">
        <div className="v2-brand">
          <span className="v2-brand-mark">TM</span>
          <div>
            <h1>TradeMaster Intelligence</h1>
            <p>Market, Signals, Strategy Chat, and ML Console in one cockpit</p>
          </div>
        </div>

        <div className="v2-header-actions">
          <button type="button" className="v2-icon-btn" onClick={onRefresh} disabled={refreshing} aria-label="Refresh all panels">
            <RefreshCcw size={16} className={refreshing ? "spin" : ""} />
          </button>
          <a href="/ml-validation" className="v2-link-btn">
            Open ML Deep View
          </a>
        </div>
      </div>

      <div className="v2-header-controls">
        <label className="v2-field">
          <span>Symbol</span>
          <input
            list="v2-symbol-options"
            value={selectedSymbol}
            onChange={(event) => onSelectSymbol(event.target.value.toUpperCase())}
            placeholder="BTCUSDT"
          />
          <datalist id="v2-symbol-options">
            {symbolOptions.map((symbol) => (
              <option key={symbol} value={symbol} />
            ))}
          </datalist>
        </label>

        <label className="v2-field">
          <span>Interval</span>
          <select value={interval} onChange={(event) => onIntervalChange(event.target.value)}>
            {INTERVAL_OPTIONS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <div className="v2-status-strip" role="status" aria-live="polite">
          <div className="v2-status-item">
            <Activity size={14} />
            <StatusDot ok={apiOk} />
            API {apiOk ? "Connected" : "Down"}
          </div>
          <div className="v2-status-item">
            {wsConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
            <StatusDot ok={wsConnected} />
            WS {wsConnected ? "Live" : "Retrying"}
          </div>
          <div className="v2-status-item">
            <Bot size={14} />
            <StatusDot ok={mlOk} />
            ML {mlOk ? "Ready" : "Lagging"}
          </div>
          {rateLimited && <div className="v2-status-item warn">Rate Limited</div>}
          <div className="v2-status-item subtle">Data {dataOk ? "Fresh" : "Stale"}</div>
          <div className="v2-status-item subtle">Updated {updatedAtLabel}</div>
        </div>
      </div>
    </header>
  );
}
