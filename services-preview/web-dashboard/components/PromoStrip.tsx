"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

export function PromoStrip() {
  return (
    <section className="section-shell" aria-label="Promotional announcement">
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.5 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="flex flex-wrap items-center gap-3 rounded-2xl border border-accent/20 bg-gradient-to-r from-accent-soft/90 to-white px-5 py-4"
      >
        <span className="rounded-full bg-accent px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white">Launch Week</span>
        <p className="text-sm text-ink">
          New users can test the analyst workspace with full market pulse widgets and alert simulation.
        </p>
        <a href="#pricing" className="focus-ring ml-auto inline-flex items-center gap-1 text-sm font-semibold text-accent-deep">
          See details
          <ArrowRight size={16} />
        </a>
      </motion.div>
    </section>
  );
}
