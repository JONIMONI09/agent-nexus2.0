---
name: agent-orchestration
description: Rules for single-AI vs multi-agent mode, subagent delegation, self-correction loops, and streaming event lifecycle. Use when modifying orchestration, agents, SSE events, or the chat run pipeline.
---

# Agent Orchestration — modes, delegation, loops

## Mode laws
- **Single AI mode** (`single_agent: true`, segmented control "Single AI" over the input bar) = EXACTLY ONE answer bubble labeled "AI". The main agent may commission a subagent (e.g. web_search) when needed — shown as a collapsible "Subagent commissioned" block inside its message. Never emit Scout + Synthesizer bubbles in this mode.
- **Two-agents mode** = Scout (Agent A) → Synthesizer (Agent B). Synthesizer gets Scout's evidence, expands creatively.
- The browser branch (`app/lib/browser-agent.ts`) must honor the same flag — the past bug was WebLLM always running the 2-agent loop regardless of the toggle. `run_complete` finalizes; it must never create a second message after `agent_completed` (past duplicate-answer bug).

## Execution-path routing law
- Any agent set to a **server provider** (Ollama, LM Studio, llama.cpp, LocalAI, vLLM, custom OpenAI-compatible) → FastAPI orchestrator (`python_backend/main.py`), streamed via SSE.
- Any agent set to **browser-webllm** → runs fully in the tab via `runBrowserAgents()`. NEVER forward `browser-webllm` to FastAPI (it answers "Provider not configured"). Never treat browser models as FastAPI provider IDs.

## Self-correction loop
- Invalid tool call (unknown skill / bad args) → `tool_error` → error text fed back as tool result → model retries with a valid call, capped by `MAX_TOOL_ROUNDS`. No consent modal for invalid calls. All retries visible in the trace.
- Fallback: primary model timeout/crash → configured fallback model → UI status line explains the swap transparently.

## Streaming lifecycle
Events: `run_started, agent_started, agent_think, tool_call_requested, tool_consent_required, tool_result, tool_error, delegation_started, delegation_completed, agent_delta, agent_completed, run_complete, run_failed`.
One streaming message per agent slot, created once and finalized once. Aborting a new run must clean up stale streams, IDs and status.

## Tests to keep green
`bun run test:python` (test_orchestration.py covers single-agent delegation + pipeline; schema validation; unknown skill).
