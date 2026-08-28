"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

export type FsTodo = { id: string; task: string; completed: boolean; origin: string; messages?: { from: string; text: string }[] };

export type FsFeedItem = {
  id: string;
  kind: "agent" | "tool" | "result" | "mismatch" | "loop" | "consent" | "complete" | "error" | "todos";
  text: string;
  detail?: string;
  ok?: boolean;
  ts: number;
};

type FsAgentPanelProps = {
  open: boolean;
  onClose: () => void;
  running: boolean;
  feed: FsFeedItem[];
  todos: FsTodo[];
  pendingTool: { tool: string; arguments: Record<string, unknown> } | null;
  onDecision: (approved: boolean) => void;
  decisionBusy: boolean;
  summary: string;
};

const kindMeta: Record<FsFeedItem["kind"], { label: string; color: string }> = {
  agent: { label: "TEAM", color: "text-cyan" },
  tool: { label: "TOOL", color: "text-white/85" },
  result: { label: "RESULT", color: "text-fog/70" },
  mismatch: { label: "MISMATCH", color: "text-coral" },
  loop: { label: "⚠ LOOP", color: "text-amber-300" },
  consent: { label: "CONSENT", color: "text-coral" },
  complete: { label: "DONE", color: "text-lime" },
  error: { label: "ERROR", color: "text-coral" },
  todos: { label: "TODOS", color: "text-lime" },
};

export function FsAgentPanel({ open, onClose, running, feed, todos, pendingTool, onDecision, decisionBusy, summary }: FsAgentPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pendingTool) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose, pendingTool]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [feed]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button type="button" aria-label="Close filesystem agent" className="fixed inset-0 z-40 cursor-default bg-ink/70 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={running ? undefined : onClose} />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Filesystem agent"
            className="fixed inset-x-0 bottom-0 z-40 mx-auto flex h-[76dvh] w-full max-w-3xl flex-col overflow-hidden border-t border-white/10 bg-[#0d131d]/95 shadow-[0_-20px_80px_rgba(0,0,0,0.45)] backdrop-blur-2xl sm:inset-x-3 sm:bottom-3 sm:h-[min(76dvh,680px)] sm:rounded-2xl sm:border"
            initial={{ y: "100%", opacity: 0.6 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "100%", opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 32 }}
          >
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4 py-4 sm:px-5">
              <div className="min-w-0">
                <p className="font-mono-label text-cyan">Filesystem agent {running && <span className="ml-2 inline-flex items-center gap-1.5 text-lime"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-lime" />RUNNING</span>}</p>
                <h2 className="mt-1 truncate text-base font-semibold text-white">Team workspace — jailed to projects/</h2>
              </div>
              <button type="button" onClick={onClose} disabled={running} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/10 text-xl text-fog transition-colors hover:border-white/30 hover:text-white disabled:opacity-30" aria-label="Close">×</button>
            </div>

            {todos.length > 0 && (
              <div className="shrink-0 border-b border-white/10 px-4 py-3 sm:px-5">
                <p className="font-mono-label text-fog/55">Todos — must be completed before the run ends</p>
                <ul className="mt-2 space-y-1.5">
                  {todos.map((todo) => (
                    <li key={todo.id} className="flex min-w-0 items-center gap-2">
                      <span className={`grid h-4 w-4 shrink-0 place-items-center rounded border text-[9px] ${todo.completed ? "border-lime/50 bg-lime/20 text-lime" : "border-white/25 text-transparent"}`}>✓</span>
                      <span className={`min-w-0 truncate text-[11px] ${todo.completed ? "text-fog/45 line-through" : "text-white/85"}`}>{todo.task}</span>
                      {(todo.messages?.length ?? 0) > 0 && <span className="shrink-0 font-mono text-[9px] text-cyan" title="subagent message thread active">📨{todo.messages?.length}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div ref={scrollRef} className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3 sm:px-5">
              {feed.length === 0 && <p className="copy-safe font-mono text-[10px] leading-5 text-fog/40">The team reports here. Tool calls, todos and decisions appear under each step — no input needed from you except Allow / Deny.</p>}
              {feed.map((item) => {
                const meta = kindMeta[item.kind];
                return (
                  <div key={item.id} className={`min-w-0 rounded-xl border px-3 py-2.5 ${item.kind === "mismatch" || item.kind === "error" ? "border-coral/30 bg-coral/[0.06]" : item.kind === "loop" ? "border-amber-300/30 bg-amber-300/[0.07]" : item.kind === "complete" ? "border-lime/30 bg-lime/[0.06]" : "border-white/10 bg-white/[0.02]"}`}>
                    <div className="flex items-center gap-2">
                      <span className={`shrink-0 font-mono text-[9px] tracking-wide ${meta.color}`}>{meta.label}</span>
                      <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-white/85">{item.text}</span>
                    </div>
                    {item.detail && <p className="copy-safe mt-1 break-words whitespace-pre-wrap text-[11px] leading-5 text-fog/65">{item.detail}</p>}
                  </div>
                );
              })}
              {summary && (
                <div className="min-w-0 rounded-xl border border-lime/30 bg-lime/[0.06] px-3 py-3">
                  <p className="font-mono-label text-lime">Final report</p>
                  <p className="copy-safe mt-1 break-words whitespace-pre-wrap text-[12px] leading-5 text-white/90">{summary}</p>
                </div>
              )}
            </div>

            {pendingTool && (
              <div className="shrink-0 border-t border-coral/30 bg-coral/[0.08] px-4 py-3 sm:px-5">
                <p className="font-mono-label text-coral">⚠️ Permission required: {pendingTool.tool}</p>
                <p className="copy-safe mt-1 max-h-16 overflow-y-auto break-words font-mono text-[10px] leading-4 text-fog/75">{JSON.stringify(pendingTool.arguments).slice(0, 300)}</p>
                <div className="mt-2 flex gap-2">
                  <button type="button" onClick={() => onDecision(true)} disabled={decisionBusy} className="flex-1 rounded-lg bg-lime px-3 py-2.5 text-xs font-semibold text-ink disabled:opacity-40">Allow</button>
                  <button type="button" onClick={() => onDecision(false)} disabled={decisionBusy} className="flex-1 rounded-lg border border-coral/40 px-3 py-2.5 text-xs font-semibold text-coral transition-colors hover:bg-coral/[0.1] disabled:opacity-40">Deny</button>
                </div>
              </div>
            )}

            <p className="shrink-0 border-t border-white/10 px-4 py-2.5 font-mono text-[9px] text-fog/40 sm:px-5">All paths are jailed to projects/ — escaping is blocked and reported. Nothing outside is writable.</p>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
