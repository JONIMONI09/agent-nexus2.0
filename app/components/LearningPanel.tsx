"use client";

import { useEffect, useState } from "react";

import type { LearningMemory, ThinkingStyle } from "./types";

type LearningPanelProps = {
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
  thinkingStyle: ThinkingStyle;
  onThinkingStyleChange: (style: ThinkingStyle) => void;
};

const files: { key: keyof LearningMemory; label: string; hint: string }[] = [
  { key: "learn", label: "learn.md", hint: "Journal of insights the AI extracted from your chats." },
  { key: "rules", label: "Rules.md", hint: "Standing rules the AI must obey in every run." },
  { key: "agent", label: "Agent.md", hint: "Persona and behavior profile of the AI." },
];

const thinkingStyles: { value: ThinkingStyle; label: string; description: string }[] = [
  { value: "concise", label: "Concise", description: "Shortest possible answer." },
  { value: "balanced", label: "Balanced", description: "Structured, no filler." },
  { value: "deep", label: "Deep", description: "Edge cases, assumptions, counterarguments." },
  { value: "creative", label: "Creative", description: "Many angles, unconventional options." },
];

export function LearningPanel({ enabled, onEnabledChange, thinkingStyle, onThinkingStyleChange }: LearningPanelProps) {
  const [memory, setMemory] = useState<LearningMemory>({ learn: "", rules: "", agent: "" });
  const [openFile, setOpenFile] = useState<keyof LearningMemory | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch("/api/learning", { cache: "no-store" });
        const payload = (await response.json().catch(() => ({}))) as { enabled?: boolean; files?: LearningMemory };
        if (cancelled) return;
        setMemory({ learn: payload.files?.learn ?? "", rules: payload.files?.rules ?? "", agent: payload.files?.agent ?? "" });
        onEnabledChange(Boolean(payload.enabled));
      } catch {
        if (!cancelled) setLoadError("Memory files could not be loaded.");
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleFile = (key: keyof LearningMemory) => {
    if (openFile === key) {
      setOpenFile(null);
      return;
    }
    setOpenFile(key);
    setDraft(memory[key]);
  };

  const saveFile = async (key: keyof LearningMemory) => {
    setSaving(true);
    try {
      const response = await fetch(`/api/learning/files/${key}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file: key, content: draft }),
      });
      if (!response.ok) throw new Error("Save failed.");
      setMemory((current) => ({ ...current, [key]: draft }));
      setOpenFile(null);
    } catch {
      setLoadError("The memory file could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const resetFile = async (key: keyof LearningMemory) => {
    setSaving(true);
    try {
      const response = await fetch(`/api/learning/files/${key}/reset`, { method: "POST" });
      if (!response.ok) throw new Error("Reset failed.");
      const payload = (await response.json().catch(() => ({}))) as { ok?: boolean };
      if (payload.ok) {
        const fresh = await fetch("/api/learning", { cache: "no-store" });
        const data = (await fresh.json().catch(() => ({}))) as { files?: LearningMemory };
        setMemory({ learn: data.files?.learn ?? "", rules: data.files?.rules ?? "", agent: data.files?.agent ?? "" });
        if (openFile === key) setDraft(data.files?.[key] ?? "");
      }
    } catch {
      setLoadError("The memory file could not be reset.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-4">
      <div>
        <p className="font-mono-label text-fog/65">Learning &amp; memory</p>
        <p className="mt-1 text-xs leading-5 text-fog/70">The AI learns from your feedback over time. Turning this on injects learn.md, Rules.md and Agent.md into every run.</p>
      </div>

      <button
        type="button"
        onClick={() => onEnabledChange(!enabled)}
        role="switch"
        aria-checked={enabled}
        className={`flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-3 transition-colors ${enabled ? "border-lime/40 bg-lime/[0.07]" : "border-white/10 bg-white/[0.025]"}`}
      >
        <span className="min-w-0 text-left">
          <span className="block truncate text-xs font-medium text-white">Learning</span>
          <span className="mt-0.5 block truncate text-[10px] text-fog/55">{enabled ? "On — insights are saved and injected" : "Off — the AI learns nothing"}</span>
        </span>
        <span className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${enabled ? "bg-lime" : "bg-white/15"}`}>
          <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-ink transition-all ${enabled ? "left-[22px]" : "left-0.5 bg-white/70"}`} />
        </span>
      </button>

      <div className="space-y-2">
        {files.map((file) => (
          <div key={file.key} className="min-w-0 rounded-xl border border-white/10 bg-white/[0.025]">
            <button type="button" onClick={() => toggleFile(file.key)} className="flex w-full min-w-0 items-center gap-2 px-3 py-2.5 text-left" aria-expanded={openFile === file.key}>
              <span className="shrink-0 font-mono text-[10px]" aria-hidden="true">{openFile === file.key ? "▾" : "▸"}</span>
              <span className="shrink-0 font-mono-label text-cyan">{file.label}</span>
              <span className="ml-auto min-w-0 truncate text-[10px] text-fog/45">{file.hint}</span>
            </button>
            {openFile === file.key && (
              <div className="border-t border-white/10 px-3 py-3">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={7}
                  maxLength={60000}
                  spellCheck={false}
                  className="w-full resize-y rounded-lg border border-white/10 bg-black/30 p-2.5 font-mono text-[11px] leading-5 text-white/90 outline-none focus:border-lime/50"
                />
                <div className="mt-2 flex items-center gap-2">
                  <button type="button" onClick={() => void saveFile(file.key)} disabled={saving} className="rounded-lg bg-lime px-3 py-1.5 font-mono text-[10px] font-semibold text-ink disabled:opacity-40">Save</button>
                  <button type="button" onClick={() => void resetFile(file.key)} disabled={saving} className="rounded-lg border border-coral/30 px-3 py-1.5 font-mono text-[10px] text-coral transition-colors hover:bg-coral/[0.08] disabled:opacity-40">Reset</button>
                  <span className="ml-auto font-mono text-[9px] text-fog/35">{draft.length}/60000</span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div>
        <p className="font-mono-label text-fog/65">How the AI thinks</p>
        <div className="mt-2 grid grid-cols-2 gap-2">
          {thinkingStyles.map((style) => (
            <button
              key={style.value}
              type="button"
              onClick={() => onThinkingStyleChange(style.value)}
              className={`min-w-0 rounded-xl border px-3 py-2.5 text-left transition-colors ${thinkingStyle === style.value ? "border-cyan/50 bg-cyan/[0.08]" : "border-white/10 bg-white/[0.025] hover:border-white/25"}`}
              aria-pressed={thinkingStyle === style.value}
            >
              <span className={`block truncate text-xs font-medium ${thinkingStyle === style.value ? "text-cyan" : "text-white"}`}>{style.label}</span>
              <span className="mt-0.5 block text-[10px] leading-4 text-fog/55">{style.description}</span>
            </button>
          ))}
        </div>
      </div>

      {loadError && <p className="copy-safe rounded-lg border border-coral/25 bg-coral/[0.07] px-2.5 py-2 text-[11px] text-coral">{loadError}</p>}
    </section>
  );
}
