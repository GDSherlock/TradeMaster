import { Activity, Database } from "lucide-react";

type LegacyTopbarProps = {
  apiOk: boolean;
  dataOk: boolean;
  wsConnected: boolean;
  updatedAtLabel: string;
};

function Dot({ ok }: { ok: boolean }) {
  return <span className={`legacy-status-dot ${ok ? "ok" : "fail"}`} aria-hidden="true" />;
}

export function LegacyTopbar({ apiOk, dataOk, wsConnected, updatedAtLabel }: LegacyTopbarProps) {
  return (
    <header className="legacy-topbar">
      <div className="legacy-brand">
        <span className="legacy-brand-mark">CA</span>
        <div>
          <p className="legacy-brand-title">Crypto Analyst</p>
          <p className="legacy-brand-subtitle">Signal-centric market cockpit</p>
        </div>
      </div>

      <div className="legacy-status-wrap" role="status" aria-live="polite">
        <div className="legacy-status-row">
          <Activity size={14} />
          <Dot ok={apiOk} />
          <span>API: {apiOk ? "Connected" : "Unavailable"}</span>
          <a className="legacy-nav-link" href="/ml-validation">
            ML Validation
          </a>
        </div>
        <div className="legacy-status-row">
          <Database size={14} />
          <Dot ok={dataOk} />
          <span>Data: {dataOk ? "Live" : "Stale"}</span>
          <span className="legacy-status-time">WS: {wsConnected ? "Connected" : "Reconnecting"}</span>
          <span className="legacy-status-time">Updated: {updatedAtLabel}</span>
        </div>
      </div>
    </header>
  );
}
