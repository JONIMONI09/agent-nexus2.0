"use client";

import { useState } from "react";

import type { ProviderDetection, ProviderKind, ProviderProfile } from "./types";

type ProviderManagerProps = {
  providers: ProviderProfile[];
  loading: boolean;
  error: string;
  providerModels: Record<string, string[]>;
  providerModelsLoading: Record<string, boolean>;
  onRefresh: () => void;
  onRefreshModels: (providerId: string) => void;
  onSaved: () => void;
  onDeleted: () => void;
};

type ProviderForm = {
  id: string;
  name: string;
  description: string;
  kind: Exclude<ProviderKind, "ollama"> | "ollama";
  baseUrl: string;
  authEnvVar: string;
  modelsPath: string;
  chatPath: string;
  defaultModel: string;
  script: string;
  allowedHosts: string;
};

const emptyForm: ProviderForm = {
  id: "",
  name: "",
  description: "",
  kind: "openai_compatible",
  baseUrl: "",
  authEnvVar: "",
  modelsPath: "",
  chatPath: "",
  defaultModel: "",
  script: "",
  allowedHosts: "",
};

const kindLabels: Record<ProviderKind, string> = {
  ollama: "Ollama native",
  openai_compatible: "OpenAI compatible",
  custom_script: "Deno adapter",
};

function responseError(payload: { error?: string; detail?: string }) {
  return payload.error ?? payload.detail ?? "The provider operation failed.";
}

export function ProviderManager({
  providers,
  loading,
  error,
  providerModels,
  providerModelsLoading,
  onRefresh,
  onRefreshModels,
  onSaved,
  onDeleted,
}: ProviderManagerProps) {
  const [form, setForm] = useState<ProviderForm>(emptyForm);
  const [formOpen, setFormOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [probeBusy, setProbeBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [detection, setDetection] = useState<ProviderDetection | null>(null);

  const update = <K extends keyof ProviderForm>(key: K, value: ProviderForm[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const openNew = () => {
    setForm(emptyForm);
    setDetection(null);
    setNotice("");
    setFormOpen(true);
  };

  const detect = async () => {
    if (!form.baseUrl.trim()) {
      setNotice("Enter a provider URL before probing it.");
      return;
    }
    setProbeBusy(true);
    setNotice("");
    try {
      const response = await fetch("/api/providers/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: form.baseUrl, auth_env_var: form.authEnvVar }),
      });
      const payload = (await response.json().catch(() => ({}))) as { ok?: boolean; result?: ProviderDetection; error?: string; detail?: string };
      if (!response.ok || !payload.result) throw new Error(responseError(payload));
      const result = payload.result;
      setDetection(result);
      setForm((current) => ({
        ...current,
        name: current.name || result.name_suggestion,
        baseUrl: result.normalized_base_url,
        kind: result.kind === "unknown" ? current.kind : result.kind,
        defaultModel: current.defaultModel || result.models[0] || "",
      }));
      setNotice(result.message);
    } catch (operationError) {
      setDetection(null);
      setNotice(operationError instanceof Error ? operationError.message : "The provider URL could not be checked.");
    } finally {
      setProbeBusy(false);
    }
  };

  const save = async () => {
    if (!form.name.trim()) {
      setNotice("Give the provider a name first.");
      return;
    }
    if (form.kind !== "custom_script" && !form.baseUrl.trim()) {
      setNotice("A native or OpenAI-compatible provider needs a base URL.");
      return;
    }
    if (form.kind === "custom_script" && !form.script.trim()) {
      setNotice("A Deno adapter needs source code before it can be saved.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch("/api/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: form.id.trim() || undefined,
          name: form.name,
          description: form.description,
          kind: form.kind,
          base_url: form.baseUrl,
          auth_env_var: form.authEnvVar,
          models_path: form.modelsPath,
          chat_path: form.chatPath,
          default_model: form.defaultModel,
          script: form.script,
          allowed_hosts: form.allowedHosts.split(",").map((host) => host.trim()).filter(Boolean),
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as { ok?: boolean; error?: string; detail?: string };
      if (!response.ok) throw new Error(responseError(payload));
      setNotice("Provider profile saved. Credential values remain outside the app.");
      setFormOpen(false);
      onSaved();
    } catch (operationError) {
      setNotice(operationError instanceof Error ? operationError.message : "The provider profile could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (provider: ProviderProfile) => {
    if (provider.builtin || !window.confirm(`Delete ${provider.name}?`)) return;
    setBusy(true);
    setNotice("");
    try {
      const response = await fetch(`/api/providers/${encodeURIComponent(provider.id)}`, { method: "DELETE" });
      const payload = (await response.json().catch(() => ({}))) as { error?: string; detail?: string };
      if (!response.ok) throw new Error(responseError(payload));
      onDeleted();
    } catch (operationError) {
      setNotice(operationError instanceof Error ? operationError.message : "The provider profile could not be deleted.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono-label text-fog/65">Provider registry</p>
          <p className="mt-1 text-xs leading-5 text-fog/70">Choose Ollama, a cloud API, any compatible URL, or your own adapter.</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button type="button" onClick={onRefresh} disabled={loading} className="rounded-lg border border-cyan/20 px-2.5 py-2 font-mono text-[10px] text-cyan transition-colors hover:border-cyan/50 hover:bg-cyan/[0.08] disabled:opacity-50">{loading ? "Checking" : "Refresh"}</button>
          <button type="button" onClick={openNew} className="rounded-lg bg-lime px-2.5 py-2 font-mono text-[10px] font-semibold text-ink transition-transform hover:scale-[1.02]">+ Add</button>
        </div>
      </div>

      {error && <p className="copy-safe rounded-lg border border-coral/20 bg-coral/[0.06] p-3 text-xs leading-5 text-coral/90">{error}</p>}
      {notice && <p className="copy-safe rounded-lg border border-cyan/15 bg-cyan/[0.05] p-3 text-xs leading-5 text-cyan/90">{notice}</p>}

      <div className="space-y-2">
        {providers.map((provider) => {
          const modelNames = providerModels[provider.id] ?? [];
          const modelBusy = providerModelsLoading[provider.id] ?? false;
          return (
            <div key={provider.id} className="min-w-0 rounded-xl border border-white/10 bg-white/[0.025] p-3">
              <div className="flex min-w-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium text-white">{provider.name}</p>
                    <span className="shrink-0 rounded-full border border-white/10 px-2 py-0.5 font-mono text-[9px] text-fog/65">{kindLabels[provider.kind]}</span>
                    {provider.builtin && <span className="shrink-0 rounded-full border border-lime/20 px-2 py-0.5 font-mono text-[9px] text-lime/80">built in</span>}
                  </div>
                  <p className="copy-safe mt-1 text-[11px] leading-4 text-fog/55">{provider.base_url || "adapter runtime"}</p>
                  {provider.auth_env_var && <p className="mt-1 font-mono text-[10px] text-cyan/70">key ref: {provider.auth_env_var}</p>}
                </div>
                {!provider.builtin && <button type="button" onClick={() => void remove(provider)} disabled={busy} className="shrink-0 px-1 text-lg text-fog/50 transition-colors hover:text-coral disabled:opacity-40" aria-label={`Delete ${provider.name}`}>×</button>}
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <div className="flex min-w-0 flex-wrap gap-1.5">
                  {Object.entries(provider.capabilities).filter(([, enabled]) => enabled).slice(0, 4).map(([capability]) => <span key={capability} className="max-w-full rounded-md bg-cyan/[0.06] px-2 py-1 font-mono text-[9px] text-cyan/70">{capability.replaceAll("_", " ")}</span>)}
                  {modelNames.length > 0 && <span className="rounded-md bg-lime/[0.06] px-2 py-1 font-mono text-[9px] text-lime/80">{modelNames.length} models</span>}
                </div>
                {provider.kind !== "custom_script" && <button type="button" onClick={() => onRefreshModels(provider.id)} disabled={modelBusy} className="shrink-0 rounded-md border border-white/10 px-2 py-1.5 font-mono text-[9px] text-fog/70 transition-colors hover:border-cyan/30 hover:text-cyan disabled:opacity-50">{modelBusy ? "Loading" : "Models"}</button>}
              </div>
              {modelNames.length > 0 && <p className="copy-safe mt-2 text-[10px] leading-4 text-fog/50">{modelNames.slice(0, 3).join(" · ")}{modelNames.length > 3 ? " · …" : ""}</p>}
            </div>
          );
        })}
        {!loading && providers.length === 0 && <p className="rounded-xl border border-white/10 p-3 text-xs leading-5 text-fog/60">The provider registry is unavailable.</p>}
      </div>

      {formOpen && (
        <div className="space-y-4 rounded-xl border border-lime/20 bg-lime/[0.035] p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-mono-label text-lime">New provider profile</p>
              <p className="mt-1 text-xs leading-5 text-fog/70">Save a protocol, not a secret. Put the key value in Environment settings.</p>
            </div>
            <button type="button" onClick={() => setFormOpen(false)} className="text-lg text-fog/55 hover:text-white" aria-label="Close provider form">×</button>
          </div>

          <label className="block"><span className="font-mono-label text-fog/60">Name</span><input value={form.name} onChange={(event) => update("name", event.target.value)} maxLength={120} placeholder="My inference gateway" className="mt-2 h-10 w-full min-w-0 rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-white outline-none focus:border-lime/50" /></label>
          <label className="block"><span className="font-mono-label text-fog/60">Type</span><select value={form.kind} onChange={(event) => update("kind", event.target.value as ProviderForm["kind"])} className="mt-2 h-10 w-full min-w-0 rounded-lg border border-white/10 bg-[#101722] px-3 text-sm text-white outline-none focus:border-lime/50"><option value="openai_compatible">OpenAI-compatible URL</option><option value="ollama">Ollama native URL</option><option value="custom_script">Deno TypeScript adapter</option></select></label>
          <label className="block"><span className="font-mono-label text-fog/60">Provider URL</span><div className="mt-2 flex min-w-0 gap-2"><input value={form.baseUrl} onChange={(event) => update("baseUrl", event.target.value)} maxLength={2000} placeholder={form.kind === "custom_script" ? "Optional base URL" : "https://api.example.com/v1"} className="h-10 min-w-0 flex-1 rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-white outline-none focus:border-lime/50" /><button type="button" onClick={() => void detect()} disabled={probeBusy || form.kind === "custom_script"} className="shrink-0 rounded-lg border border-cyan/25 px-2.5 text-[10px] font-semibold text-cyan transition-colors hover:bg-cyan/[0.08] disabled:opacity-40">{probeBusy ? "Probe" : "Detect"}</button></div></label>
          <label className="block"><span className="font-mono-label text-fog/60">Credential environment name</span><input value={form.authEnvVar} onChange={(event) => update("authEnvVar", event.target.value.toUpperCase())} maxLength={128} placeholder="OPENAI_API_KEY (name only)" className="mt-2 h-10 w-full min-w-0 rounded-lg border border-white/10 bg-black/20 px-3 font-mono text-xs text-white outline-none focus:border-lime/50" /><span className="mt-1 block text-[10px] leading-4 text-fog/50">The secret value is never sent to this browser form.</span></label>

          {form.kind !== "custom_script" ? (
            <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block min-w-0"><span className="font-mono-label text-fog/60">Models path</span><input value={form.modelsPath} onChange={(event) => update("modelsPath", event.target.value)} maxLength={300} placeholder={form.kind === "ollama" ? "/api/tags" : "/models"} className="mt-2 h-10 w-full min-w-0 rounded-lg border border-white/10 bg-black/20 px-3 font-mono text-[11px] text-white outline-none focus:border-lime/50" /></label>
              <label className="block min-w-0"><span className="font-mono-label text-fog/60">Chat path</span><input value={form.chatPath} onChange={(event) => update("chatPath", event.target.value)} maxLength={300} placeholder={form.kind === "ollama" ? "/api/chat" : "/chat/completions"} className="mt-2 h-10 w-full min-w-0 rounded-lg border border-white/10 bg-black/20 px-3 font-mono text-[11px] text-white outline-none focus:border-lime/50" /></label>
            </div>
          ) : (
            <>
              <label className="block"><span className="font-mono-label text-fog/60">Network allowlist</span><input value={form.allowedHosts} onChange={(event) => update("allowedHosts", event.target.value)} maxLength={2000} placeholder="api.example.com, localhost:11434" className="mt-2 h-10 w-full min-w-0 rounded-lg border border-white/10 bg-black/20 px-3 font-mono text-[11px] text-white outline-none focus:border-lime/50" /><span className="mt-1 block text-[10px] leading-4 text-fog/50">Comma-separated hosts. Deno receives no ambient environment permissions.</span></label>
              <label className="block"><span className="font-mono-label text-fog/60">Adapter source</span><textarea value={form.script} onChange={(event) => update("script", event.target.value)} maxLength={60000} rows={9} spellCheck={false} placeholder={'const input = JSON.parse(await new Response(Deno.stdin.readable).text());\n// Print one JSON object: { "content": "..." }\nconsole.log(JSON.stringify({ content: "response" }));'} className="copy-safe mt-2 w-full resize-y rounded-lg border border-white/10 bg-black/30 p-3 font-mono text-[11px] leading-5 text-cyan/90 outline-none focus:border-lime/50" /><span className="mt-1 block text-[10px] leading-4 text-fog/50">Runs only when Deno is installed, with `--no-remote`, an explicit network allowlist, and an execution timeout.</span></label>
            </>
          )}
          {detection && <div className={`copy-safe rounded-lg border p-3 text-xs leading-5 ${detection.detected ? "border-lime/20 bg-lime/[0.05] text-lime/90" : "border-coral/20 bg-coral/[0.05] text-coral/90"}`}><strong>{detection.detected ? "Detected" : "Not detected"}: </strong>{detection.message}{detection.models.length > 0 && <span className="block mt-1 text-fog/70">Models: {detection.models.slice(0, 5).join(", ")}</span>}</div>}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><button type="button" onClick={() => setForm(emptyForm)} className="min-h-10 rounded-lg border border-white/10 px-3 text-xs text-fog transition-colors hover:text-white">Reset</button><button type="button" onClick={() => void save()} disabled={busy} className="min-h-10 rounded-lg bg-lime px-3 text-xs font-semibold text-ink transition-transform hover:scale-[1.01] disabled:opacity-50">{busy ? "Saving..." : "Save provider"}</button></div>
        </div>
      )}
    </section>
  );
}
