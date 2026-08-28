---
name: provider-registry
description: Rules for adding/detecting LLM providers (Ollama, LM Studio, llama.cpp, LocalAI, vLLM, custom OpenAI-compatible URLs, browser WebLLM), capability probing and verified model IDs. Use when touching providers, model lists, or connection logic.
---

# Provider Registry — discovery, capabilities, honesty

## Provider families
- **Server**: Ollama (`/api/tags`, `/api/chat`), LM Studio (`/v1`), llama.cpp server (`/v1`), LocalAI (`/v1`), vLLM (`/v1`), any user-added OpenAI-compatible URL.
- **Browser**: `browser-webllm` (WebGPU in-tab, no URL, no key) — handled client-side only.

## Adding/validating a provider (user flow)
1. User enters a URL → normalize (append `/v1` for OpenAI-compatible, keep Ollama native paths).
2. Backend probes real endpoints (`provider_probe.py`) — never mark a provider available from a guess.
3. Load models ONLY from real discovery responses. Never ship invented model IDs.
4. Detect capabilities (chat, streaming, tool-calling, embeddings) and show them; UI disables what a provider cannot do.
5. Connection errors (CORS, refused, timeout) are surfaced verbatim in the UI — no silent swallowing.

## WebLLM model catalog law
- Only use model IDs verified to exist in the installed `@mlc-ai/web-llm` prebuilt list (check the package before adding).
- Android/low-memory picks: SmolLM2 360M, Qwen2.5 0.5B. Desktop: Qwen 1.5B, Llama 3.2 3B.
- A model is "ready" only after real `CreateMLCEngine` initialization completes with progress shown. "Initialized" without a completed load is a lie — never render it.

## Sandbox reality
Ollama is absent in the Freebuff sandbox → Ollama 502 in logs is EXPECTED, not a bug. Do not "fix" it; use Browser WebLLM or a reachable server provider for verification.

## Per-agent selection
Each agent (Scout, Synthesizer, Fallback, Main) picks provider + model independently, validated against that provider's real discovery output. Presets must only reference models the provider actually reports.

## Hard rules (added after real bugs)
- **Feature routing follows the answering model.** Any auxiliary feature that calls a model (translation, debate, summarization) must try the provider the run ACTUALLY answers with (scout route first), then the fallback. Bug precedent: auto-translate was hardwired to the fallback provider and silently no-op'd on browser-only setups — the user saw "translation doesn't work".
- **Browser-mode features must be fully client-capable.** If a feature should work in a browser-only setup (no Ollama/server running), implement it client-side (e.g. `translate-client.ts` with the WebLLM engine) — never only server-side.
- **Silent degradation needs a visible trace.** When an enhancement fails and the run continues with degraded behavior, emit an activity/error chip so the user can see WHY the feature "did nothing".
