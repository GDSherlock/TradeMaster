"use client";

import Link from "next/link";
import { Menu, X } from "lucide-react";
import { useState } from "react";

const NAV_ITEMS = [
  { href: "#features", label: "Features" },
  { href: "#markets", label: "Markets" },
  { href: "#insights", label: "Insights" },
  { href: "#pricing", label: "Pricing" }
];

export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-black/5 bg-white/75 backdrop-blur-lg">
      <nav className="section-shell flex h-20 items-center justify-between" aria-label="Main navigation">
        <Link href="/" className="focus-ring inline-flex items-center gap-3 rounded-full px-1 py-1">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-ink text-sm font-semibold text-white">CA</span>
          <span className="font-semibold tracking-tight">Crypto Analyst</span>
        </Link>

        <ul className="hidden items-center gap-8 text-sm text-muted lg:flex">
          {NAV_ITEMS.map((item) => (
            <li key={item.label}>
              <a href={item.href} className="focus-ring rounded-full px-2 py-1 transition hover:text-ink">
                {item.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="hidden items-center gap-3 sm:flex">
          <button className="focus-ring rounded-full bg-ink px-5 py-2 text-sm font-medium text-white transition hover:bg-ink/90">
            Try Demo
          </button>
          <button className="focus-ring rounded-full border border-black/10 px-5 py-2 text-sm font-medium transition hover:border-black/20 hover:bg-black/5">
            Sign in
          </button>
        </div>

        <button
          type="button"
          className="focus-ring inline-flex rounded-xl border border-black/10 p-2 text-ink lg:hidden"
          aria-label={open ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={open}
          onClick={() => setOpen((prev) => !prev)}
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </nav>

      {open && (
        <div className="border-t border-black/10 bg-white px-5 py-4 lg:hidden">
          <ul className="space-y-2 text-sm">
            {NAV_ITEMS.map((item) => (
              <li key={item.label}>
                <a
                  href={item.href}
                  className="focus-ring block rounded-lg px-3 py-2 text-muted transition hover:bg-black/5 hover:text-ink"
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex gap-2">
            <button className="focus-ring flex-1 rounded-full bg-ink px-4 py-2 text-sm font-medium text-white">Try Demo</button>
            <button className="focus-ring flex-1 rounded-full border border-black/10 px-4 py-2 text-sm font-medium">Sign in</button>
          </div>
        </div>
      )}
    </header>
  );
}
