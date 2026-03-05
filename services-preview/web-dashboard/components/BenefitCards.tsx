"use client";

import { motion } from "framer-motion";
import { Bell, CandlestickChart, ShieldAlert } from "lucide-react";

const BENEFITS = [
  {
    title: "Sharper market context",
    body: "Track momentum, liquidity, and top movers with clear signal framing for faster trade planning.",
    Icon: CandlestickChart
  },
  {
    title: "Risk visibility first",
    body: "Monitor allocation, downside metrics, and warning panels before committing to high-beta moves.",
    Icon: ShieldAlert
  },
  {
    title: "Actionable alerting",
    body: "Promote repeatable setups into automation flows and keep your desk synced with market shifts.",
    Icon: Bell
  }
];

export function BenefitCards() {
  return (
    <section id="features" className="section-shell py-20">
      <div className="mb-8 max-w-3xl">
        <h2 className="font-editorial text-4xl leading-tight sm:text-5xl">Built for analysts who need clarity under pressure.</h2>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {BENEFITS.map(({ Icon, title, body }, index) => (
          <motion.article
            key={title}
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.32, delay: index * 0.06, ease: "easeOut" }}
            whileHover={{ y: -2 }}
            className="card-surface p-6"
          >
            <div className="mb-4 inline-flex rounded-xl bg-accent-soft p-2 text-accent-deep">
              <Icon size={20} />
            </div>
            <h3 className="text-lg font-semibold text-ink">{title}</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted">{body}</p>
          </motion.article>
        ))}
      </div>
    </section>
  );
}
