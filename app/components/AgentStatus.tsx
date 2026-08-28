"use client";

import { motion } from "framer-motion";

import type { AgentState } from "./types";

type AgentStatusProps = {
  agent: "scout" | "analyst" | "synthesizer";
  state: AgentState;
  onClick?: () => void;
};

const agentCopy = {
  scout: {
    name: "The Scout",
    short: "A",
    accent: "text-cyan",
    ring: "border-cyan/30",
  },
  analyst: {
    name: "The Analyst",
    short: "C",
    accent: "text-amber-300",
    ring: "border-amber-300/30",
  },
  synthesizer: {
    name: "The Synthesizer",
    short: "B",
    accent: "text-lime",
    ring: "border-lime/30",
  },
};

export function AgentStatus({ agent, state, onClick }: AgentStatusProps) {
  const copy = agentCopy[agent];
  const isActive = state.phase === "working" || state.phase === "waiting";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={`flex w-full min-w-0 items-center gap-3 rounded-xl border-l-2 pl-3 text-left transition-colors ${copy.ring} ${onClick ? "cursor-pointer border-r border-t border-b border-white/10 px-2 py-2.5 hover:bg-white/[0.04]" : "border-r-0 border-t-0 border-b-0"}`}
    >
      <div className="relative grid h-8 w-8 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[0.05] font-mono text-xs font-semibold text-white">
        {isActive && (
          <motion.span
            className={`absolute inset-0 rounded-full border ${copy.ring}`}
            animate={{ scale: [1, 1.25], opacity: [0.8, 0] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        <span className={copy.accent}>{copy.short}</span>
      </div>
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <p className="truncate text-xs font-medium text-white">{copy.name}</p>
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isActive ? "animate-pulse bg-lime" : state.phase === "error" ? "bg-coral" : "bg-white/25"}`} />
        </div>
        <p className="truncate text-[11px] text-fog/70">{state.label}</p>
      </div>
      {onClick && <span className="ml-auto shrink-0 font-mono text-[10px] text-fog/40">VIEW ›</span>}
    </button>
  );
}
