"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { AgentStatus } from "./AgentStatus";
import { ModelSelector } from "./ModelSelector";
import { ProviderManager } from "./ProviderManager";
import { LearningPanel } from "./LearningPanel";
import type { ThinkingStyle } from "./types";
import { BrowserLocalProvider, BROWSER_PROVIDER_ID, type BrowserLoadState } from "./BrowserLocalProvider";
import type { AgentState, ProviderProfile } from "./types";
import type { MLCEngine } from "@mlc-ai/web-llm";

type SettingsDrawerProps = {
  open: boolean;
  onClose: () => void;
  scoutProviderId: string;
  synthesizerProviderId: string;
  fallbackProviderId: string;
  scoutModel: string;
  synthesizerModel: string;
  fallbackModel: string;
  systemPrompt: string;
  providers: ProviderProfile[];
  providersLoading: boolean;
  providersError: string;
  providerModels: Record<string, string[]>;
  providerModelsLoading: Record<string, boolean>;
  scoutState: AgentState;
  synthesizerState: AgentState;
  analystState?: AgentState;
  agentCount?: number;
  onScoutProviderChange: (value: string) => void;
  onSynthesizerProviderChange: (value: string) => void;
  onFallbackProviderChange: (value: string) => void;
  onScoutModelChange: (value: string) => void;
  onSynthesizerModelChange: (value: string) => void;
  onFallbackModelChange: (value: string) => void;
  onSystemPromptChange: (value: string) => void;
  onRefreshProviders: () => void;
  onRefreshProviderModels: (providerId: string) => void;
  onOpenSubAgents: () => void;
  browserModel: string;
  browserReady: boolean;
  onBrowserModelChange: (value: string) => void;
  onBrowserReadyChange: (ready: boolean) => void;
  onBrowserEngineChange: (engine: MLCEngine | null) => void;
  learningEnabled: boolean;
  onLearningEnabledChange: (enabled: boolean) => void;
  thinkingStyle: ThinkingStyle;
  onThinkingStyleChange: (style: ThinkingStyle) => void;
  autoTranslate: boolean;
  onAutoTranslateChange: (enabled: boolean) => void;
  onBrowserLoadStateChange: (state: BrowserLoadState | null) => void;
  onRegisterLoadStop: (stop: () => void) => void;
};

function FsSandboxSection() {
  const [sandbox, setSandbox] = useState<string>("jailed");
  const [dockerAvailable, setDockerAvailable] = useState(false);
  const [projectsRoot, setProjectsRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch("/api/fs", { cache: "no-store" });
        const payload = (await response.json().catch(() => ({}))) as { sandbox?: string; docker_available?: boolean; projects_root?: string };
        if (cancelled) return;
        setSandbox(payload.sandbox ?? "jailed");
        setDockerAvailable(Boolean(payload.docker_available));
        setProjectsRoot(payload.projects_root ?? "");
      } catch {
        if (!cancelled) setError("Sandbox settings could not be loaded.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const choose = async (value: string) => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/fs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sandbox: value, auto_create_projects: true }),
      });
      const payload = (await response.json().catch(() => ({}))) as { error?: string; detail?: string; sandbox?: string; docker_available?: boolean };
      if (!response.ok) throw new Error(payload.error ?? payload.detail ?? "Could not change the sandbox.");
      setSandbox(payload.sandbox ?? value);
      setDockerAvailable(Boolean(payload.docker_available));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not change the sandbox.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-3 rounded-xl border border-lime/15 bg-lime/[0.03] p-4">
      <div>
        <p className="font-mono-label text-lime">Filesystem agent sandbox</p>
        <p className="mt-1 text-xs leading-5 text-fog/70">All file operations are jailed to <span className="font-mono text-[10px] text-white/80">projects/</span> — escaping is impossible and reported.{projectsRoot ? ` Root: ${projectsRoot}` : ""}</p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button type="button" onClick={() => void choose("jailed")} disabled={busy} className={`min-w-0 rounded-xl border px-3 py-2.5 text-left transition-colors ${sandbox === "jailed" ? "border-lime/50 bg-lime/[0.08]" : "border-white/10 bg-white/[0.025] hover:border-white/25"}`} aria-pressed={sandbox === "jailed"}>
          <span className={`block truncate text-xs font-medium ${sandbox === "jailed" ? "text-lime" : "text-white"}`}>Hardened path jail</span>
          <span className="mt-0.5 block text-[10px] leading-4 text-fog/55">Default. Normalized paths + symlink checks.</span>
        </button>
        <button type="button" onClick={() => void choose("docker")} disabled={busy || !dockerAvailable} title={dockerAvailable ? "Runs tools in an OWASP-hardened container" : "Docker is not available here; the path jail stays active."} className={`min-w-0 rounded-xl border px-3 py-2.5 text-left transition-colors disabled:opacity-40 ${sandbox === "docker" ? "border-cyan/50 bg-cyan/[0.08]" : "border-white/10 bg-white/[0.025] hover:border-white/25"}`} aria-pressed={sandbox === "docker"}>
          <span className={`block truncate text-xs font-medium ${sandbox === "docker" ? "text-cyan" : "text-white"}`}>Docker {dockerAvailable ? "" : "· n/a"}</span>
          <span className="mt-0.5 block text-[10px] leading-4 text-fog/55">--cap-drop ALL, no-new-privileges, read-only, no network.</span>
        </button>
      </div>
      {error && <p className="copy-safe break-words text-[11px] text-coral">{error}</p>}
    </section>
  );
}

type AgentRouteProps = {
  label: string;
  providerId: string;
  model: string;
  providers: ProviderProfile[];
  providerModels: Record<string, string[]>;
  providerModelsLoading: Record<string, boolean>;
  onProviderChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onRefreshModels: (providerId: string) => void;
  browserReady: boolean;
  browserModel: string;
};

function AgentRoute({
  label,
  providerId,
  model,
  providers,
  providerModels,
  providerModelsLoading,
  onProviderChange,
  onModelChange,
  onRefreshModels,
  browserReady,
  browserModel,
}: AgentRouteProps) {
  const provider = providers.find((item) => item.id === providerId);
  const isBrowser = providerId === BROWSER_PROVIDER_ID;
  const routeModels = isBrowser ? [browserModel] : (providerModels[providerId] ?? []);
  const discoveredModels = routeModels;
  const modelsLoading = providerModelsLoading[providerId] ?? false;
  const providerOptions = Array.from(new Set([BROWSER_PROVIDER_ID, providerId, ...providers.map((item) => item.id)].filter(Boolean)));

  return (
    <div className="min-w-0 rounded-xl border border-white/10 bg-white/[0.025] p-3">
      <p className="font-mono-label text-fog/65">{label}</p>
      <select
        value={providerId}
        onChange={(event) => onProviderChange(event.target.value)}
        className="mt-2 h-10 w-full min-w-0 rounded-lg border border-white/10 bg-[#101722] px-3 text-xs text-white outline-none focus:border-lime/50"
      >
        {providerOptions.length === 0 && <option value="">No providers detected</option>}
        {providerOptions.map((id) => {
          const option = providers.find((item) => item.id === id);
          return <option key={id} value={id}>{id === BROWSER_PROVIDER_ID ? "Browser local · WebLLM" : option?.name ?? id}</option>;
        })}
      </select>        {isBrowser ? <p className="copy-safe mt-1 truncate text-[10px] text-fog/50">WebLLM · {browserReady ? "initialized in this browser" : "initialize browser runtime first"}</p> : provider && <p className="copy-safe mt-1 truncate text-[10px] text-fog/50">{provider.kind} · {provider.base_url || "adapter runtime"}</p>}
      {isBrowser && /fallback/i.test(label) && <p className="copy-safe mt-1 break-words text-[10px] leading-4 text-amber-200/90">⚠️ The browser provider runs only in this tab and can never act as a server-side fallback. When a server run needs the fallback route, the first configured server provider is used instead.</p>}
      <div className="mt-3 flex min-w-0 items-end gap-2">
        <div className="min-w-0 flex-1"><ModelSelector label={`${label} model`} value={model} models={discoveredModels} loading={modelsLoading} onChange={onModelChange} /></div>
        {!isBrowser && provider?.kind !== "custom_script" && <button type="button" onClick={() => onRefreshModels(providerId)} disabled={modelsLoading || !providerId} className="mb-5 shrink-0 rounded-lg border border-cyan/20 px-2 py-2 font-mono text-[9px] text-cyan transition-colors hover:bg-cyan/[0.08] disabled:opacity-40">{modelsLoading ? "..." : "Discover"}</button>}
      </div>
    </div>
  );
}

export function SettingsDrawer({
  open,
  onClose,
  scoutProviderId,
  synthesizerProviderId,
  fallbackProviderId,
  scoutModel,
  synthesizerModel,
  fallbackModel,
  systemPrompt,
  providers,
  providersLoading,
  providersError,
  providerModels,
  providerModelsLoading,
  scoutState,
  synthesizerState,
  analystState,
  agentCount = 1,
  onScoutProviderChange,
  onSynthesizerProviderChange,
  onFallbackProviderChange,
  onScoutModelChange,
  onSynthesizerModelChange,
  onFallbackModelChange,
  onSystemPromptChange,
  onRefreshProviders,
  onRefreshProviderModels,
  onOpenSubAgents,
  browserModel,
  browserReady,
  onBrowserModelChange,
  onBrowserReadyChange,
  onBrowserEngineChange,
  learningEnabled,
  onLearningEnabledChange,
  thinkingStyle,
  onThinkingStyleChange,
  autoTranslate,
  onAutoTranslateChange,
  onBrowserLoadStateChange,
  onRegisterLoadStop,
}: SettingsDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open) drawerRef.current?.focus();
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button type="button" aria-label="Close settings" className="fixed inset-0 z-30 cursor-default bg-ink/70 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside
            ref={drawerRef}
            tabIndex={-1}
            aria-label="Workspace settings"
            className="fixed inset-y-0 left-0 z-40 flex w-[min(96vw,460px)] flex-col border-r border-white/10 bg-[#0d131d]/95 shadow-[20px_0_80px_rgba(0,0,0,0.4)] backdrop-blur-2xl outline-none"
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            onPointerDown={(event) => {
              if (event.pointerType !== "touch") return;
              const startX = event.clientX;
              const handlePointerUp = (upEvent: PointerEvent) => {
                if (startX - upEvent.clientX > 90) onClose();
                window.removeEventListener("pointerup", handlePointerUp);
              };
              window.addEventListener("pointerup", handlePointerUp, { once: true });
            }}
          >
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-5">
              <div className="min-w-0"><p className="font-mono-label text-lime">Control room</p><h2 className="mt-1 text-lg font-semibold text-white">Providers & routing</h2></div>
              <button type="button" onClick={onClose} className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/10 text-xl text-fog transition-colors hover:border-white/30 hover:text-white" aria-label="Close settings">×</button>
            </div>
            <div className="flex-1 space-y-7 overflow-y-auto px-5 py-6">
              <BrowserLocalProvider onModelChange={onBrowserModelChange} onReadyChange={onBrowserReadyChange} onEngineChange={onBrowserEngineChange} onLoadStateChange={onBrowserLoadStateChange} onRegisterLoadStop={onRegisterLoadStop} />

              <ProviderManager providers={providers} loading={providersLoading} error={providersError} providerModels={providerModels} providerModelsLoading={providerModelsLoading} onRefresh={onRefreshProviders} onRefreshModels={onRefreshProviderModels} onSaved={onRefreshProviders} onDeleted={onRefreshProviders} />

              <section className="space-y-3">
                <div><p className="font-mono-label text-fog/65">Agent routing</p><p className="mt-1 text-xs leading-5 text-fog/70">Each role can use a different local or hosted provider. Model ids may also be entered manually.</p></div>
                <AgentRoute label="Scout / Agent A" providerId={scoutProviderId} model={scoutModel} providers={providers} providerModels={providerModels} providerModelsLoading={providerModelsLoading} onProviderChange={onScoutProviderChange} onModelChange={onScoutModelChange} onRefreshModels={onRefreshProviderModels} browserReady={browserReady} browserModel={browserModel} />
                <AgentRoute label="Synthesizer / Agent B" providerId={synthesizerProviderId} model={synthesizerModel} providers={providers} providerModels={providerModels} providerModelsLoading={providerModelsLoading} onProviderChange={onSynthesizerProviderChange} onModelChange={onSynthesizerModelChange} onRefreshModels={onRefreshProviderModels} browserReady={browserReady} browserModel={browserModel} />
                <AgentRoute label="Fallback route" providerId={fallbackProviderId} model={fallbackModel} providers={providers} providerModels={providerModels} providerModelsLoading={providerModelsLoading} onProviderChange={onFallbackProviderChange} onModelChange={onFallbackModelChange} onRefreshModels={onRefreshProviderModels} browserReady={browserReady} browserModel={browserModel} />
              </section>

              <section>
                <label className="block"><span className="font-mono-label text-fog/65">Workspace instruction</span><textarea value={systemPrompt} onChange={(event) => onSystemPromptChange(event.target.value)} maxLength={6000} rows={5} placeholder="Optional instruction applied to both agents..." className="mt-2 w-full resize-y rounded-xl border border-white/10 bg-black/20 p-3 text-sm leading-6 text-white placeholder:text-fog/35 outline-none transition-colors focus:border-lime/50" /><span className="mt-1 block text-right text-[11px] text-fog/45">{systemPrompt.length}/6000</span></label>
              </section>

              <LearningPanel enabled={learningEnabled} onEnabledChange={(value) => { onLearningEnabledChange(value); }} thinkingStyle={thinkingStyle} onThinkingStyleChange={onThinkingStyleChange} />

              <section className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.025] p-3">
                <div className="min-w-0">
                  <p className="font-mono-label text-fog/65">Auto-translate input</p>
                  <p className="mt-1 text-[11px] leading-4 text-fog/55">Non-English messages are translated to English with your local model (free, no API key) so smaller models follow them better. Answers stay in your language.</p>
                </div>
                <button type="button" onClick={() => onAutoTranslateChange(!autoTranslate)} aria-pressed={autoTranslate} className={`shrink-0 rounded-full border px-3 py-1.5 font-mono text-[10px] transition-colors ${autoTranslate ? "border-lime/40 bg-lime/10 text-lime" : "border-white/15 bg-white/[0.04] text-fog/60"}`}>{autoTranslate ? "On" : "Off"}</button>
              </section>

              <section>
                <div className="mb-4 flex items-center justify-between"><div><p className="font-mono-label text-fog/65">Agent pulse</p><p className="mt-1 text-xs text-fog/60">Live state for the active run.</p></div><span className="h-2 w-2 animate-pulse rounded-full bg-lime" /></div>
                <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.025] p-4">
                  <AgentStatus agent="scout" state={scoutState} onClick={onOpenSubAgents} />
                  {agentCount >= 3 && analystState && <AgentStatus agent="analyst" state={analystState} onClick={onOpenSubAgents} />}
                  <AgentStatus agent="synthesizer" state={synthesizerState} onClick={onOpenSubAgents} />
                  <button type="button" onClick={onOpenSubAgents} className="w-full rounded-lg border border-cyan/25 bg-cyan/[0.06] px-3 py-2.5 font-mono text-[10px] text-cyan transition-colors hover:bg-cyan/[0.12]">OPEN ACTIVITY INSPECTOR ↗</button>
                </div>
              </section>

              <FsSandboxSection />

              <section className="rounded-xl border border-cyan/15 bg-cyan/[0.04] p-4"><p className="font-mono-label text-cyan">Privacy boundary</p><p className="mt-2 text-xs leading-5 text-fog/75">Provider secrets are referenced by environment-variable name only. The backend keeps values off the browser and logs. Web search still pauses for explicit approval.</p></section>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
