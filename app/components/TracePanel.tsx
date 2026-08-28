"use client";

import { motion } from "framer-motion";

import type { AgentActivity, AgentActivityKind } from "./types";

type TracePanelProps = {
  items: AgentActivity[];
  active: boolean;
  onSelect: (item: AgentActivity) => void;
};

const kindMeta: Record<AgentActivityKind, { label: string; dot: string; chip: string; dim: boolean }> = {
  think: { label: "THINK", dot: "bg-white/35", chip: "border-white/10 bg-white/[0.02] text-fog/70", dim: true },
  status: { label: "STATE", dot: "bg-white/50", chip: "border-white/12 bg-white/[0.035] text-white/80", dim: false },
  tool: { label: "TOOL", dot: "bg-coral", chip: "border-coral/30 bg-coral/[0.06] text-coral", dim: false },
  decision: { label: "GATE", dot: "bg-lime", chip: "border-lime/30 bg-lime/[0.06] text-lime", dim: false },
  error: { label: "MISCALL", dot: "bg-coral", chip: "border-coral/40 bg-coral/[0.1] text-coral", dim: false },
  fallback: { label: "FALLBACK", dot: "bg-amber-300", chip: "border-amber-300/35 bg-amber-300/[0.08] text-amber-300", dim: false },
  debate: { label: "DEBATE", dot: "bg-cyan", chip: "border-cyan/35 bg-cyan/[0.07] text-cyan", dim: false },
  learning: { label: "LEARN", dot: "bg-lime", chip: "border-lime/35 bg-lime/[0.08] text-lime", dim: false },
};

export function TracePanel({ items, active, onSelect }: TracePanelProps) {
  if (items.length === 0) return null;
  const visible = items.slice(-8);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-3 sm:px-6">
      <div className="overflow-hidden rounded-xl border border-white/10 bg-black/15 px-3 py-3">
        <div className="mb-2 flex items-center justify-between gap-3">
          <span className="font-mono-label text-fog/55">Agent activity — tap a step to inspect</span>
          {active && <span className="flex items-center gap-2 font-mono text-[10px] text-lime"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-lime" />LIVE</span>}
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {visible.map((item, index) => {
            const meta = kindMeta[item.kind];
            const isLatest = index === visible.length - 1;
            return (
              <motion.button
                key={item.id}
                type="button"
                onClick={() => onSelect(item)}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                whileTap={{ scale: 0.97 }}
                className={`flex min-w-[140px] max-w-[220px] shrink-0 items-start gap-2 rounded-lg border px-2.5 py-2 text-left transition-colors ${meta.chip} hover:border-white/30 ${meta.dim ? "opacity-75" : ""}`}
                aria-label={`Inspect: ${item.text}`}
              >
                <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${meta.dot}`} />
                <span className="min-w-0">
                  <span className={`block truncate text-[11px] font-medium ${meta.dim ? "italic text-fog/60" : ""}`}>{item.text}</span>
                  {item.detail && <span className="mt-0.5 block truncate text-[10px] text-fog/55">{item.detail}</span>}
                </span>
                {isLatest && active && <span className="ml-auto mt-1 h-2 w-2 shrink-0 animate-ping rounded-full bg-lime/50" />}
              </motion.button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
