"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MLCEngine } from "@mlc-ai/web-llm";

export type BrowserLoadState = {
  loading: boolean;
  progress: number;
  label: string;
  model: string;
  done: boolean;
};

type BrowserLocalProviderProps = {
  onReadyChange?: (ready: boolean) => void;
  onModelChange?: (model: string) => void;
  onEngineChange?: (engine: MLCEngine | null) => void;
  /** Streams model-load progress to the app shell so loading stays visible when this settings panel is closed. */
  onLoadStateChange?: (state: BrowserLoadState | null) => void;
  /** Registers a stop function so the app-shell stop button can cancel an in-flight model load. */
  onRegisterLoadStop?: (stop: () => void) => void;
};

type BrowserStatus = "idle" | "loading" | "ready" | "error";

export const BROWSER_PROVIDER_ID = "browser-webllm";
export const DEFAULT_BROWSER_MODEL = "SmolLM2-360M-Instruct-q4f16_1-MLC";

/**
 * Model slots with two quantizations per slot.
 * q4f16_1 needs the WebGPU "shader-f16" feature — many Qualcomm (Adreno) adapters
 * do not expose it on Vulkan (gpuweb#5006). q4f32_1 runs everywhere WebGPU works.
 * All IDs verified against @mlc-ai/web-llm 0.2.84 prebuiltAppConfig (165 models).
 */
const browserModels = [
  { label: "SmolLM2 · 360M", tier: "Android / low memory", size: "~380 MB", f16: "SmolLM2-360M-Instruct-q4f16_1-MLC", f32: "SmolLM2-360M-Instruct-q4f32_1-MLC" },
  { label: "Qwen 2.5 · 0.5B", tier: "Android / standard", size: "~950 MB", f16: "Qwen2.5-0.5B-Instruct-q4f16_1-MLC", f32: "Llama-3.2-1B-Instruct-q4f32_1-MLC" },
  { label: "Qwen 2.5 · 1.5B", tier: "Desktop / standard", size: "~1.6 GB", f16: "Qwen2.5-1.5B-Instruct-q4f16_1-MLC", f32: "SmolLM2-1.7B-Instruct-q4f32_1-MLC" },
  { label: "Llama 3.2 · 3B", tier: "Desktop / capable GPU", size: "~2.3 GB", f16: "Llama-3.2-3B-Instruct-q4f16_1-MLC", f32: "Llama-3.2-3B-Instruct-q4f32_1-MLC" },
] as const;

/* --- Minimal structural WebGPU types (independent of lib.dom version) --- */
type AdapterInfo = { vendor?: string; architecture?: string; device?: string; description?: string };
type MiniGPUAdapter = {
  features?: Set<string> | string[];
  info?: AdapterInfo;
  requestAdapterInfo?: () => Promise<AdapterInfo>;
};
type MiniGPU = { requestAdapter: (options?: { powerPreference?: string }) => Promise<MiniGPUAdapter | null> };

type GpuProbe = {
  available: boolean;
  adapterLabel: string;
  shaderF16: boolean;
  chromeVersion: string | null;
  isAndroid: boolean;
  reason: "no-navigator-gpu" | "adapter-null" | "adapter-timeout" | null;
};

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([
    promise,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), ms)),
  ]);
}

function deviceFacts(): { chromeVersion: string | null; isAndroid: boolean } {
  if (typeof navigator === "undefined") return { chromeVersion: null, isAndroid: false };
  const match = navigator.userAgent.match(/Chrom(?:e|ium)\/(\d+)/);
  return { chromeVersion: match ? match[1] : null, isAndroid: /Android/i.test(navigator.userAgent) };
}

function featuresHas(adapter: MiniGPUAdapter, feature: string): boolean {
  const set = adapter.features;
  if (!set) return false;
  if (typeof (set as Set<string>).has === "function") return (set as Set<string>).has(feature);
  return Array.isArray(set) ? set.includes(feature) : false;
}

async function readAdapterLabel(adapter: MiniGPUAdapter): Promise<string> {
  try {
    const info = adapter.info;
    if (info) {
      const parts = [info.vendor, info.architecture, info.device || info.description].filter(Boolean);
      if (parts.length > 0) return parts.join(" · ");
    }
    if (typeof adapter.requestAdapterInfo === "function") {
      const info = await adapter.requestAdapterInfo();
      const parts = [info.vendor, info.architecture, info.device || info.description].filter(Boolean);
      if (parts.length > 0) return parts.join(" · ");
    }
  } catch {
    // Adapter info is optional diagnostics — never fail the probe over it.
  }
  return "";
}

async function probeWebGPU(): Promise<GpuProbe> {
  const { chromeVersion, isAndroid } = deviceFacts();
  const base = { adapterLabel: "", shaderF16: false, chromeVersion, isAndroid };
  if (typeof navigator === "undefined" || !("gpu" in navigator)) {
    return { ...base, available: false, reason: "no-navigator-gpu" };
  }
  const gpu = (navigator as Navigator & { gpu: MiniGPU }).gpu;
  // Android Chrome can hang for seconds on the first request — stage power preferences
  // and race each attempt against a timeout.
  let adapter: MiniGPUAdapter | null = null;
  let timedOut = false;
  for (const options of [{ powerPreference: "high-performance" }, { powerPreference: "low-power" }, undefined]) {
    const started = Date.now();
    adapter = await withTimeout(
      gpu.requestAdapter(options).catch(() => null),
      6000,
    );
    if (adapter) break;
    if (Date.now() - started >= 5900) timedOut = true;
  }
  if (!adapter) {
    return { ...base, available: false, reason: timedOut ? "adapter-timeout" : "adapter-null" };
  }
  return {
    ...base,
    available: true,
    reason: null,
    adapterLabel: await readAdapterLabel(adapter),
    shaderF16: featuresHas(adapter, "shader-f16"),
  };
}

function environmentProblem(): string | null {
  if (typeof window === "undefined") return null;
  if (window.self !== window.top) {
    return "This preview runs inside an embedded frame, and Chrome blocks WebGPU in embedded frames. Open the preview URL directly in its own browser tab, then initialize.";
  }
  if (window.isSecureContext === false) {
    return "WebGPU requires a secure context (HTTPS or localhost). Open this page over HTTPS.";
  }
  return null;
}

const FLAG_UNSAFE_WEBGPU = "chrome://flags/#enable-unsafe-webgpu";
const FLAG_IGNORE_BLOCKLIST = "chrome://flags/#ignore-gpu-blocklist";
const FLAG_VULKAN = "chrome://flags/#enable-vulkan";

function unavailableAdvice(probe: GpuProbe): { headline: string; detail: string[]; flags?: string[] } {
  if (probe.reason === "no-navigator-gpu") {
    if (probe.isAndroid) {
      const version = probe.chromeVersion ? `Your Chrome is ${probe.chromeVersion}.` : "This browser does not report a Chrome version.";
      return {
        headline: "This browser does not expose WebGPU.",
        detail: [
          `WebGPU ships in Chrome 121+ on Android (Android 12+, Qualcomm/ARM GPUs). ${version}`,
          "Firefox, older Samsung Internet versions and in-app WebViews have no WebGPU — open this page in current Google Chrome.",
        ],
      };
    }
    return {
      headline: "This browser does not expose WebGPU.",
      detail: [
        "WebGPU ships by default in Chrome/Edge 113+ (Windows, macOS, ChromeOS). Firefox and Safari need current versions.",
        "On desktop Chrome also check chrome://settings/system → 'Use graphics acceleration when available'.",
      ],
    };
  }
  if (probe.reason === "adapter-timeout") {
    return {
      headline: "The GPU adapter request timed out.",
      detail: [
        "The graphics driver did not answer in time — this happens on some Android devices and virtual GPUs.",
        "Press Re-check GPU; if it persists, your GPU driver is likely blocklisted. Use a server provider on this device.",
      ],
      flags: [FLAG_UNSAFE_WEBGPU, FLAG_IGNORE_BLOCKLIST],
    };
  }
  // adapter-null: browser has WebGPU, but no adapter passes the GPU blocklist.
  if (probe.isAndroid) {
    const version = probe.chromeVersion ? ` (your Chrome: ${probe.chromeVersion})` : "";
    return {
      headline: "WebGPU exists, but your GPU is not on Chrome's allowlist — flags can fix this.",
      detail: [
        `Chrome enables WebGPU on Android 12+ with Qualcomm (Adreno) or ARM (Mali) GPUs${version}. MediaTek/PowerVR and Samsung Xclipse devices are not on the default allowlist (Xclipse needs Chrome 139+ on Android 16+).`,
        "Your report says the WebGPU API exists but requestAdapter fails — that is exactly the blocklist case. The flags below force WebGPU on.",
      ],
      flags: [FLAG_UNSAFE_WEBGPU, FLAG_IGNORE_BLOCKLIST, FLAG_VULKAN],
    };
  }
  return {
    headline: "WebGPU exists, but no GPU adapter was allowed.",
    detail: [
      "Your GPU or driver is on Chrome's blocklist, or hardware acceleration is off (chrome://settings/system).",
      "The flags below force WebGPU on despite the blocklist.",
    ],
    flags: [FLAG_UNSAFE_WEBGPU, FLAG_IGNORE_BLOCKLIST],
  };
}

function CopyFlagChip({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // Older Android WebViews block the async clipboard API — fall back to a hidden textarea.
      const area = document.createElement("textarea");
      area.value = value;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy");
      } catch {
        // Nothing else a web page can do; the raw text stays visible for manual typing.
      }
      document.body.removeChild(area);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [value]);
  return (
    <button
      type="button"
      onClick={() => void copy()}
      className="flex w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-amber-300/35 bg-amber-300/[0.08] px-2.5 py-2 text-left transition-colors hover:bg-amber-300/[0.15]"
    >
      <span className="copy-safe min-w-0 break-all font-mono text-[10px] leading-4 text-amber-100">{value}</span>
      <span className="shrink-0 font-mono text-[9px] uppercase text-amber-200/80">{copied ? "Copied ✓" : "Copy"}</span>
    </button>
  );
}

function resolveSlotModel(slotIndex: number, shaderF16: boolean): string {
  const slot = browserModels[slotIndex];
  return shaderF16 || !slot.f32 ? slot.f16 : slot.f32;
}

function slotIndexOf(model: string): number {
  const index = browserModels.findIndex((slot) => slot.f16 === model || slot.f32 === model);
  return index >= 0 ? index : 0;
}

export function BrowserLocalProvider({ onReadyChange, onModelChange, onEngineChange, onLoadStateChange, onRegisterLoadStop }: BrowserLocalProviderProps) {
  const [probe, setProbe] = useState<GpuProbe | null>(null);
  const [checking, setChecking] = useState(true);
  const [model, setModel] = useState<string>(DEFAULT_BROWSER_MODEL);
  const [status, setStatus] = useState<BrowserStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("");
  const [envProblem, setEnvProblem] = useState<string | null>(null);
  const engineRef = useRef<MLCEngine | null>(null);
  const cancelRequestedRef = useRef(false);

  const slotIndex = useMemo(() => slotIndexOf(model), [model]);
  const selected = browserModels[slotIndex];
  const shaderF16 = probe?.shaderF16 ?? true;
  const gpuAvailable = probe?.available ?? false;

  const runGpuCheck = useCallback(async () => {
    setChecking(true);
    setMessage("");
    setEnvProblem(environmentProblem());
    const result = await probeWebGPU();
    setProbe(result);
    setChecking(false);
    if (!result.available) {
      return;
    }
    if (!result.shaderF16 && model.endsWith("q4f16_1-MLC")) {
      const slot = browserModels.find((item) => item.f16 === model);
      if (slot?.f32) {
        setModel(slot.f32);
        onModelChange?.(slot.f32);
        setMessage("This GPU lacks the shader-f16 feature (common on Adreno). Switched to the q4f32 variant of the same model — press Initialize.");
        return;
      }
    }
  }, [model, onModelChange]);

  useEffect(() => {
    void runGpuCheck();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    onReadyChange?.(status === "ready");
  }, [onReadyChange, status]);

  useEffect(() => {
    // WebLLM cannot abort an in-flight engine creation; stopping detaches the engine the
    // moment the current step finishes, so the UI never stays stuck in "loading".
    onRegisterLoadStop?.(() => {
      if (!cancelRequestedRef.current) {
        cancelRequestedRef.current = true;
        setMessage("Stopping… the model is detached as soon as the current download step finishes.");
        onLoadStateChange?.({ loading: true, progress, label: "Stopping…", model: selected.label, done: false });
      }
    });
  }, [onRegisterLoadStop, onLoadStateChange, progress, selected.label]);

  const initialize = useCallback(async () => {
    if (envProblem) {
      setMessage(envProblem);
      return;
    }
    if (!gpuAvailable) {
      setMessage("WebGPU is not available on this device. Use a server provider, or apply the flags above and re-check.");
      return;
    }
    setStatus("loading");
    setProgress(0);
    cancelRequestedRef.current = false;
    setMessage(`Preparing ${selected.label} (${shaderF16 ? "q4f16" : "q4f32"}) for this device...`);
    onLoadStateChange?.({ loading: true, progress: 0, label: `Preparing ${selected.label}...`, model: selected.label, done: false });
    try {
      const { CreateMLCEngine } = await import("@mlc-ai/web-llm");
      const engine = await CreateMLCEngine(model, {
        initProgressCallback: (event) => {
          const value = typeof event.progress === "number" ? Math.round(event.progress * 100) : 0;
          setProgress(Math.max(0, Math.min(100, value)));
          setMessage(event.text || "Downloading browser model...");
          onLoadStateChange?.({ loading: true, progress: Math.max(0, Math.min(100, value)), label: event.text || "Downloading model weights...", model: selected.label, done: false });
        },
      });
      if (cancelRequestedRef.current) {
        try {
          await engine.unload();
        } catch {
          // A half-initialized engine may fail to unload; dropping the reference is enough.
        }
        onEngineChange?.(null);
        setStatus("idle");
        setProgress(0);
        setMessage("Load stopped — the model was detached before it became active.");
        onLoadStateChange?.(null);
        cancelRequestedRef.current = false;
        return;
      }
      engineRef.current = engine;
      onModelChange?.(model);
      onEngineChange?.(engine);
      setStatus("ready");
      setProgress(100);
      setMessage("Ready. This model runs locally in the browser tab.");
      onLoadStateChange?.({ loading: false, progress: 100, label: "Model ready", model: selected.label, done: true });
    } catch (error) {
      engineRef.current = null;
      onEngineChange?.(null);
      setStatus("error");
      const raw = error instanceof Error ? error.message : String(error);
      onLoadStateChange?.({ loading: false, progress: 0, label: `Model failed: ${raw.slice(0, 80)}`, model: selected.label, done: true });
      cancelRequestedRef.current = false;
      if (/shader-f16/i.test(raw)) {
        const slot = browserModels.find((item) => item.f16 === model);
        if (slot?.f32) {
          setModel(slot.f32);
          onModelChange?.(slot.f32);
          setStatus("idle");
          setMessage("This GPU does not support shader-f16. Switched to the q4f32 variant — press Initialize to load it.");
          return;
        }
      }
      setMessage(
        /OOM|out of memory|allocation/i.test(raw)
          ? `Not enough GPU memory for ${selected.label}. Pick a smaller model (SmolLM2 360M on Android).`
          : `${raw} — press Initialize to retry.`,
      );
    }
  }, [envProblem, gpuAvailable, model, onEngineChange, onLoadStateChange, onModelChange, onRegisterLoadStop, selected.label, shaderF16]);

  const changeModel = async (value: string) => {
    if (status === "loading") return;
    if (engineRef.current) {
      try {
        await engineRef.current.unload();
      } catch {
        // An already-broken engine may fail to unload; dropping the reference is enough.
      }
    }
    engineRef.current = null;
    onEngineChange?.(null);
    setModel(value);
    onModelChange?.(value);
    setStatus("idle");
    setProgress(0);
    setMessage("New model selected. Initialize it before assigning it to an agent.");
  };

  const advice = probe && !probe.available && !envProblem ? unavailableAdvice(probe) : null;
  const options = browserModels.map((slot, index) => {
    const id = resolveSlotModel(index, shaderF16);
    const quant = id.includes("q4f32") ? "q4f32" : "q4f16";
    return { id, label: `${slot.label} · ${quant} · ${slot.tier} · ${slot.size}` };
  });

  return (
    <section className="space-y-3 rounded-xl border border-cyan/20 bg-cyan/[0.04] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><p className="font-mono-label text-cyan">Browser local runtime</p><p className="mt-1 text-xs leading-5 text-fog/75">WebLLM loads real model weights directly into Chrome. No Ollama, URL, or API key.</p></div>
        <span className={`shrink-0 rounded-full border px-2 py-1 font-mono text-[9px] ${checking ? "border-white/15 text-fog/60" : status === "loading" ? "border-cyan/40 bg-cyan/[0.08] text-cyan" : probe?.available ? "border-lime/25 text-lime" : "border-coral/25 text-coral"}`}>{status === "loading" ? `Loading ${progress}%` : checking ? "Checking GPU" : probe?.available ? "WebGPU ready" : "WebGPU unavailable"}</span>
      </div>
      {envProblem && (
        <div className="space-y-2 rounded-lg border border-amber-300/25 bg-amber-300/[0.07] px-2.5 py-2">
          <p className="copy-safe break-words text-[11px] leading-5 text-amber-200/95">⚠️ {envProblem}</p>
          <button
            type="button"
            onClick={() => window.open(window.location.href, "_blank", "noopener")}
            className="rounded-lg border border-amber-300/40 bg-amber-300/[0.1] px-2.5 py-1.5 font-mono text-[10px] text-amber-200 transition-colors hover:bg-amber-300/[0.18]"
          >
            OPEN IN NEW TAB ↗
          </button>
        </div>
      )}
      {probe?.available && (
        <p className="copy-safe break-words rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-2 font-mono text-[10px] leading-4 text-fog/60">
          GPU: {probe.adapterLabel || "adapter detected"} · shader-f16: {probe.shaderF16 ? "✓" : "✗ (using q4f32 models)"} · Chrome {probe.chromeVersion ?? "?"}{probe.isAndroid ? " · Android" : ""}
        </p>
      )}
      <label className="block"><span className="font-mono-label text-fog/60">Browser model</span><select value={model} onChange={(event) => void changeModel(event.target.value)} disabled={status === "loading"} className="mt-2 h-10 w-full min-w-0 rounded-lg border border-white/10 bg-[#101722] px-3 text-xs text-white outline-none focus:border-cyan/50 disabled:opacity-60">{options.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      {/360M|0\.5B/.test(model) && <p className="copy-safe rounded-lg border border-amber-300/20 bg-amber-300/[0.06] px-2.5 py-2 text-[10px] leading-4 text-amber-200/90">⚠️ Tiny model — it may loop or repeat itself on complex prompts. Prefer Qwen 1.5B or Llama 3B on desktop for stable answers.</p>}
      {advice && (
        <div className="space-y-2 rounded-lg border border-coral/25 bg-coral/[0.06] px-2.5 py-2">
          <p className="copy-safe break-words text-[11px] font-semibold leading-5 text-coral">⚠️ {advice.headline}</p>
          {advice.detail.map((line) => (
            <p key={line.slice(0, 24)} className="copy-safe break-words text-[11px] leading-5 text-fog/80">{line}</p>
          ))}
          {advice.flags && advice.flags.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <p className="copy-safe break-words text-[10px] leading-4 text-fog/60">
                No web page can open chrome:// addresses — Chrome blocks that by design. Instead: tap <span className="text-amber-200">Copy</span> on each flag, paste it into the address bar (one at a time), set it to <span className="text-amber-200">Enabled</span>, then tap <span className="text-amber-200">Relaunch</span> at the bottom of the flags page and return here to press Re-check GPU.
              </p>
              {advice.flags.map((flag) => <CopyFlagChip key={flag} value={flag} />)}
            </div>
          )}
          <div className="flex flex-wrap gap-2 pt-1">
            <a href="https://webgpureport.org" target="_blank" rel="noopener noreferrer" className="rounded-lg border border-cyan/30 px-2.5 py-1.5 font-mono text-[10px] text-cyan transition-colors hover:bg-cyan/[0.08]">WebGPU REPORT ↗</a>
            <a href="https://developer.chrome.com/docs/web-platform/webgpu/troubleshooting-tips" target="_blank" rel="noopener noreferrer" className="rounded-lg border border-cyan/30 px-2.5 py-1.5 font-mono text-[10px] text-cyan transition-colors hover:bg-cyan/[0.08]">TROUBLESHOOTING DOCS ↗</a>
            <a href="https://web.dev/blog/webgpu-supported-major-browsers" target="_blank" rel="noopener noreferrer" className="rounded-lg border border-cyan/30 px-2.5 py-1.5 font-mono text-[10px] text-cyan transition-colors hover:bg-cyan/[0.08]">SUPPORT MATRIX ↗</a>
          </div>
        </div>
      )}
      {status === "loading" && <div className="space-y-2"><div className="h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-cyan transition-[width] duration-300" style={{ width: `${progress}%` }} /></div><div className="flex items-center justify-between gap-3 text-[10px] text-fog/60"><span className="truncate">{message}</span><span className="flex shrink-0 items-center gap-2"><span className="font-mono">{progress}%</span><button type="button" onClick={() => { if (!cancelRequestedRef.current) { cancelRequestedRef.current = true; setMessage("Stopping… the model is detached as soon as the current download step finishes."); } }} className="rounded-lg border border-coral/40 px-2 py-1 font-mono text-[9px] uppercase text-coral transition-colors hover:bg-coral/[0.12]">■ Stop</button></span></div></div>}
      {status !== "loading" && message && <p className={`copy-safe break-words text-xs leading-5 ${status === "error" ? "text-coral" : status === "ready" ? "text-lime" : "text-fog/65"}`}>{message}</p>}
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 truncate font-mono text-[10px] text-fog/45">{status === "ready" ? "Cached in this browser" : status === "error" ? "Ready to retry" : "First run downloads model weights"}</p>
        {!checking && !envProblem && (
          <button type="button" onClick={() => void runGpuCheck()} className="min-h-10 shrink-0 rounded-lg border border-cyan/30 px-3 text-xs text-cyan transition-colors hover:bg-cyan/[0.08]">Re-check GPU</button>
        )}
        <button type="button" onClick={() => void initialize()} disabled={checking || !gpuAvailable || status === "loading" || status === "ready"} className="min-h-10 shrink-0 rounded-lg bg-cyan px-3 text-xs font-semibold text-ink transition-transform hover:scale-[1.01] disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-fog/40">{status === "ready" ? "Initialized" : status === "loading" ? "Loading…" : "Initialize"}</button>
      </div>
    </section>
  );
}
