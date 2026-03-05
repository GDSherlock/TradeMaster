"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { BellRing, ShieldCheck, TrendingUp } from "lucide-react";

const previewRows = [
  { pair: "BTCUSDT", confidence: 84, status: "Long Bias" },
  { pair: "ETHUSDT", confidence: 73, status: "Breakout Watch" },
  { pair: "SOLUSDT", confidence: 66, status: "Risk-Adjusted Short" }
];

export function Hero() {
  return (
    <section className="section-shell grid gap-10 pb-20 pt-14 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:pb-28 lg:pt-20">
      <motion.div
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: "easeOut" }}
      >
        <p className="mb-5 inline-flex items-center rounded-full border border-accent/20 bg-accent-soft px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-accent-deep">
          Crypto Intelligence Platform
        </p>
        <h1 className="font-editorial text-5xl font-semibold leading-[0.92] tracking-tight text-ink sm:text-6xl lg:text-7xl">
          Read the market
          <br />
          before it moves.
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
          A modern analyst workspace for crypto signals, portfolio risk posture, and automated alerts, designed to turn noisy flows
          into confident decisions.
        </p>
        <div className="mt-9 flex flex-wrap items-center gap-3">
          <Link
            href="/app"
            className="focus-ring rounded-full bg-ink px-6 py-3 text-sm font-semibold text-white transition hover:bg-ink/90"
          >
            Try Demo
          </Link>
          <a
            href="#features"
            className="focus-ring inline-flex items-center rounded-full border border-black/10 px-6 py-3 text-sm font-semibold text-ink transition hover:bg-black/5"
          >
            Explore Features
          </a>
        </div>
      </motion.div>

      <motion.aside
        initial={{ opacity: 0, y: 28 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut", delay: 0.1 }}
        className="card-surface overflow-hidden p-5 sm:p-6"
        aria-label="Application preview"
      >
        <div className="rounded-2xl border border-black/10 bg-gradient-to-br from-white to-accent-soft/40 p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">Live Signal Board</h2>
            <span className="rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-white">Streaming</span>
          </div>
          <div className="space-y-3">
            {previewRows.map((row) => (
              <article key={row.pair} className="rounded-xl border border-black/10 bg-white p-3">
                <div className="flex items-center justify-between text-sm">
                  <strong>{row.pair}</strong>
                  <span className="font-medium text-accent-deep">{row.confidence}%</span>
                </div>
                <p className="mt-1 text-xs text-muted">{row.status}</p>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/10">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${row.confidence}%` }} />
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
          <div className="rounded-xl border border-black/10 bg-white p-3 text-center">
            <TrendingUp className="mx-auto mb-1 h-4 w-4 text-accent" />
            Pulse
          </div>
          <div className="rounded-xl border border-black/10 bg-white p-3 text-center">
            <ShieldCheck className="mx-auto mb-1 h-4 w-4 text-accent" />
            Risk
          </div>
          <div className="rounded-xl border border-black/10 bg-white p-3 text-center">
            <BellRing className="mx-auto mb-1 h-4 w-4 text-accent" />
            Alerts
          </div>
        </div>
      </motion.aside>
    </section>
  );
}
