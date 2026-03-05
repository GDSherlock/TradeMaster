"use client";

import { motion } from "framer-motion";
import { Activity, BellRing, Gauge, ShieldCheck } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";

import { getLandingModules } from "@/lib/mock-data";

const iconMap = [Gauge, Activity, ShieldCheck, BellRing];

export function ModuleGrid() {
  const modules = getLandingModules();

  return (
    <section id="markets" className="section-shell py-20">
      <div className="mb-8 flex items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Product modules</p>
          <h2 className="mt-2 font-editorial text-4xl leading-tight sm:text-5xl">Your crypto operating surface.</h2>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {modules.map((module, index) => {
          const Icon = iconMap[index] ?? Gauge;
          return (
            <motion.article
              key={module.name}
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.28 }}
              transition={{ duration: 0.36, ease: "easeOut", delay: index * 0.06 }}
              whileHover={{ y: -2, boxShadow: "0 22px 48px rgba(20, 122, 104, 0.16)" }}
              className="card-surface p-6"
            >
              <div className="mb-4 flex items-center justify-between">
                <div className="inline-flex rounded-xl bg-accent-soft p-2 text-accent-deep">
                  <Icon size={18} />
                </div>
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">Live metric</span>
              </div>
              <h3 className="text-xl font-semibold text-ink">{module.name}</h3>
              <p className="mt-2 text-sm text-muted">{module.description}</p>
              <p className="mt-4 text-lg font-semibold text-ink">{module.metric}</p>
              <div className="mt-4 h-16">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={module.sparkline.map((value, idx) => ({ idx, value }))}>
                    <Line type="monotone" dataKey="value" stroke="#147a68" strokeWidth={2.2} dot={false} />
                    <Tooltip
                      cursor={{ stroke: "rgba(20,122,104,0.25)", strokeDasharray: "3 3" }}
                      formatter={(value) => [`${value}`, "Index"]}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </motion.article>
          );
        })}
      </div>
    </section>
  );
}
