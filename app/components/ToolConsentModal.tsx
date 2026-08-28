"use client";

import { AnimatePresence, motion } from "framer-motion";

import { CopyButton } from "./CopyButton";
import type { ToolRequest } from "./types";

type ToolConsentModalProps = {
  request: ToolRequest | null;
  busy: boolean;
  onDecision: (approved: boolean) => void;
};

export function ToolConsentModal({ request, busy, onDecision }: ToolConsentModalProps) {
  return (
    <AnimatePresence>
      {request && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-ink/80 p-3 backdrop-blur-md sm:items-center sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="tool-consent-title"
        >
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16 }}
            className="w-full max-w-lg overflow-hidden rounded-2xl border border-coral/40 bg-[#15131a] shadow-[0_28px_90px_rgba(0,0,0,0.55)]"
          >
            <div className="flex items-start gap-3 border-b border-coral/15 bg-coral/[0.08] p-5">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-coral/30 bg-coral/10 text-lg text-coral" aria-hidden="true">!</div>
              <div className="min-w-0">
                <p className="font-mono-label text-coral">Manual approval required</p>
                <h2 id="tool-consent-title" className="mt-1 text-lg font-semibold text-white">The AI wants to use a skill</h2>
              </div>
            </div>
            <div className="space-y-4 p-5">
              <div>
                <p className="font-mono-label text-fog/60">Requested operation</p>
                <p className="mt-1 break-words text-base font-semibold text-white">{request.tool}</p>
              </div>
              <div>
                <div className="flex items-center justify-between gap-2">
                  <p className="font-mono-label text-fog/60">Arguments</p>
                  <CopyButton value={JSON.stringify(request.arguments, null, 2)} label="Copy call" />
                </div>
                <pre className="copy-safe mt-2 max-h-36 overflow-auto rounded-xl border border-white/10 bg-black/20 p-3 font-mono text-xs leading-5 text-cyan/90">{JSON.stringify(request.arguments, null, 2)}</pre>
              </div>
              <p className="text-xs leading-5 text-fog/75">Nothing will run until you decide. Approving sends this query to public web search; denying returns a denial result to the agent, which then answers without live evidence.</p>
              <div className="grid grid-cols-2 gap-3 pt-1">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onDecision(false)}
                  className="min-h-12 rounded-xl border border-white/15 bg-white/[0.04] px-4 text-sm font-semibold text-white transition-colors hover:border-coral/50 hover:bg-coral/10 disabled:cursor-wait disabled:opacity-50"
                >
                  {busy ? "Resolving..." : "Deny"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onDecision(true)}
                  className="min-h-12 rounded-xl bg-lime px-4 text-sm font-semibold text-ink transition-transform hover:scale-[1.01] disabled:cursor-wait disabled:opacity-50"
                >
                  {busy ? "Resolving..." : "Allow once"}
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
