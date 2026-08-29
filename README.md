# Local Agent Studio

A **local-first, multi-agent AI workspace**. Two agent minds — **The Scout** (research) and
**The Synthesizer** (writing) — collaborate on every answer, entirely through runtimes you control:
Ollama, any OpenAI-compatible local server (LM Studio, llama.cpp, LocalAI, vLLM), your own provider
URLs, or **models running directly in the browser via WebGPU** (WebLLM). No cloud inference is
required, and every tool call **pauses for your explicit approval**.

---

## Features

- 🧠 **Two-agent loop** — Scout gathers evidence (with your consent), Synthesizer crafts the final answer.
- 🪄 **Single AI mode** — one AI answers; when needed it **commissions a subagent** (web search). The
  delegation appears as a collapsible block inside the AI's message; the subagent's result is delivered
  back to the AI, which then answers correctly.
- 🛡️ **Manual consent for every tool call** — nothing runs silently. A high-priority modal asks
  **Allow / Deny** with the exact arguments before any web query is dispatched.
- ✅ **Tool-call validation & self-correction** — unknown skills or invalid arguments are rejected
  before consent, reported visibly in the chat, and fed back to the model so it retries with a valid call
  (capped to prevent loops).
- 🔁 **Auto-fallback** — if the primary model times out or crashes, a lighter fallback model takes over
  and the UI shows exactly what happened.
- 📱 **Mobile-first glassmorphism UI** — portrait-optimized, sticky bottom composer, slide-in settings
  drawer, floating **live sub-agent view** (thinking stream, tool calls, decisions, errors).
- 🖥️ **Browser-native inference** — WebLLM + WebGPU: pick a small model, hit **Initialize**, and run
  agents with **no server, no URL, no API key**. Model weights stay in the browser cache.
- 🔌 **Provider registry with capability detection** — add any OpenAI-compatible base URL, let the
  backend probe it, and models/capabilities are detected automatically.
- 🔐 **Privacy boundary** — provider secrets are referenced by environment-variable *name* only;
  values never reach the browser or the logs.

---

## Architecture

```text
Chrome Android / Desktop
        │  SSE stream (events)          browser WebGPU (optional)
        ▼                                     │
   Next.js 14 (App Router) ◄────────── WebLLM engine in-tab
        │  /api/chat proxy
        ▼
   FastAPI backend (Python)
        │
        ├── Provider Runtime ──► Ollama / LM Studio / llama.cpp / LocalAI / vLLM / custom URL
        ├── Consent Broker ────► waits for your Allow / Deny decision
        ├── Skill Registry ────► web_search (ddgs, zero API key)
        └── Agent loop ────────► Scout (evidence) → Synthesizer (answer)
                                 or single AI that delegates to a subagent
```

- **Transport:** Server-Sent Events (`text/event-stream`) for streaming deltas, thinking traces,
  tool-call requests, fallback notices and completion events.
- **Frontend:** Next.js 14 App Router, React 18, TypeScript, Tailwind CSS, Framer Motion.
- **Backend:** Python 3.11, FastAPI, Uvicorn, Pydantic v2, httpx.

---

## Tech stack

| Layer            | Choice                                                              |
| ---------------- | ------------------------------------------------------------------- |
| Frontend         | Next.js 14 (App Router), React 18, TypeScript                       |
| Styling          | Tailwind CSS, Framer Motion                                         |
| Backend          | Python 3.11, FastAPI, Uvicorn, Pydantic v2, httpx                   |
| Local LLMs       | Ollama (native API) or any OpenAI-compatible server                 |
| Browser LLMs     | WebLLM (`@mlc-ai/web-llm`) via WebGPU                               |
| Web search       | `ddgs` (keyless DuckDuckGo metasearch)                              |
| Persistence      | Local SQLite (standard library) for provider profiles / sessions    |
| Tests            | `tsc` typecheck, pytest, pytest-asyncio                             |

---

## Prerequisites

Pick at least **one** model source:

1. **Ollama** (recommended): install from [ollama.com](https://ollama.com), then pull a model:
   ```bash
   ollama pull qwen3        # or llama3.2, gemma3, mistral, phi ...
   ```
2. **Any OpenAI-compatible local server**: LM Studio (start the local server on port 1234),
   llama.cpp (`--server`, port 8080), LocalAI, vLLM, llamafile.
3. **Browser-only**: Chrome (desktop or Android) with **WebGPU enabled** — no server needed.
   Small models (SmolLM2 360M, Qwen 0.5B/1.5B, Llama 3.2 1B–3B) are offered in the UI.

Node.js 18+ and Bun are used for the frontend; Python 3.10+ for the backend.

---

## Quick start

```bash
# 1. Install dependencies (frontend + Python venv)
bun install
bun run setup:python

# 2. Start everything (Next.js on :3000, FastAPI on :8001)
bun run dev

# 3. Open http://localhost:3000
```

`bun run dev` runs both processes via `scripts/dev.sh`. In the Freebuff Cloud preview the same
command is the configured preview command.

### Useful scripts (`package.json`)

| Script                 | Purpose                                  |
| ---------------------- | ---------------------------------------- |
| `bun run dev`          | Start Next.js + FastAPI together         |
| `bun run dev:web`      | Next.js only (`0.0.0.0:3000`)            |
| `bun run dev:api`      | FastAPI only (`0.0.0.0:8001`)            |
| `bun run setup:python` | Create the Python venv and install deps  |
| `bun run typecheck`    | TypeScript project check (`tsc -b`)      |
| `bun run test:python`  | Backend test suite (pytest)              |
| `bun run build`        | Production build (`next build`)          |

---

## Configuration (environment variables)

All variables are optional; sensible defaults are used.

| Variable                     | Default                    | Purpose                                     |
| ---------------------------- | -------------------------- | ------------------------------------------- |
| `OLLAMA_BASE_URL`            | `http://localhost:11434`   | Ollama host                                 |
| `BACKEND_URL`                | `http://127.0.0.1:8001`    | FastAPI address used by the Next.js proxy   |
| `OLLAMA_TIMEOUT_SECONDS`     | `90`                       | Per-request LLM timeout                     |
| `APPROVAL_TIMEOUT_SECONDS`   | `300`                      | How long a consent prompt stays valid       |
| `MAX_CONTEXT_CHARS`          | `18000`                    | Context budget before compaction            |
| `MAX_TOOL_ROUNDS`            | `3`                        | Max tool-call rounds per agent (loop guard) |
| `FALLBACK_MODEL`             | `qwen2.5:3b`               | Default fallback model id                   |
| `PROVIDER_PROBE_TIMEOUT_SECONDS` | `5`                    | Timeout for provider capability probes      |

**Provider API keys** (optional, e.g. for an external OpenAI-compatible endpoint): set them in the
host environment and reference the variable **name** in the provider form. The backend resolves the
value at request time; it never ships the value to the browser and never logs it.

**GitHub integration** (optional): The `/api/github/sync` endpoint requires authentication. See
[SECURITY.md](SECURITY.md) for configuration details. Required environment variables:
- `GITHUB_SYNC_SECRET` — Authentication secret for the sync endpoint
- `GITHUB_TOKEN` — GitHub personal access token for repository operations

---

## Modes

### Multi-agent (default, checkbox "Single AI" unchecked)

1. **Agent A / Scout** — inspects the request; if fresh evidence is needed it requests
   `web_search`, which **pauses for your approval**. On approval the query runs locally via `ddgs`.
2. **Agent B / Synthesizer** — receives the Scout's evidence packet and writes the final answer
   with sources.

### Single AI (checkbox "Single AI" checked)

- One AI answers directly with the Synthesizer's model.
- When the request needs fresh web evidence, the AI **commissions the web_search subagent**: you see
  a collapsible **"Subagent commissioned · web_search"** block inside the AI's message.
- Expand the block to inspect the arguments, your decision, and the returned sources. The result is
  delivered back to the AI, which then incorporates it into a correct final answer.

---

## Filesystem agent team: scheduling & subagent messaging

The filesystem agent spawns a ROOT AGENT that orchestrates a jailed `projects/` workspace
and a commissioned subagent team. Two coordination systems power this:

### Subagent messaging (`message_subagent`)

The root agent commissions specialists as todos prefixed `subagent:` (e.g.
`"subagent: reviewer checks all files"`). It can then write to them directly:

- `message_subagent {todo_id, message}` — the subagent **reads the message in its own
  focused turn**, may **adjust its plan** (it is instructed to say so explicitly) and
  **replies to the root**. The full message thread is stored on the todo (visible in the
  panel as a 📨 badge) and the reply is injected into the root conversation.
- Subagent turns run on the same local model, never touch the filesystem in that reply
  turn, and are outage-resilient: a dead model returns `subagent failed to respond: …`
  as the reply instead of killing the run.
- Consent: `message_subagent`, `schedule_task` and `wait_for_schedule` never touch disk,
  so they bypass the tool-consent modal by design (file tools still always ask).

### Task scheduling (`schedule_task` / `wait_for_schedule`)

The root agent can schedule delayed work **with real waiting inside the run**:

- `schedule_task {description, delay_seconds}` — registers a task (1–300 s, max 8 per run).
- `wait_for_schedule {}` — **really waits** (async polling) until a task is due, then its
  description is delivered as a tool result the agent must act on.
- Safety rails: `GENERATION_STALL`-style caps — `MAX_DELAY_SECONDS=300`, `MAX_TASKS=8`,
  and a per-run **wait budget of 90 s** so a schedule-happy model can never hang the run.
  Invalid calls are rejected with a clear message the model self-corrects from.

SSE events for the panel: `fs_scheduled`, `fs_schedule_wait`, `fs_schedule_due`,
`fs_subagent_message`, `fs_subagent_reply`.

### Dead-code analysis with fallow

This repo ships [`fallow`](https://www.npmjs.com/package/fallow) (v3.19+) as a dev tool.
Find unused code before deleting anything:

```bash
bunx fallow dead-code          # unused exports, types, dependency hygiene
bunx fallow dead-code --trace app/components/types.ts:PipelineAgent   # prove a consumer really exists
bunx fallow audit --base main  # review changed files before a PR
bunx fallow health --hotspots  # complexity hotspots / refactoring priorities
```

Current status: clean. The one remaining `fallow dead-code` note — `tailwindcss` listed as
a dev dependency "used in production" — is a known false positive: Tailwind is a build-time
tool and production only ships the compiled CSS.

## Tool calling & consent

1. The model emits a `web_search` tool call with a query.
2. The backend **validates** the call against the skill schema:
   - **Valid call** → a `tool_call` SSE event opens the consent modal: tool name, arguments,
     **Allow once / Deny**. The pipeline waits (`APPROVAL_TIMEOUT_SECONDS`).
   - **Invalid call** (unknown skill, missing/typed arguments, out-of-range values) → a `tool_error`
     event. No consent modal is shown; a visible rejection message appears in the chat, and the error
     is returned to the model so it retries with a valid call (`MAX_TOOL_ROUNDS` cap prevents loops).
3. On approval the skill executes; on denial the model receives a denial result and answers without
   live evidence.

---

## Providers

Open **Settings → Providers & routing**. Built-ins: Ollama, LM Studio, llama.cpp, LocalAI, vLLM
(detected from their default local ports). You can also:

- **Add a custom OpenAI-compatible provider** — paste a base URL (e.g. `http://192.168.1.10:8080/v1`),
  run **Detect**, and the backend probes known endpoints, reports capabilities and lists models.
- **Use Browser local · WebLLM** — enable WebGPU in Chrome, pick a model, click **Initialize**
  (downloads weights with progress), then assign it to Scout / Synthesizer / Fallback.
- Route each agent to a different provider/model, including the fallback route.

---

## API reference

### Backend (FastAPI)

| Method | Endpoint                        | Purpose                                   |
| ------ | ------------------------------- | ----------------------------------------- |
| GET    | `/health`                       | Liveness                                  |
| GET    | `/providers`                    | List provider profiles                    |
| POST   | `/providers/detect`             | Probe a base URL, return capabilities     |
| POST   | `/providers`                    | Create/update a custom provider           |
| GET    | `/providers/{id}/models`        | Discover models for a provider            |
| DELETE | `/providers/{id}`               | Delete a custom provider                  |
| GET    | `/models`                       | List Ollama models (`/api/tags` proxy)    |
| POST   | `/approve-tool`                 | Resolve a consent request (`allow/deny`)  |
| POST   | `/orchestrate`                  | Run the agent pipeline (SSE response)     |

### SSE events (`POST /orchestrate`)

| Event          | Payload highlights                              | Meaning                                   |
| -------------- | ----------------------------------------------- | ----------------------------------------- |
| `run_started`  | `run_id`                                        | Pipeline started                          |
| `context`      | `compacted`, `dropped_count`                    | History packed for the context budget     |
| `agent_status` | `agent`, `phase`, `label`, `detail`             | Agent state change                        |
| `agent_delta`  | `agent`, `content`                              | Streamed answer text                      |
| `agent_think`  | `agent`, `content`                              | Streamed private reasoning trace          |
| `tool_call`    | `call_id`, `run_id`, `tool`, `arguments`        | Consent required — show the modal         |
| `tool_result`  | `call_id`, `tool`, `approved`, `reason`, `ok`, `sources` | Tool finished/blocked        |
| `tool_error`   | `tool`, `arguments`, `reason`                   | Invalid call — rejected before consent    |
| `fallback`     | `from_model`, `to_model`, `reason`              | Primary model failed, fallback engaged    |
| `agent_reset`  | `agent`, `reason`                               | Incomplete draft replaced                 |
| `scout_complete` | `brief`, `sources`                            | Scout finished (multi-agent mode)         |
| `run_complete` | `answer`, `sources`, `delegations`, `single_agent` | Final answer (incl. delegation blocks) |
| `error`        | `message`                                       | Run failed — nothing fabricated           |

The Next.js proxy at `/api/chat` forwards to `POST /orchestrate`; `app/api/providers/*` proxy the
provider registry.

---

## Project structure

```text
app/
  page.tsx                      Main chat UI (composer, streaming, consent, delegation)
  api/chat/route.ts             SSE proxy to FastAPI
  api/providers/**/route.ts     Provider registry proxies
  components/
    ChatMessage.tsx             Message bubble (+ delegation blocks, sources)
    SubAgentDelegation.tsx      Collapsible "subagent commissioned" block
    SubAgentPanel.tsx           Floating live sub-agent view
    ToolConsentModal.tsx        Allow / Deny overlay
    AgentStatus.tsx             Clickable agent pulse cards
    SettingsDrawer.tsx          Slide-in control room
    ProviderManager.tsx         Add/detect custom providers
    BrowserLocalProvider.tsx    WebLLM + WebGPU model manager
    ModelSelector.tsx           Model dropdown
    TracePanel.tsx              Run trace chips
    types.ts                    Shared frontend types
  lib/browser-agent.ts          In-browser Scout+Synthesizer runner
python_backend/
  main.py                       FastAPI app, SSE pipeline, agent loop
  agents/{scout,synthesizer,main_agent}.py   System prompts + message builders
  skills/web_search.py          ddgs skill (consent-gated)
  tools.py                      ToolRegistry + ConsentBroker
  provider_*.py                 Registry, probe, runtime, store
  tests/                        pytest suite
sessions.md                     Build memory (decisions, skills, pending items)
```

---

## Testing

```bash
bun run typecheck          # TypeScript project check
bun run test:python        # 15 backend tests
```

The backend suite covers: consent pipeline, schema validation of tool arguments, unknown-skill
rejection, fallback + draft reset, single-agent delegation collection, provider model discovery,
and context packing.

---

## Troubleshooting

- **"Ollama not found" / 502 on `/providers/ollama/models`** — no Ollama reachable at
  `OLLAMA_BASE_URL`. Start Ollama and pull a model, or switch the agents to another provider
  (LM Studio, llama.cpp, …) or to **Browser local · WebLLM**.
- **"Initialize the browser model before assigning it to an agent"** — open Settings → Browser
  local · WebLLM, pick a model and click **Initialize** (WebGPU required; Chrome only).
- **WebGPU unavailable** — the browser-local provider is disabled; use a server provider instead.
- **A run ends with no answer** — the stream may have hit the tool-call limit or a provider error;
  the UI shows the exact `error` event. Check the model is pulled and reachable.
- **Preview says the sandbox is gone** — the Freebuff cloud sandbox was cleaned up after inactivity;
  reconnect/provision the workspace again.

---

## Privacy

- Web search runs through `ddgs` from your own machine and only after explicit approval.
- Browser-WebLLM mode downloads model weights into the browser cache; prompts never leave the tab.
- Provider secrets are referenced by env-var name only; the backend keeps values out of the browser
  and out of the logs.
- Reasoning traces are streamed to your tab and shown in the live sub-agent view — nothing is sent
  to a cloud model provider unless you explicitly configure one.

---

## License

Private project — see repository owner for licensing terms.
