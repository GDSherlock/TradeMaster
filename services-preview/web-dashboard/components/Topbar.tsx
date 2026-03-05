"use client";

import { Menu, Search } from "lucide-react";

type TopbarProps = {
  menuOpen: boolean;
  onMenuToggle: () => void;
  dataMode: "mock" | "live";
  source: "mock" | "live" | "mock-fallback";
  onDataModeChange: (mode: "mock" | "live") => void;
};

export function Topbar({ menuOpen, onMenuToggle, dataMode, onDataModeChange, source }: TopbarProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-black/10 bg-white/80 px-4 py-3 backdrop-blur-md sm:px-6">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="focus-ring inline-flex rounded-xl border border-black/10 p-2 text-ink lg:hidden"
          aria-controls="mobile-sidebar"
          aria-expanded={menuOpen}
          onClick={onMenuToggle}
        >
          <Menu size={18} />
        </button>

        <label className="relative min-w-[220px] flex-1">
          <span className="sr-only">Search market pairs</span>
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="search"
            placeholder="Search pair, signal, or tag"
            className="focus-ring w-full rounded-full border border-black/10 bg-white py-2.5 pl-9 pr-4 text-sm text-ink placeholder:text-muted"
          />
        </label>

        <div className="inline-flex items-center rounded-full border border-black/10 bg-white p-1 text-xs font-medium">
          <button
            type="button"
            onClick={() => onDataModeChange("mock")}
            className={`focus-ring rounded-full px-3 py-1.5 ${dataMode === "mock" ? "bg-ink text-white" : "text-muted"}`}
          >
            Mock
          </button>
          <button
            type="button"
            onClick={() => onDataModeChange("live")}
            className={`focus-ring rounded-full px-3 py-1.5 ${dataMode === "live" ? "bg-ink text-white" : "text-muted"}`}
          >
            Live (beta)
          </button>
        </div>

        <div className="rounded-full border border-black/10 bg-white px-3 py-1.5 text-xs font-medium text-muted">
          Source: {source}
        </div>

        <button className="focus-ring inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/10 bg-accent-soft text-sm font-semibold text-accent-deep">
          KJ
        </button>
      </div>
    </header>
  );
}
