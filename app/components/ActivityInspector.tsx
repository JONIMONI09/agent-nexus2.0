"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { CopyButton } from "./CopyButton";
import type { AgentActivity, DebatePanel } from "./types";

type ActivityInspectorProps = {
  open: boolean;
  onClose: () => void;
  items: AgentActivity[];
  selected: AgentActivity | null;
};

const agentTag: Record<string, { label: string; color: string }> = {
  scout: { label: "SCOUT", color: "text-cyan" },
  analyst: { label: "ANALYST", color: "text-amber-300" },
  synthesizer: { label: "SYNTH", color: "text-lime" },
  main: { label: "AI", color: "text-white" },
  system: { label: "SYSTEM", color: "text-fog/60" },
};

const kindLabel: Record<string, string> = {
  think: "Reasoning step",
  status: "State change",
  tool: "Subagent commissioned",
  decision: "Your decision",
  error: "Wrong tool call",
  fallback: "Fallback",
  debate: "Debate panel",
  learning: "Learning update",
};

function time(ts: number) {
  return new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(ts);
}

function ToolPayload({ item }: { item: AgentActivity }) {
  const payload = item.payload ?? {};
  return (
    <div className="mt-2 space-y-2">
      {payload.arguments && (
        <div className="min-w-0 rounded-lg border border-white/10 bg-black/25 px-2.5 py-2">
          <p className="font-mono-label text-fog/50">Arguments</p>
          <p className="copy-safe mt-1 break-words font-mono text-[10px] leading-4 text-white/80">{JSON.stringify(payload.arguments)}</p>
        </div>
      )}
      {payload.approved !== undefined && (
        <p className={`copy-safe rounded-lg border px-2.5 py-2 text-[11px] leading-5 ${payload.approved ? "border-lime/30 bg-lime/[0.06] text-lime" : "border-coral/30 bg-coral/[0.07] text-coral"}`}>
          {payload.approved ? "✓ You allowed this subagent." : "✗ You denied this subagent — it never ran."}
          {payload.reason && !payload.approved ? ` (${payload.reason})` : ""}
        </p>
      )}
      {payload.debate && payload.debate.speeches.length > 0 && <DebateDetails panel={payload.debate} />}
      {payload.sources && payload.sources.length > 0 && (
        <div className="min-w-0 space-y-1.5">
          <p className="font-mono-label text-fog/50">Delivered sources ({payload.sources.length})</p>
          {payload.sources.slice(0, 5).map((source) => (
            <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="block min-w-0 truncate rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[11px] text-cyan hover:border-cyan/40">{source.title}</a>
          ))}
        </div>
      )}
      {item.detail && !payload.debate && (
        <p className="copy-safe whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-black/20 px-2.5 py-2 text-[11px] leading-5 text-fog/70">{item.detail}</p>
      )}
    </div>
  );
}

function DebateDetails({ panel }: { panel: DebatePanel }) {
  return (
    <div className="min-w-0 space-y-2">
      <p className="font-mono-label text-cyan">Debate: {panel.topic}</p>
      {panel.speeches.map((speech) => (
        <div key={speech.role} className="min-w-0 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-2">
          <p className="truncate font-mono-label text-white/85">{speech.role}</p>
          <p className="copy-safe mt-1 break-words text-[11px] leading-5 text-fog/80">{speech.speech}</p>
        </div>
      ))}
      {panel.synthesis && (
        <div className="min-w-0 rounded-lg border border-lime/25 bg-lime/[0.05] px-2.5 py-2">
          <p className="font-mono-label text-lime">Synthesis</p>
          <p className="copy-safe mt-1 break-words text-[11px] leading-5 text-white/85">{panel.synthesis}</p>
        </div>
      )}
    </div>
  );
}

function Entry({ item, highlighted, defaultOpen }: { item: AgentActivity; highlighted: boolean; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const tag = agentTag[item.agent] ?? agentTag.system;
  const isThink = item.kind === "think";
  const hasPayload = Boolean(item.payload && (item.payload.arguments || item.payload.approved !== undefined || item.payload.debate || (item.payload.sources && item.payload.sources.length > 0)));
  const expandable = isThink || hasPayload || Boolean(item.detail && item.detail.length > 140);

  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);

  return (
    <li className={`min-w-0 rounded-xl border px-3 py-2.5 transition-colors ${highlighted ? "border-cyan/45 bg-cyan/[0.06]" : "border-white/10 bg-white/[0.02]"}`}>
      <button type="button" onClick={() => expandable && setOpen((current) => !current)} className="flex w-full min-w-0 items-center gap-2 text-left" aria-expanded={open}>
        <span className={`shrink-0 font-mono text-[9px] tracking-wide ${tag.color}`}>{tag.label}</span>
        <span className="shrink-0 font-mono text-[9px] text-fog/35">{time(item.ts)}</span>
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-white/85">{item.text}</span>
        {expandable && <span className="shrink-0 font-mono text-[9px] text-fog/40">{open ? "▾" : "▸"}</span>}
      </button>
      {open && (
        <div className="mt-2">
          <div className="mb-2 flex justify-end">
            <CopyButton value={JSON.stringify({ agent: item.agent, kind: item.kind, text: item.text, detail: item.detail ?? null, payload: item.payload ?? null }, null, 2)} label="Copy entry" />
          </div>
          {isThink && <p className="copy-safe max-h-52 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-black/25 px-2.5 py-2 text-[11px] leading-5 text-cyan/75">{item.text}</p>}
          {!isThink && (item.kind === "tool" || item.kind === "decision" || item.kind === "debate") && <ToolPayload item={item} />}
          {!isThink && item.kind !== "tool" && item.kind !== "decision" && item.kind !== "debate" && item.detail && (
            <p className="copy-safe whitespace-pre-wrap break-words rounded-lg border border-white/10 bg-black/20 px-2.5 py-2 text-[11px] leading-5 text-fog/70">{item.detail}</p>
          )}
        </div>
      )}
    </li>
  );
}

export function ActivityInspector({ open, onClose, items, selected }: ActivityInspectorProps) {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const node = listRef.current?.querySelector("[data-highlighted='true']");
    node?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [open, selected]);

  const selectedItem = selected ? items.find((item) => item.id === selected.id) ?? selected : null;

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button type="button" aria-label="Close activity inspector" className="fixed inset-0 z-40 cursor-default bg-ink/70 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Agent activity inspector"
            className="fixed inset-x-0 bottom-0 z-40 mx-auto flex h-[74dvh] w-full max-w-2xl flex-col overflow-hidden border-t border-white/10 bg-[#0d131d]/95 shadow-[0_-20px_80px_rgba(0,0,0,0.45)] backdrop-blur-2xl sm:inset-x-3 sm:bottom-3 sm:h-[min(74dvh,660px)] sm:rounded-2xl sm:border"
            initial={{ y: "100%", opacity: 0.6 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "100%", opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 32 }}
          >
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4 py-4 sm:px-5">
              <div className="min-w-0">
                <p className="font-mono-label text-cyan">{selectedItem ? kindLabel[selectedItem.kind] ?? "Activity" : "Run timeline"}</p>
                <h2 className="mt-1 truncate text-base font-semibold text-white">{selectedItem ? selectedItem.text : "What the agents did"}</h2>
              </div>
              <button type="button" onClick={onClose} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/10 text-xl text-fog transition-colors hover:border-white/30 hover:text-white" aria-label="Close">×</button>
            </div>
            <ul ref={listRef} className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3 sm:px-4">
              {items.length === 0 && <p className="copy-safe px-1 font-mono text-[10px] leading-5 text-fog/40">No activity yet. Send a message to start a run.</p>}
              {[...items].reverse().map((item) => (
                <li key={item.id} data-highlighted={selectedItem?.id === item.id || undefined}>
                  <Entry item={item} highlighted={selectedItem?.id === item.id} defaultOpen={selectedItem?.id === item.id} />
                </li>
              ))}
            </ul>
            <p className="shrink-0 border-t border-white/10 px-4 py-2.5 font-mono text-[9px] text-fog/40 sm:px-5">Reasoning stays collapsed until you expand it. Nothing here leaves this device.</p>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
