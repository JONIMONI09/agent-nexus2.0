---
name: bug-hunter
description: Systematic bug finding, isolation and fixing for this repo (Next.js frontend + FastAPI backend + browser WebLLM). Use when a user reports broken behavior, a crash, a wrong agent response, or when a preview/test fails.
---

# Bug Hunter — systematic debugging for Local Agent Studio

Follow these phases strictly. Never jump to a fix before reproducing.

## Phase 1 — Reproduce
- Get the exact symptom: what the user did, what they expected, what happened.
- Pull evidence, not guesses: `freebuff-preview logs`, browser console output, pytest failures.
- If it cannot be reproduced locally, say so explicitly and collect more data. Never fabricate a cause.

## Phase 2 — Isolate
Determine which layer owns the bug before touching code:
- **Next.js UI** (`app/**`): rendering, state, duplicated `useState` declarations, event wiring.
- **Next.js API proxy** (`app/api/**`): request/response shaping, SSE forwarding.
- **FastAPI backend** (`python_backend/**`): orchestration, tools, consent, provider routing.
- **Browser runtime** (`app/lib/browser-agent.ts`, `BrowserLocalProvider.tsx`): WebGPU detection, WebLLM init, streaming.
- **Provider side**: Ollama/external server unreachable, model not loaded, CORS.

Read the actual file first. This repo's past bugs were all concrete:
- duplicated `browserModel`/`browserReady` state in `app/page.tsx` (build error);
- `browser-webllm` forwarded to FastAPI → "Provider 'browser-webllm' is not configured";
- `run_complete` creating a second message after `scout_complete` → duplicate answers, no end marker.

## Phase 3 — Classify
Label the bug: state-duplication, wrong-layer routing, stream lifecycle, capability mismatch, model degeneration, environment (Ollama absent in sandbox = expected 502, not a bug).

## Phase 4 — Minimal fix
- Smallest change that fixes the root cause. No drive-by refactors.
- Keep provider routing laws intact: browser providers never go to FastAPI; server providers never run in the tab.
- For stream bugs: fix the event lifecycle (`agent_completed`/`run_complete` must finalize, never re-create).

## Phase 5 — Verify
Run, in order, and paste real output:
```bash
bun run typecheck
bun run test:python
freebuff-preview status
```
Only claim "fixed" after all three pass and the preview returns HTTP 200. Update `sessions.md` with cause + fix.
