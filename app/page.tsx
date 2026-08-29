"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { AgentStatus } from "./components/AgentStatus";
import { ChatMessage } from "./components/ChatMessage";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { ActivityInspector } from "./components/ActivityInspector";
import { FsAgentPanel, type FsFeedItem, type FsTodo } from "./components/FsAgentPanel";
import { LearningBar } from "./components/LearningBar";
import { LearningPanel } from "./components/LearningPanel";
import type { LearningUpdate, ThinkingStyle } from "./components/types";
import { BROWSER_PROVIDER_ID, DEFAULT_BROWSER_MODEL, type BrowserLoadState } from "./components/BrowserLocalProvider";
import { detectNonEnglish, languageNoteSuffix, translateWithEngine } from "./lib/translate-client";
import { ToolConsentModal } from "./components/ToolConsentModal";
import { TracePanel } from "./components/TracePanel";
import type { AgentActivity, AgentState, ChatMessage as ChatMessageType, DebatePanel, Delegation, ProviderProfile, Source, ToolRequest } from "./components/types";
import type { MLCEngine } from "@mlc-ai/web-llm";
import { runBrowserAgents } from "./lib/browser-agent";

const initialScoutState: AgentState = {
  phase: "idle",
  label: "Standing by",
  detail: "Ready for a private research pass.",
};

const initialSynthesizerState: AgentState = {
  phase: "idle",
  label: "Standing by",
  detail: "Will shape the final answer after Scout.",
};

const starterMessage: ChatMessageType = {
  id: "welcome",
  role: "assistant",
  agent: "system",
  content: "Your local research desk is ready. Ask anything that benefits from current evidence, or use me as a private brainstorming partner.",
  createdAt: 0,
};

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function dedupeRepeatedText(text: string): string {
  // Collapse accidentally duplicated segments, e.g. "Provider 'browser-webllm' is not
  // configured.Provider 'browser-webllm' is not configured." → a single occurrence.
  let previous = "";
  let current = text;
  while (current !== previous) {
    previous = current;
    current = current.replace(/(.{20,}?)\1/g, "$1");
  }
  return current;
}

function defaultModel(models: string[], preferred: string) {
  return models.find((model) => model === preferred) ?? models[0] ?? preferred;
}

export default function HomePage() {
  const [messages, setMessages] = useState<ChatMessageType[]>([starterMessage]);
  const [input, setInput] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderProfile[]>([]);
  const [providersLoading, setProvidersLoading] = useState(true);
  const [providersError, setProvidersError] = useState("");
  const [providerModels, setProviderModels] = useState<Record<string, string[]>>({});
  const [providerModelsLoading, setProviderModelsLoading] = useState<Record<string, boolean>>({});
  const [scoutProviderId, setScoutProviderId] = useState("ollama");
  const [synthesizerProviderId, setSynthesizerProviderId] = useState("ollama");
  const [fallbackProviderId, setFallbackProviderId] = useState("ollama");
  const [scoutModel, setScoutModel] = useState("qwen3");
  const [synthesizerModel, setSynthesizerModel] = useState("qwen3");
  const [fallbackModel, setFallbackModel] = useState("qwen2.5:3b");
  const [browserModel, setBrowserModel] = useState(DEFAULT_BROWSER_MODEL);
  const browserModelRef = useRef(browserModel);
  const [browserReady, setBrowserReady] = useState(false);
  const browserEngineRef = useRef<MLCEngine | null>(null);
  const [autoTranslate, setAutoTranslate] = useState(false);
  const [browserLoad, setBrowserLoad] = useState<BrowserLoadState | null>(null);
  const browserLoadStopRef = useRef<(() => void) | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [scoutState, setScoutState] = useState<AgentState>(initialScoutState);
  const [synthesizerState, setSynthesizerState] = useState<AgentState>(initialSynthesizerState);
  const [pendingTool, setPendingTool] = useState<ToolRequest | null>(null);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [connectionLabel, setConnectionLabel] = useState("Local only");
  const [traceItems, setTraceItems] = useState<AgentActivity[]>([]);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [selectedActivity, setSelectedActivity] = useState<AgentActivity | null>(null);
  const [agentCount, setAgentCount] = useState(1);
  const [analystState, setAnalystState] = useState<AgentState>(initialScoutState);
  const [streamingScoutId, setStreamingScoutId] = useState<string | null>(null);
  const [streamingSynthesizerId, setStreamingSynthesizerId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [learningEnabled, setLearningEnabled] = useState(false);
  const [thinkingStyle, setThinkingStyle] = useState<ThinkingStyle>("balanced");
  const [learningUpdate, setLearningUpdate] = useState<LearningUpdate | null>(null);
  const [fsPanelOpen, setFsPanelOpen] = useState(false);
  const [fsRunning, setFsRunning] = useState(false);
  const [fsFeed, setFsFeed] = useState<FsFeedItem[]>([]);
  const [fsTodos, setFsTodos] = useState<FsTodo[]>([]);
  const [fsPendingTool, setFsPendingTool] = useState<{ runId: string; tool: string; arguments: Record<string, unknown> } | null>(null);
  const [fsSummary, setFsSummary] = useState("");
  const fsPendingRef = useRef<{ runId: string; approvalToken: string; tool: string; arguments: Record<string, unknown> } | null>(null);
  const fsApprovalTokenRef = useRef<string | null>(null);
  const fsAbortRef = useRef<AbortController | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);
  const streamingIdsRef = useRef<{ scout: string | null; synthesizer: string | null; analyst: string | null; main: string | null }>({ scout: null, synthesizer: null, analyst: null, main: null });
  const runningRef = useRef(false);

  const pushActivity = useCallback((agent: AgentActivity["agent"], kind: AgentActivity["kind"], text: string, detail?: string, payload?: AgentActivity["payload"]) => {
    setTraceItems((current) => {
      const last = current[current.length - 1];
      if (kind === "think" && last?.kind === "think" && last.agent === agent && last.text.length < 2000) {
        return [...current.slice(0, -1), { ...last, text: `${last.text}${text}` }];
      }
      const entry: AgentActivity = { id: createId("act"), agent, kind, text: text.slice(0, 800), detail, ts: Date.now(), payload };
      return [...current, entry].slice(-60);
    });
  }, []);

  const loadProviderModels = useCallback(async (providerId: string) => {
    setProviderModelsLoading((current) => ({ ...current, [providerId]: true }));
    try {
      const response = await fetch(`/api/providers/${encodeURIComponent(providerId)}/models`, { cache: "no-store" });
      const payload = (await response.json().catch(() => ({}))) as { ok?: boolean; models?: { name?: string; id?: string }[]; error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Model discovery failed.");
      const names = (payload.models ?? []).map((model) => model.name ?? model.id).filter((name): name is string => Boolean(name));
      setProviderModels((current) => ({ ...current, [providerId]: names }));
      if (providerId === "ollama") {
        if (names.length > 0) {
          setScoutModel((current) => defaultModel(names, current));
          setSynthesizerModel((current) => defaultModel(names, current));
          setFallbackModel((current) => defaultModel(names, current));
          setConnectionLabel("Ollama linked");
          setProvidersError("");
        } else {
          setConnectionLabel("Ollama not found");
          setProvidersError("Ollama returned no installed models.");
        }
      }
    } catch (error) {
      if (providerId === "ollama") setConnectionLabel("Ollama not found");
      setProvidersError(error instanceof Error ? error.message : "Could not discover provider models.");
      setProviderModels((current) => ({ ...current, [providerId]: [] }));
    } finally {
      setProviderModelsLoading((current) => ({ ...current, [providerId]: false }));
    }
  }, []);

  const refreshProviders = useCallback(async () => {
    setProvidersLoading(true);
    setProvidersError("");
    try {
      const response = await fetch("/api/providers", { cache: "no-store" });
      const payload = (await response.json().catch(() => ({}))) as { ok?: boolean; providers?: ProviderProfile[]; error?: string };
      if (!response.ok) throw new Error(payload.error ?? "The provider registry could not be loaded.");
      setProviders([...(payload.providers ?? []), { id: BROWSER_PROVIDER_ID, name: "Browser local · WebLLM", description: "Client-side WebGPU runtime", kind: "openai_compatible", base_url: "", auth_env_var: "", models_path: "", chat_path: "", default_model: browserModelRef.current, allowed_hosts: [], capabilities: { browser_webgpu: true, streaming: true }, builtin: true }]);
      setConnectionLabel("Provider registry ready");
      void loadProviderModels("ollama");
    } catch (error) {
      setProviders([]);
      setProvidersError(error instanceof Error ? error.message : "The provider registry could not be loaded.");
    } finally {
      setProvidersLoading(false);
    }
  }, [loadProviderModels]);

  useEffect(() => {
    void refreshProviders();
  }, [refreshProviders]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pendingTool, traceItems]);

  const chooseProvider = useCallback((agent: "scout" | "synthesizer" | "fallback", providerId: string) => {
    const provider = providers.find((item) => item.id === providerId);
    const model = providerId === BROWSER_PROVIDER_ID ? browserModel : provider?.default_model ?? "";
    if (agent === "scout") {
      setScoutProviderId(providerId);
      setScoutModel(model);
    } else if (agent === "synthesizer") {
      setSynthesizerProviderId(providerId);
      setSynthesizerModel(model);
    } else {
      setFallbackProviderId(providerId);
      setFallbackModel(model);
    }
    void loadProviderModels(providerId);
  }, [browserModel, loadProviderModels, providers]);

  const updateAgentState = useCallback((agent: "scout" | "synthesizer" | "analyst", state: AgentState) => {
    if (agent === "scout") setScoutState(state);
    else if (agent === "analyst") setAnalystState(state);
    else setSynthesizerState(state);
  }, []);

  const resetStreamingMessage = useCallback((agent?: "scout" | "synthesizer" | "analyst" | "main") => {
    setMessages((current) => current.filter((message) => {
      if (!message.streaming) return true;
      if (!agent) return false;
      return message.agent !== agent;
    }));
    if (!agent || agent === "scout") {
      setStreamingScoutId(null);
      streamingIdsRef.current.scout = null;
    }
    if (!agent || agent === "synthesizer") {
      setStreamingSynthesizerId(null);
      streamingIdsRef.current.synthesizer = null;
    }
    if (!agent || agent === "main") {
      streamingIdsRef.current.main = null;
    }
  }, []);

  const upsertStreamingMessage = useCallback((agent: "scout" | "synthesizer" | "analyst" | "main", content: string) => {
    const existingId = streamingIdsRef.current[agent];
    if (existingId) {
      setMessages((current) => current.map((message) => message.id === existingId ? { ...message, content: `${message.content}${content}` } : message));
      return;
    }
    const id = createId(agent);
    const nextMessage: ChatMessageType = {
      id,
      role: "assistant",
      agent,
      content,
      createdAt: Date.now(),
      startedAt: Date.now(),
      streaming: true,
    };
    streamingIdsRef.current[agent] = id;
    setMessages((current) => [...current, nextMessage]);
    if (agent === "scout") setStreamingScoutId(id);
    else if (agent === "synthesizer") setStreamingSynthesizerId(id);
  }, []);

  const commitStreamingMessage = useCallback((agent: "scout" | "synthesizer" | "analyst" | "main", content: string, sources?: Source[], delegations?: Delegation[]) => {
    const existingId = streamingIdsRef.current[agent];
    setMessages((current) => {
      if (!existingId) {
        if (!content.trim()) return current;
        return [...current, { id: createId(agent), role: "assistant", agent, content, sources, delegations, createdAt: Date.now(), startedAt: Date.now(), elapsedMs: 0 }];
      }
      return current.map((message) => message.id === existingId ? { ...message, content: content || message.content, sources, delegations, streaming: false, elapsedMs: message.startedAt ? Date.now() - message.startedAt : undefined } : message);
    });
    streamingIdsRef.current[agent] = null;
    if (agent === "scout") setStreamingScoutId(null);
    else if (agent === "synthesizer") setStreamingSynthesizerId(null);
  }, []);

  const onToolCall = useCallback((request: ToolRequest) => {
    setPendingTool(request);
  }, []);

  const handleToolDecision = useCallback(async (approved: boolean) => {
    if (!pendingTool) return;
    setDecisionBusy(true);
    try {
      const response = await fetch("/api/approve-tool", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ call_id: pendingTool.call_id, approved }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(payload?.error ?? "The consent decision could not be delivered.");
      }
      setPendingTool(null);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not resolve the tool request.");
    } finally {
      setDecisionBusy(false);
    }
  }, [pendingTool]);

  const consumeStream = useCallback(async (response: Response) => {
    if (!response.body) throw new Error("The local agent stream returned no body.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const handleEvent = async (line: string) => {
      const data = line.replace(/^data:\s*/, "");
      if (!data) return;
      const event = JSON.parse(data) as {
        type: string;
        agent?: "scout" | "synthesizer" | "analyst" | "main";
        phase?: AgentState["phase"];
        label?: string;
        detail?: string;
        content?: string;
        call_id?: string;
        run_id?: string;
        tool?: string;
        arguments?: Record<string, unknown>;
        approved?: boolean;
        reason?: string;
        sources?: Source[];
        brief?: string;
        answer?: string;
        from_model?: string;
        to_model?: string;
        compacted?: boolean;
        dropped_count?: number;
        message?: string;
        delegations?: Delegation[];
        single_agent?: boolean;
        topic?: string;
        speeches?: { role: string; speech: string }[];
        synthesis?: string;
        learning?: LearningUpdate;
        original?: string;
        language?: string;
        translated?: string;
      };

      if (event.type === "run_started") {
        pushActivity("system", "status", "Run started", event.run_id?.slice(0, 8));
      } else if (event.type === "context") {
        pushActivity("system", "status", event.compacted ? "Context compacted" : "Context ready", event.compacted ? `${event.dropped_count ?? 0} older message(s) omitted.` : "Full recent history retained.");
      } else if (event.type === "agent_status" && event.agent && event.phase && event.label) {
        if (event.agent === "scout" || event.agent === "synthesizer" || event.agent === "analyst") updateAgentState(event.agent, { phase: event.phase, label: event.label, detail: event.detail ?? "" });
        // Only REAL activity reaches the strip above the chat box. Pure thinking phases arrive
        // without an agent_status event, so quiet runs keep the strip empty.
        pushActivity(event.agent, "status", event.label, event.detail);
      } else if (event.type === "delegation_completed" && event.tool === "discuss") {
        const panel: DebatePanel = { topic: String(event.topic ?? ""), speeches: (event.speeches ?? []) as { role: string; speech: string }[], synthesis: String(event.synthesis ?? "") };
        const agent = event.agent === "synthesizer" ? "synthesizer" : event.agent === "analyst" ? "analyst" : "scout";
        pushActivity(agent, "debate", `Debate panel: ${panel.topic}`, panel.synthesis || "Panel finished.", { debate: panel });
      } else if (event.type === "agent_delta" && event.agent && event.content) {
        if (event.agent === "analyst") {
          pushActivity("analyst", "think", event.content);
        } else {
          upsertStreamingMessage(event.agent, event.content);
        }
      } else if (event.type === "agent_think" && event.agent && event.content && (event.agent === "scout" || event.agent === "synthesizer" || event.agent === "analyst")) {
        pushActivity(event.agent, "think", event.content);
      } else if (event.type === "analyst_complete") {
        pushActivity("analyst", "status", "Analyst packet ready", (event.brief ?? "").slice(0, 140) || "Evidence reviewed.");
      } else if (event.type === "tool_call" && event.call_id && event.run_id && event.tool) {
        onToolCall({ call_id: event.call_id, run_id: event.run_id, agent: event.agent ?? "scout", tool: event.tool, arguments: event.arguments ?? {} });
        if (event.agent) pushActivity(event.agent, "tool", `Subagent: ${event.tool}`, "Waiting for your decision.", { tool: event.tool, arguments: event.arguments ?? {} });
      } else if (event.type === "tool_result") {
        if (event.agent) pushActivity(event.agent, "decision", event.approved ? "Subagent allowed — result delivered" : "Subagent denied by you", event.reason, { approved: event.approved, reason: event.reason });
      } else if (event.type === "tool_error" && event.tool) {
        const reason = event.reason ?? "arguments did not match the skill schema.";
        if (event.agent) pushActivity(event.agent, "error", `Wrong tool call: ${event.tool}`, `${reason} — the AI retries with a valid call.`, { tool: event.tool, reason });
      } else if (event.type === "fallback") {
        pushActivity(event.agent ?? "system", "fallback", `Fallback: ${event.from_model} → ${event.to_model}`, event.reason ?? "Primary model failed.");
      } else if (event.type === "agent_reset") {
        resetStreamingMessage(event.agent);
        pushActivity(event.agent ?? "system", "status", "Draft reset", event.reason ?? "Replacing the incomplete turn.");
      } else if (event.type === "scout_complete") {
        commitStreamingMessage("scout", event.brief ?? "Scout completed without a written brief.", event.sources ?? []);
        pushActivity("scout", "status", "Scout brief ready", `${(event.sources ?? []).length} source(s) collected.`, { sources: event.sources ?? [] });
      } else if (event.type === "run_complete") {
        commitStreamingMessage(event.single_agent ? "main" : "synthesizer", event.answer ?? "The run completed without an answer.", event.sources ?? [], event.delegations);
        if (!event.single_agent) pushActivity("synthesizer", "status", "Answer complete", "Final response committed to the workspace.");
        pushActivity("system", "status", "Answer ready", event.single_agent ? "Single-agent response completed." : "The local agent loop completed.");
        if (event.learning && typeof event.learning === "object") {
          const learning = event.learning as LearningUpdate;
          if (learning.added_lessons > 0 || learning.added_rules > 0) {
            setLearningUpdate(learning);
            pushActivity("system", "learning", `Learned ${learning.added_lessons} insight(s)`, `${learning.added_rules} standing rule(s) stored in Rules.md.`);
          }
        }
      } else if (event.type === "input_translated") {
        const note = `${event.language ?? "non-English"} → English`;
        setMessages((current) => {
          let index = -1;
          for (let i = current.length - 1; i >= 0; i -= 1) {
            if (current[i].role === "user") { index = i; break; }
          }
          if (index === -1) return current;
          return current.map((message, i) => i === index ? { ...message, translation: `${note} · ${event.translated ?? ""}` } : message);
        });
        pushActivity("system", "status", `Input auto-translated (${note})`, (event.translated ?? "").slice(0, 140));
      } else if (event.type === "error") {
        throw new Error(dedupeRepeatedText(event.message ?? "The local agent run failed."));
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const eventBlock of events) {
        const dataLine = eventBlock.split("\n").find((line) => line.startsWith("data:"));
        if (dataLine) await handleEvent(dataLine);
      }
      if (done) {
        const finalDataLine = buffer.split("\n").find((line) => line.startsWith("data:"));
        if (finalDataLine) await handleEvent(finalDataLine);
        break;
      }
    }
  }, [commitStreamingMessage, onToolCall, pushActivity, resetStreamingMessage, updateAgentState, upsertStreamingMessage]);

  const setLearningOnServer = useCallback(async (enabled: boolean) => {
    try {
      await fetch("/api/learning", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) });
    } catch {
      // The drawer shows the server-side state on next open; never block the UI on this.
    }
  }, []);

  const pushFsFeed = useCallback((kind: FsFeedItem["kind"], text: string, detail?: string, ok?: boolean) => {
    setFsFeed((current) => [...current, { id: createId("fs"), kind, text: text.slice(0, 300), detail: detail?.slice(0, 1200), ok, ts: Date.now() }]);
  }, []);

  const handleFsDecision = useCallback(async (approved: boolean) => {
    const pending = fsPendingRef.current;
    const approvalToken = fsApprovalTokenRef.current;
    if (!pending || !approvalToken) return;
    try {
      const response = await fetch("/api/fs/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: pending.runId, approval_token: approvalToken, approved }),
      });
      if (!response.ok) throw new Error("The decision could not be delivered.");
      pushFsFeed("consent", approved ? `Allowed: ${pending.tool}` : `Denied: ${pending.tool}`, approved ? "The tool runs inside the projects jail." : "The tool was blocked by you.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not resolve the FS tool request.");
    } finally {
      fsPendingRef.current = null;
      setFsPendingTool(null);
    }
  }, [pushFsFeed]);

  const startFsRun = useCallback(async (task: string) => {
    if (fsRunning) return;
    const trimmed = task.trim();
    if (!trimmed) return;
    setFsPanelOpen(true);
    setFsRunning(true);
    setFsFeed([]);
    setFsTodos([]);
    setFsSummary("");
    setFsPendingTool(null);
    fsPendingRef.current = null;
    fsApprovalTokenRef.current = null;
    pushFsFeed("agent", "Root Agent starting", "Team protocol: docs/original_request.md + AGENTS.md rules.");
    setMessages((current) => [...current, { id: createId("user"), role: "user", content: `🛠️ Filesystem agent: ${trimmed}`, createdAt: Date.now() }]);

    const controller = new AbortController();
    fsAbortRef.current = controller;
    try {
      const response = await fetch("/api/fs/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ message: trimmed }),
      });
      if (!response.ok || !response.body) {
        const payload = (await response.json().catch(() => null)) as { error?: string; detail?: string } | null;
        throw new Error(payload?.error ?? payload?.detail ?? "The filesystem agent service rejected the run.");
      }
      
      // Capture the approval token from the response header
      const approvalToken = response.headers.get("X-Approval-Token");
      if (approvalToken) {
        fsApprovalTokenRef.current = approvalToken;
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of [...blocks, ...(done && buffer ? [buffer] : [])]) {
          const line = block.split("\n").find((item) => item.startsWith("data:"));
          if (!line) continue;
          const event = JSON.parse(line.replace(/^data:\s*/, "")) as Record<string, unknown>;
          const type = String(event.type ?? "");
          if (type === "fs_started") {
            pushFsFeed("agent", "Run started", String(event.run_id ?? "").slice(0, 8));
          } else if (type === "fs_agent_started") {
            pushFsFeed("agent", String(event.role ?? "Agent joined"));
          } else if (type === "fs_todo_list") {
            setFsTodos((event.todos as FsTodo[]) ?? []);
            pushFsFeed("todos", `Plan registered (${(event.created as number) ?? 0} todos)`);
          } else if (type === "fs_todo_update") {
            setFsTodos((event.todos as FsTodo[]) ?? []);
            pushFsFeed("todos", `Todo ${(event.id as string) ?? ""} ${event.ok ? "completed" : "unknown id"}`);
          } else if (type === "fs_tool_call") {
            const tool = String(event.tool ?? "");
            pushFsFeed("tool", `Tool: ${tool}`, JSON.stringify(event.arguments ?? {}).slice(0, 400));
          } else if (type === "fs_consent_required") {
            const pending = { runId: String(event.run_id ?? ""), approvalToken: approvalToken ?? "", tool: String(event.tool ?? ""), arguments: (event.arguments as Record<string, unknown>) ?? {} };
            fsPendingRef.current = pending;
            setFsPendingTool(pending);
            pushFsFeed("consent", `⚠️ Permission requested: ${pending.tool}`);
          } else if (type === "fs_consent_result") {
            pushFsFeed("consent", event.approved ? "Allowed — executing inside jail" : "Denied — tool skipped");
          } else if (type === "fs_tool_result") {
            pushFsFeed("result", event.ok ? `✓ ${event.tool}` : `✗ ${event.tool}`, String(event.brief ?? ""), Boolean(event.ok));
          } else if (type === "fs_tool_mismatch") {
            pushFsFeed("mismatch", "old_string mismatch", `${String(event.tool ?? "")}: ${String(event.reason ?? "")} — the AI must re-read the file and retry.`);
          } else if (type === "fs_loop_notice") {
            pushFsFeed("loop", "Loop detected — system told the AI", String(event.reason ?? ""));
          } else if (type === "fs_scheduled") {
            const task = event.task as { id?: string; description?: string; delay_seconds?: number } | undefined;
            pushFsFeed("agent", `⏱ Scheduled ${task?.id ?? "task"} (due in ${task?.delay_seconds ?? "?"}s)`, task?.description);
          } else if (type === "fs_schedule_wait") {
            pushFsFeed("agent", `⏳ Real waiting for scheduled tasks (budget left: ${String(event.budget_left ?? "?")}s)`);
          } else if (type === "fs_schedule_due") {
            const dueTasks = (event.tasks as Array<{ id?: string; description?: string }>) ?? [];
            pushFsFeed("result", `⏱ ${dueTasks.length} scheduled task(s) now due — handed to the AI`, dueTasks.map((task) => task.description).join(" · ").slice(0, 300), true);
          } else if (type === "fs_subagent_message") {
            pushFsFeed("agent", `📨 → ${String(event.agent ?? "subagent")}: root sent a message`, String(event.text ?? "").slice(0, 200));
          } else if (type === "fs_subagent_reply") {
            pushFsFeed("result", `📨 ← ${String(event.agent ?? "subagent")} replied — plan may be adjusted`, String(event.text ?? "").slice(0, 300), true);
          } else if (type === "fs_complete") {
            setFsTodos((event.todos as FsTodo[]) ?? []);
            setFsSummary(String(event.summary ?? "Run finished."));
            pushFsFeed("complete", "Run complete");
          } else if (type === "fs_error") {
            pushFsFeed("error", "Run failed", String(event.message ?? ""));
          }
        }
        if (done) break;
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        pushFsFeed("complete", "Filesystem run stopped", "Stopped by you; completed files and the current todo state were kept.");
      } else {
        pushFsFeed("error", "Run stopped", error instanceof Error ? error.message : "The filesystem agent run failed.");
      }
    } finally {
      fsAbortRef.current = null;
      fsPendingRef.current = null;
      fsApprovalTokenRef.current = null;
      setFsPendingTool(null);
      setFsRunning(false);
    }
  }, [fsRunning, pushFsFeed]);

  useEffect(() => {
    if (!browserLoad?.done) return;
    const timer = setTimeout(() => setBrowserLoad(null), 4500);
    return () => clearTimeout(timer);
  }, [browserLoad?.done]);

  const stopRun = useCallback(() => {
    // Server path: aborting the SSE fetch cancels the FastAPI stream (CancelledError →
    // consent cleanup). Browser path: WebLLM stops the generation in-flight. A model
    // LOAD in progress is detached as well.
    abortRef.current?.abort();
    try {
      browserEngineRef.current?.interruptGenerate();
    } catch {
      // The engine may be idle or already disposed.
    }
    browserLoadStopRef.current?.();
    if (fsRunning) fsAbortRef.current?.abort();
  }, [fsRunning]);

  const sendMessage = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || runningRef.current) return;
    setInput("");
    setErrorMessage("");
    setRunning(true);
    runningRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    setPendingTool(null);
    setTraceItems([]);
    setSelectedActivity(null);
    setAnalystState(initialScoutState);
    setSynthesizerState(initialSynthesizerState);
    setMessages((current) => [...current, { id: createId("user"), role: "user", content: trimmed, createdAt: Date.now() }]);

    const history = messages.filter((message): message is ChatMessageType & { role: "user" | "assistant" } => message.role === "user" || message.role === "assistant").slice(-40).map((message) => ({ role: message.role, content: message.content }));

    // When the browser runtime fails mid-run, transparently retry on a server provider
    // instead of dead-ending. Null unless that fallback path is active.
    let serverOverrides: { scoutProvider: string; synthesizerProvider: string; fallbackProvider: string; scoutModel: string; synthesizerModel: string } | null = null;
    try {
      if (scoutProviderId === BROWSER_PROVIDER_ID || synthesizerProviderId === BROWSER_PROVIDER_ID) {
        try {
          if (!browserEngineRef.current || !browserReady) throw new Error("Initialize the browser model before assigning it to an agent.");
        const tinyBrowserModel = /360M|0\.5B/i.test(browserModel);
        const onBrowserDelta = (event: { agent: "scout" | "synthesizer" | "main"; content: string }) => upsertStreamingMessage(event.agent, event.content);
        const noteDegraded = () => {
          setMessages((current) => [...current, { id: createId("loop"), role: "system", agent: "system", content: "⚠️ The browser model began repeating itself, so the answer was stopped early. For complex tasks switch to Qwen 1.5B / Llama 3B or a server provider.", createdAt: Date.now() }]);
          pushActivity("system", "error", "Output loop stopped", "The tiny browser model began repeating itself.");
        };
        // Browser-mode auto-translate: browser setups often have NO server provider running,
        // so translation happens right here with the in-browser model.
        let runMessage = trimmed;
        if (autoTranslate) {
          const detection = detectNonEnglish(trimmed);
          if (detection.nonEnglish) {
            pushActivity("system", "status", `Translating input (${detection.language} → English)`, "Using the in-browser model.");
            const translated = await translateWithEngine(browserEngineRef.current, trimmed);
            if (translated) {
              runMessage = translated + languageNoteSuffix(detection.language);
              setMessages((current) => {
                let index = -1;
                for (let i = current.length - 1; i >= 0; i -= 1) {
                  if (current[i].role === "user") { index = i; break; }
                }
                if (index === -1) return current;
                return current.map((message, i) => i === index ? { ...message, translation: `${detection.language} → English · ${translated}` } : message);
              });
              pushActivity("system", "status", `Input auto-translated (${detection.language} → English)`, translated.slice(0, 140));
            } else {
              pushActivity("system", "error", "Translation failed", "The browser model could not translate — running with the original message.");
            }
          }
        }
          if (agentCount === 1) {
            pushActivity("main", "status", "Browser AI active", "One in-browser model is answering.");
            setSynthesizerState({ phase: "working", label: "AI running locally", detail: browserModel });
            const browserResult = await runBrowserAgents(browserEngineRef.current, runMessage, history, systemPrompt, onBrowserDelta, true, tinyBrowserModel);
            commitStreamingMessage("main", browserResult.answer);
            if (browserResult.degraded) noteDegraded();
            pushActivity("system", "status", "Answer ready", "Single-agent browser response completed.");
            return;
          }
          pushActivity("system", "status", agentCount >= 3 ? "Browser mode runs Scout + Synthesizer" : "Browser agents active", "The in-browser tab executes the research loop locally.");
          pushActivity("scout", "status", "Scout running in browser", browserModel);
          setScoutState({ phase: "working", label: "Scout running locally", detail: browserModel });
          const browserResult = await runBrowserAgents(browserEngineRef.current, runMessage, history, systemPrompt, onBrowserDelta, false, tinyBrowserModel);
          if (browserResult.degraded) noteDegraded();
          commitStreamingMessage("scout", browserResult.scout);
          pushActivity("scout", "status", "Scout brief ready", "Browser-local inference (no web access in browser mode).");
          pushActivity("synthesizer", "status", "Synthesizer drafting", browserModel);
          setSynthesizerState({ phase: "working", label: "Synthesizer running locally", detail: browserModel });
          commitStreamingMessage("synthesizer", browserResult.answer);
          pushActivity("synthesizer", "status", "Answer complete", "Browser-local inference.");
          pushActivity("system", "status", "Answer ready", "Browser-local inference completed.");
          return;
        } catch (browserError) {
          const serverProviderId = fallbackProviderId && fallbackProviderId !== BROWSER_PROVIDER_ID
            ? fallbackProviderId
            : providers.find((provider) => provider.id !== BROWSER_PROVIDER_ID)?.id ?? "";
          if (!serverProviderId) throw browserError;
          const reason = browserError instanceof Error ? browserError.message : String(browserError);
          resetStreamingMessage();
          setMessages((current) => [...current, { id: createId("fallback"), role: "system", agent: "system", content: `⚠️ Browser runtime failed: ${reason} Retrying on the server provider "${serverProviderId}".`, createdAt: Date.now() }]);
          pushActivity("system", "fallback", "Browser → server fallback", reason);
          serverOverrides = { scoutProvider: serverProviderId, synthesizerProvider: serverProviderId, fallbackProvider: serverProviderId, scoutModel: fallbackModel, synthesizerModel: fallbackModel };
        }
      }
      // The browser provider lives only in this tab. Before calling the server, replace
      // any browser-webllm slot (including the fallback route, which the server can never
      // run) with the first configured server provider. This used to surface as a cryptic,
      // doubled "Provider 'browser-webllm' is not configured." error.
      const firstServerProviderId = providers.find((provider) => provider.id !== BROWSER_PROVIDER_ID)?.id ?? "";
      const serverSlot = (providerId: string, model: string) =>
        providerId && providerId !== BROWSER_PROVIDER_ID
          ? { provider: providerId, model }
          : { provider: firstServerProviderId, model: fallbackModel };
      const scoutSlot = serverSlot(serverOverrides?.scoutProvider ?? scoutProviderId, serverOverrides?.scoutModel ?? scoutModel);
      const synthesizerSlot = serverSlot(serverOverrides?.synthesizerProvider ?? synthesizerProviderId, serverOverrides?.synthesizerModel ?? synthesizerModel);
      const fallbackSlot = serverSlot(serverOverrides?.fallbackProvider ?? fallbackProviderId, fallbackModel);
      if (!scoutSlot.provider || !synthesizerSlot.provider || !fallbackSlot.provider) {
        const note = "No server provider is configured, and the browser model cannot serve a server-side run. Open Settings → Providers & routing to add a server provider, or initialize the browser model and keep every agent route on Browser local.";
        setErrorMessage(note);
        pushActivity("system", "error", "No provider available", note);
        return;
      }
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ message: trimmed, scout_model: scoutSlot.model, synthesizer_model: synthesizerSlot.model, fallback_model: fallbackSlot.model, scout_provider_id: scoutSlot.provider, synthesizer_provider_id: synthesizerSlot.provider, fallback_provider_id: fallbackSlot.provider, system_prompt: systemPrompt, history, single_agent: agentCount === 1, agent_count: agentCount, learning_enabled: learningEnabled, thinking_style: thinkingStyle, translate_input: autoTranslate }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string; detail?: string } | null;
        throw new Error(dedupeRepeatedText(payload?.error ?? payload?.detail ?? "The local agent service rejected the run."));
      }
      await consumeStream(response);
      setConnectionLabel("Ollama linked");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        // User pressed Stop: keep the partial answer, close the stream cleanly.
        setMessages((current) => [
          ...current.map((message) => message.streaming ? { ...message, streaming: false, elapsedMs: message.startedAt ? Date.now() - message.startedAt : undefined } : message),
          { id: createId("stop"), role: "system", agent: "system", content: "⏹ Run stopped by you — the partial answer was kept.", createdAt: Date.now() },
        ]);
        streamingIdsRef.current = { scout: null, synthesizer: null, analyst: null, main: null };
        setStreamingScoutId(null);
        setStreamingSynthesizerId(null);
        pushActivity("system", "status", "Run stopped", "You stopped this run; partial output was kept.");
      } else {
        resetStreamingMessage();
        setErrorMessage(dedupeRepeatedText(error instanceof Error ? error.message : "The local agent run failed."));
        pushActivity("system", "error", "Run stopped", dedupeRepeatedText(error instanceof Error ? error.message : "The local agent run failed.").slice(0, 140));
        setScoutState((current) => ({ ...current, phase: "error", label: "Run stopped" }));
        setSynthesizerState((current) => ({ ...current, phase: "error", label: "Waiting for next run" }));
      }
    } finally {
      abortRef.current = null;
      setPendingTool(null);
      setRunning(false);
      runningRef.current = false;
    }
  }, [agentCount, autoTranslate, browserModel, browserReady, commitStreamingMessage, consumeStream, fallbackModel, fallbackProviderId, input, learningEnabled, messages, providers, pushActivity, resetStreamingMessage, scoutModel, scoutProviderId, synthesizerModel, synthesizerProviderId, systemPrompt, thinkingStyle, upsertStreamingMessage]);

  const clearConversation = useCallback(() => {
    if (runningRef.current) return;
    setMessages([starterMessage]);
    setTraceItems([]);
    setSelectedActivity(null);
    setErrorMessage("");
    setScoutState(initialScoutState);
    setAnalystState(initialScoutState);
    setSynthesizerState(initialSynthesizerState);
  }, []);

  return (
    <main className="relative flex min-h-[100dvh] flex-col overflow-hidden bg-ink">
      <div className="pointer-events-none absolute inset-0 hairline-grid" />
      <header className="relative z-10 flex h-[72px] shrink-0 items-center justify-between border-b border-white/10 bg-ink/75 px-4 backdrop-blur-xl sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <button type="button" onClick={() => setDrawerOpen(true)} className="group grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.04] transition-colors hover:border-lime/40 hover:bg-lime/[0.06]" aria-label="Open settings">
            <span className="flex w-5 flex-col gap-1.5" aria-hidden="true"><span className="h-px w-5 bg-white transition-transform group-hover:translate-x-1" /><span className="h-px w-3 bg-lime transition-transform group-hover:translate-x-1" /><span className="h-px w-4 bg-white transition-transform group-hover:translate-x-1" /></span>
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono-label text-lime">Local Agent Studio</span>
              <span className="hidden rounded-full border border-cyan/20 px-2 py-0.5 font-mono text-[9px] text-cyan sm:inline">PRIVATE LOOP</span>
            </div>
            <p className="truncate text-xs text-fog/60">Two local minds, one deliberate answer.</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={`hidden items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-[10px] sm:flex ${connectionLabel === "Ollama linked" ? "border-lime/20 text-lime" : "border-coral/20 text-coral"}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${connectionLabel === "Ollama linked" ? "bg-lime" : "bg-coral"}`} />{connectionLabel}
          </span>
          <button type="button" onClick={clearConversation} disabled={running} className="grid h-10 w-10 place-items-center rounded-xl border border-white/10 text-lg text-fog transition-colors hover:border-white/25 hover:text-white disabled:opacity-40" aria-label="Clear conversation">↻</button>
        </div>
      </header>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 pb-2 pt-4 sm:px-8 sm:pt-6">
          <div className="flex min-w-0 items-center gap-2"><span className={`h-1.5 w-1.5 shrink-0 rounded-full ${running ? "animate-pulse bg-lime" : "bg-white/30"}`} /><span className="truncate font-mono-label text-fog/55">Workspace / Research loop</span></div>
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" onClick={() => { setSelectedActivity(null); setInspectorOpen(true); }} className={`flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono-label transition-colors ${running ? "border-cyan/40 bg-cyan/[0.08] text-cyan" : "border-white/10 text-fog/60 hover:border-cyan/30 hover:text-cyan"}`}><span className={`h-1.5 w-1.5 rounded-full ${running ? "animate-pulse bg-cyan" : "bg-white/25"}`} />Activity</button>
            <button
              type="button"
              onClick={() => {
                const task = window.prompt("What should the filesystem agent team build? It will create projects/<name>/ with README, AGENTS.md rules and docs.");
                if (task && task.trim()) void startFsRun(task);
              }}
              disabled={fsRunning || running}
              className={`flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono-label transition-colors ${fsRunning ? "border-lime/40 bg-lime/[0.1] text-lime" : "border-lime/25 text-lime/90 hover:bg-lime/[0.08]"} disabled:opacity-50`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${fsRunning ? "animate-pulse bg-lime" : "bg-lime/60"}`} />FS agent
            </button>
            <button type="button" onClick={() => setDrawerOpen(true)} className="font-mono-label text-fog/50 transition-colors hover:text-cyan sm:hidden">Settings</button>
          </div>
        </div>

        <section className="min-h-0 flex-1 overflow-y-auto px-4 pb-5 sm:px-8">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 pb-4 pt-5 sm:pt-8">
            {messages.length === 1 && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-3 max-w-xl">
                <p className="font-mono-label text-cyan">Private intelligence workspace</p>
                <h1 className="mt-3 text-4xl font-semibold leading-[1.04] text-white sm:text-6xl">Two minds.<br /><span className="text-lime">One clear signal.</span></h1>
                <p className="mt-5 max-w-md text-sm leading-6 text-fog/75">The Scout gathers evidence when you approve it. The Synthesizer turns that evidence into an answer, entirely through your local runtime.</p>
                <div className="mt-7 grid max-w-md grid-cols-2 gap-3">
                  <div className="rounded-xl border border-cyan/15 bg-cyan/[0.04] p-3"><p className="font-mono-label text-cyan">A / Scout</p><p className="mt-2 text-xs leading-5 text-fog/70">Fresh evidence, explicit tool gates.</p></div>
                  <div className="rounded-xl border border-lime/15 bg-lime/[0.04] p-3"><p className="font-mono-label text-lime">B / Synthesis</p><p className="mt-2 text-xs leading-5 text-fog/70">Grounded structure, local inference.</p></div>
                </div>
              </motion.div>
            )}

            <AnimatePresence initial={false} mode="popLayout">
              {messages.map((message) => <ChatMessage key={message.id} message={message} />)}
            </AnimatePresence>
            <div ref={scrollAnchorRef} />
          </div>
        </section>

        <div className="relative shrink-0 border-t border-white/10 bg-ink/80 pb-[max(12px,env(safe-area-inset-bottom))] pt-3 backdrop-blur-xl">
          <TracePanel items={traceItems} active={running} onSelect={(item) => { setSelectedActivity(item); setInspectorOpen(true); }} />
          <LearningBar update={learningUpdate} enabled={learningEnabled} onOpen={() => setDrawerOpen(true)} />
          <div className="mx-auto w-full max-w-3xl px-4 sm:px-6">
            {errorMessage && <div className="mb-3 copy-safe rounded-xl border border-coral/25 bg-coral/[0.07] px-3 py-2 text-xs leading-5 text-coral">{errorMessage}</div>}
            <form onSubmit={sendMessage} className="glass-panel flex items-end gap-2 rounded-2xl p-2 shadow-glow">
              <label className="sr-only" htmlFor="chat-input">Message the local agents</label>
              <textarea id="chat-input" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} rows={1} maxLength={8000} placeholder="Ask the local loop anything..." disabled={running} className="max-h-32 min-h-11 min-w-0 flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-5 text-white outline-none placeholder:text-fog/45 disabled:cursor-wait" />
              {running ? (
                <button type="button" onClick={stopRun} className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-coral/40 bg-coral/[0.12] text-base text-coral transition-colors hover:bg-coral/[0.2]" aria-label="Stop run">■</button>
              ) : (
                <button type="submit" disabled={!input.trim()} className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-lime text-xl font-semibold text-ink transition-transform hover:scale-[1.03] disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-fog/30" aria-label="Send message">↑</button>
              )}
            </form>
            <div className="mt-2 flex items-center justify-between gap-3 px-1">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex shrink-0 items-center gap-1.5">
                  <span className="font-mono-label text-fog/50">Agents</span>
                  <div role="group" aria-label="Active agent count" className="flex rounded-full border border-white/10 bg-white/[0.03] p-0.5">
                    {[1, 2, 3].map((count) => (
                      <button
                        key={count}
                        type="button"
                        onClick={() => setAgentCount(count)}
                        disabled={running}
                        title={count === 1 ? "One AI — delegates to subagents only when needed (default)." : count === 2 ? "Scout gathers evidence, Synthesizer answers." : "Scout + Analyst + Synthesizer — the evidence gets reviewed."}
                        className={`h-7 w-7 rounded-full font-mono text-[10px] transition-colors disabled:cursor-not-allowed ${agentCount === count ? "bg-lime text-ink" : "text-fog/55 hover:text-white"}`}
                      >
                        {count}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="truncate font-mono text-[10px] text-fog/40">{running ? "The local loop is active" : `${thinkingStyle} · ${agentCount === 1 ? `${synthesizerModel} · one AI` : agentCount === 2 ? `scout → ${synthesizerModel}` : `scout → analyst → ${synthesizerModel}`}${learningEnabled ? " · learning" : ""}`}</p>
              </div>
              <p className="shrink-0 font-mono text-[10px] text-fog/35">{input.length}/8000</p>
            </div>
          </div>
        </div>
      </div>

      <SettingsDrawer browserModel={browserModel} browserReady={browserReady} onBrowserModelChange={(value) => { browserModelRef.current = value; setBrowserModel(value); }} onBrowserReadyChange={setBrowserReady} onBrowserEngineChange={(engine) => { browserEngineRef.current = engine; }} open={drawerOpen} onClose={() => setDrawerOpen(false)} scoutProviderId={scoutProviderId} synthesizerProviderId={synthesizerProviderId} fallbackProviderId={fallbackProviderId} scoutModel={scoutModel} synthesizerModel={synthesizerModel} fallbackModel={fallbackModel} systemPrompt={systemPrompt} providers={providers} providersLoading={providersLoading} providersError={providersError} providerModels={providerModels} providerModelsLoading={providerModelsLoading} scoutState={scoutState} synthesizerState={synthesizerState} onScoutProviderChange={(value) => chooseProvider("scout", value)} onSynthesizerProviderChange={(value) => chooseProvider("synthesizer", value)} onFallbackProviderChange={(value) => chooseProvider("fallback", value)} onScoutModelChange={setScoutModel} onSynthesizerModelChange={setSynthesizerModel} onFallbackModelChange={setFallbackModel} onSystemPromptChange={setSystemPrompt} onRefreshProviders={() => void refreshProviders()} onRefreshProviderModels={(providerId) => void loadProviderModels(providerId)} onOpenSubAgents={() => { setSelectedActivity(null); setInspectorOpen(true); }} analystState={analystState} agentCount={agentCount} learningEnabled={learningEnabled} onLearningEnabledChange={(value) => { setLearningEnabled(value); void setLearningOnServer(value); }} thinkingStyle={thinkingStyle} onThinkingStyleChange={setThinkingStyle} autoTranslate={autoTranslate} onAutoTranslateChange={setAutoTranslate} onBrowserLoadStateChange={setBrowserLoad} onRegisterLoadStop={(stop) => { browserLoadStopRef.current = stop; }} />
      <ActivityInspector open={inspectorOpen} onClose={() => setInspectorOpen(false)} items={traceItems} selected={selectedActivity} />
      <FsAgentPanel
        open={fsPanelOpen}
        onClose={() => setFsPanelOpen(false)}
        running={fsRunning}
        feed={fsFeed}
        todos={fsTodos}
        pendingTool={fsPendingTool ? { tool: fsPendingTool.tool, arguments: fsPendingTool.arguments } : null}
        onDecision={(approved) => void handleFsDecision(approved)}
        decisionBusy={false}
        summary={fsSummary}
      />
      <ToolConsentModal request={pendingTool} busy={decisionBusy} onDecision={(approved) => void handleToolDecision(approved)} />
      {browserLoad && (browserLoad.loading || browserLoad.done) && (
        <div className="fixed bottom-24 left-3 z-[60] w-60 rounded-xl border border-cyan/25 bg-[#0d131d]/95 p-3 shadow-glow backdrop-blur">
          {browserLoad.loading ? (
            <>
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-mono text-[10px] text-cyan">⏳ {browserLoad.model}</p>
                <span className="shrink-0 font-mono text-[10px] text-cyan">{browserLoad.progress}%</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-cyan transition-[width] duration-300" style={{ width: `${browserLoad.progress}%` }} /></div>
              <p className="copy-safe mt-1 truncate font-mono text-[9px] text-fog/55">{browserLoad.label}</p>
              <button type="button" onClick={() => browserLoadStopRef.current?.()} className="mt-2 w-full rounded-lg border border-coral/40 px-2 py-1.5 font-mono text-[9px] uppercase text-coral transition-colors hover:bg-coral/[0.12]">■ Stop loading</button>
            </>
          ) : (
            <p className="copy-safe break-words font-mono text-[10px] leading-4 text-lime">✓ {browserLoad.model} ready</p>
          )}
        </div>
      )}
    </main>
  );
}
