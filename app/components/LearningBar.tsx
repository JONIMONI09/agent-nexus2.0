"use client";

import { AnimatePresence, motion } from "framer-motion";

import type { LearningUpdate } from "./types";

type LearningBarProps = {
  update: LearningUpdate | null;
  enabled: boolean;
  onOpen: () => void;
};

export function LearningBar({ update, enabled, onOpen }: LearningBarProps) {
  const visible = Boolean(update && (update.added_lessons > 0 || update.added_rules > 0));

  return (
    <div className="mx-auto w-full max-w-3xl px-4 sm:px-6" aria-live="polite">
      <AnimatePresence initial={false}>
        {visible && update && (
          <motion.button
            type="button"
            onClick={onOpen}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            className="mb-2 flex w-full min-w-0 items-center gap-2.5 rounded-xl border border-lime/25 bg-lime/[0.06] px-3 py-2 text-left transition-colors hover:bg-lime/[0.1]"
          >
            <span className="shrink-0 text-sm" aria-hidden="true">📚</span>
            <span className="min-w-0 truncate text-[11px] leading-5 text-lime">
              Learned {update.added_lessons} new insight{update.added_lessons === 1 ? "" : "s"}
              {update.added_rules > 0 ? ` + ${update.added_rules} standing rule${update.added_rules === 1 ? "" : "s"}` : ""} — stored in learn.md / Rules.md
            </span>
            <span className="ml-auto shrink-0 font-mono text-[9px] text-lime/70">VIEW ›</span>
          </motion.button>
        )}
        {!visible && enabled && (
          <motion.div
            key="learning-idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mb-2 flex items-center gap-2 px-3 py-1"
          >
            <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-lime/60" />
            <span className="truncate font-mono text-[9px] text-fog/40">Learning on — the AI saves insights to learn.md and obeys Rules.md</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
