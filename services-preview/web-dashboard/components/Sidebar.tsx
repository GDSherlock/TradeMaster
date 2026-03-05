"use client";

import Link from "next/link";
import { BarChart3, BellRing, Brain, LayoutDashboard, Shield, Wallet, X } from "lucide-react";

type SidebarProps = {
  open: boolean;
  onClose: () => void;
};

const ITEMS = [
  { label: "Overview", href: "/app", Icon: LayoutDashboard, active: true },
  { label: "Signals", href: "#", Icon: Brain },
  { label: "Markets", href: "#", Icon: BarChart3 },
  { label: "Portfolio", href: "#", Icon: Wallet },
  { label: "Risk", href: "#", Icon: Shield },
  { label: "Alerts", href: "#", Icon: BellRing }
];

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      <aside className="hidden w-72 shrink-0 border-r border-black/10 bg-white/70 p-5 backdrop-blur-md lg:block">
        <SidebarInner onClose={onClose} />
      </aside>

      {open && <button type="button" className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={onClose} aria-label="Close menu" />}

      <aside
        id="mobile-sidebar"
        className={`fixed left-0 top-0 z-50 h-full w-72 border-r border-black/10 bg-white p-5 transition-transform duration-300 lg:hidden ${open ? "translate-x-0" : "-translate-x-full"}`}
        aria-hidden={!open}
      >
        <SidebarInner onClose={onClose} mobile />
      </aside>
    </>
  );
}

function SidebarInner({ onClose, mobile = false }: { onClose: () => void; mobile?: boolean }) {
  return (
    <div className="flex h-full flex-col">
      <div className="mb-7 flex items-center justify-between">
        <Link href="/" className="focus-ring inline-flex items-center gap-2 rounded-lg">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-ink text-xs font-semibold text-white">CA</span>
          <span className="font-semibold">Crypto Analyst</span>
        </Link>
        {mobile && (
          <button
            type="button"
            className="focus-ring rounded-lg border border-black/10 p-1.5 text-ink"
            onClick={onClose}
            aria-label="Close navigation"
          >
            <X size={16} />
          </button>
        )}
      </div>

      <nav aria-label="Dashboard navigation">
        <ul className="space-y-1">
          {ITEMS.map(({ label, href, Icon, active }) => (
            <li key={label}>
              <a
                href={href}
                className={`focus-ring flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${
                  active ? "bg-accent text-white" : "text-muted hover:bg-black/5 hover:text-ink"
                }`}
              >
                <Icon size={16} />
                {label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="mt-auto rounded-2xl border border-accent/20 bg-accent-soft/60 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-accent-deep">Automation</p>
        <p className="mt-1 text-sm text-ink">12 rules live. 3 high-priority alerts in watchlist.</p>
      </div>
    </div>
  );
}
