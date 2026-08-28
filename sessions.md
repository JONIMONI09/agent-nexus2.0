# Local Agent Studio — Project Memory (sessions.md)

## 2026-08-27 (4) — FS Agent Team: jailed filesystem, Docker hardening, todos, loop guard (web-researched)
### Research grounding
- **Antigravity 2.0** (antigravity.google): multi-agent orchestration with root orchestrator + parallel subagents + error recovery/retries → adapted as RootAgent + named subagent todos + self-correction protocol.
- **AGENTS.md standard** (agents.md, 60k+ repos): "README for agents" → every project + every subfolder gets a generated AGENTS.md with boundaries, edit protocol and folder purpose.
- **OWASP Docker cheat sheet**: hardened runtime = `--cap-drop ALL --security-opt no-new-privileges --read-only --network none --user 65532:65532 --pids-limit --memory --cpus` + only projects/ bind-mounted rw (implemented in `jail.DockerSandboxConfig.run_argv`), selectable in Settings (falls back to path jail when Docker absent — it is absent in this sandbox).
- **fallow on npm** (v3.19.0, verified `--help`): real codebase analyzer → `fallow_analyze` tool (audit/health/dead-code/dupes/inspect) wired for the agent; installed as devDependency.
### Implemented (`python_backend/fs_agent/`)
- `jail.py`: PathJail (lexical + symlink escape defense, traversal tests) + hardened Docker config; projects root `<repo>/projects/`.
- `fs_tools.py`: fs_tree, fs_read_file, fs_create_project (README + AGENTS.md + docs/original_request.md verbatim + docs/decisions.md), fs_create_folder (auto-AGENTS.md), fs_write_file (placeholder rejection, no blind overwrite), fs_edit_file (**old_string verification**: MISMATCH → model MUST re-read then retry; AMBIGUOUS → longer unique string; allow_multiple opt-in), fallow_analyze.
- `todos.py`: mandatory todo board — complex tasks detected (hints/length), model must todo_add a plan; finish is refused while todos are open unless explained; board streamed to UI.
- `loop.py`: fingerprint-based loop detection → throttled ⚠️ SYSTEM notices to the model (max 3) + error-streak guard; round cap (24) ends the run with the best result.
- `team.py`: RootAgent protocol (read original_request + AGENTS.md, subagent: prefixed todos, verify with fallow, honest finish); SSE events fs_started/fs_agent_started/fs_todo_list/fs_todo_update/fs_tool_call/fs_tool_mismatch/fs_loop_notice/fs_consent_required/fs_consent_result/fs_tool_result/fs_complete/fs_error; every real tool call is consent-gated.
- Endpoints: GET/POST /fs/settings (sandbox=jailed|docker, docker→409 if unavailable), POST /fs/run (SSE), POST /fs/approve.
### Frontend
- **FS agent spawn button** in the workspace bar → prompt for the task → opens **FsAgentPanel** floating window: NO input field — display-only feed (TEAM/TOOL/RESULT/MISMATCH/⚠LOOP/CONSENT/DONE), todo checklist on top, Allow/Deny card when a tool needs consent.
- Settings → **Filesystem agent sandbox** section: jailed (default) vs Docker (disabled with hint when unavailable).
### Verified (real runs)
- pytest 42 passed (13 new: traversal blocked, hardened docker flags present, project structure, AGENTS.md per folder, mismatch protocol, ambiguous edit, todos, loop notices).
- E2E smoke via fake-chat driver: project scaffolded (`demo-app/` full tree incl. src/hello.py), escape attempt to /etc/passwd **blocked** + reported as mismatch, loop guard fired correctly, finish honored.
- `bun run typecheck` ✓ · /api/fs 200 · frontend 200.
### Note
- Docker binary is not present in this sandbox → jail mode is the enforced default; Docker selection returns 409 until a Docker-enabled host is used.

## 2026-08-27 (3) — Browser-model init fixes + general bug hunt + toolchain audit
### Why "cannot initialize" browser models happened (root causes + fixes)
- **All 4 catalog model IDs VERIFIED present** in installed @mlc-ai/web-llm 0.2.84 prebuilt list (165 models; SmolLM2-360M q4f16_1, Qwen2.5-0.5B/1.5B, Llama-3.2-3B all FOUND) — catalog was never the issue.
- **Embedded-frame WebGPU block (main cause):** the preview often runs inside an iframe; Chrome blocks WebGPU there. Fix: detect `window.self !== window.top` + non-secure context, show a clear amber explanation and an OPEN-IN-NEW-TAB button (tab initializes fine).
- **GPU check could hang forever** (button disabled, nothing happens): adapter request now races a 6s timeout with powerPreference high-performance; plus a RE-CHECK GPU retry button and concrete guidance (Chrome 121+, hardware acceleration).
- **OOM misread as generic failure:** init errors containing OOM/out-of-memory now say "not enough GPU memory → pick a smaller model"; all errors offer retry (button stays enabled after error).
- **Engine leak on model switch:** previous engine is now `unload()`ed before switching.
- **Provider-refetch cascade (general bug):** `browserModel` in `refreshProviders` deps caused a full registry refetch on every model keystroke/change; now read via `browserModelRef` (stable deps).
### Toolchain audit (as requested)
- `bun install` → "Checked 111 installs across 119 packages (no changes)" — dependency tree intact.
- `--help` verified for: next CLI, tsc, pytest, uvicorn, npm install (all respond with full parameter help).
- Sandbox episode: both dev servers were reaped mid-session and the freebuff-preview CLI is missing again; restarted the durable `scripts/dev.sh` and verified: frontend HTTP 200, /health 200, /api/learning ✓, /api/providers ✓, agent_count=4 → 422 (new backend live), count=1 stream event chain correct (fallback/error expected: no Ollama in sandbox).
- `bun run typecheck` ✓ clean · `bun run test:python` ✓ 29 passed.

## 2026-08-27 (2) — Agent count selector + activity chips + floating inspector
### Agent count instead of Two/Single toggle
- New `agent_count` (1–3, default 1, Pydantic ge/le validated → 422 outside range). 1 = one AI with delegation; 2 = Scout→Synthesizer; 3 = Scout→**Analyst**→Synthesizer (new `agents/analyst.py`: critiques/extends the Scout packet; emits `analyst_complete`; its review is appended to the Synthesizer evidence packet). `single_agent` still honored for compat (count==1 sends it).
- UI: `Agents [1|2|3]` selector over the input bar (default 1), live status line shows the pipeline (`scout → analyst → model`). Browser mode caps at the 1/2-agent paths and says so in the trace.
### Sub-agent visuals moved OUT of chat → chips + floating window
- Removed from chat messages: delegation blocks, debate block, and the red tool-error system message. Sub-agent activity now appears ONLY as clickable chips in the strip above the chat box (TracePanel rewritten: kind-colored chips, THINK chips dimmed).
- Clicking a chip opens the new `ActivityInspector` floating window: reasoning steps appear COLLAPSED (expand on tap); tool/subagent entries expand by default showing args, your Allow/Deny decision, delivered sources, and the debate panel. Selected chip is highlighted + auto-scrolled. Reasoning-only chip → just that step.
- Unified activity store: one `traceItems: AgentActivity[]` (agents scout/analyst/synthesizer/main/system; kinds incl. debate/learning; payload carries tool/args/decision/sources/debate). SubAgentPanel/SubAgentDelegation/DebateBlock deleted; AgentStatus + drawer support the Analyst card (shown when count ≥ 3).
### Verified
- `bun run typecheck` ✓ · `bun run test:python` ✓ 29 passed (3 new: 3-agent pipeline runs analyst, 2-agent skips it, analyst prompt contains evidence).
- Throwaway uvicorn on :8002: agent_count=4 → HTTP 422; count=3 streams correct event set (fallback/error path only because Ollama is absent in the sandbox); /learning round-trip ✓.
- NOTE: the managed preview's uvicorn (started by scripts/dev.sh without --reload) still serves pre-change backend code until the preview is restarted via the platform; the Next.js frontend hot-reloads automatically.

## 2026-08-27 — Honest activity, Learning memory, Debate subagents, Thinking styles
### Fixed: phantom activity above the chat box
- Root cause: backend emitted speculative `agent_status` events every run ("Scout is waking up", "Scout is scanning", "Reasoning locally") and the frontend traced every one. Now the model-thinking phase is SILENT: no status event → empty strip. Real activity only: commissioning a skill (web_search/discuss), waiting for consent, correcting an invalid call, fallback, completion.
### New: Learning system (learning.py + /api/learning + LearningPanel)
- `memory/learn.md` (auto-extracted lessons), `memory/Rules.md` (standing rules, user-editable), `memory/Agent.md` (persona). Toggle in settings; when on, `prompt_block()` injects rules+persona+last 12 lessons (≤2400 chars) into every agent prompt.
- Deterministic extraction from user words (markers: "always", "never", "from now on", "be more", "i want"…); timestamped bullets, dedupe by normalized text (bug fixed: dedupe must strip the `[stamp]` prefix); learn.md capped at 200 body lines.
- After each run with learning on, `run_complete` carries `learning: {added_lessons, added_rules}` → `LearningBar` above the chat box shows "Learned N new insights" (click → settings).
- API: GET/POST /learning, PUT /learning/files/{learn|rules|agent}, POST /learning/files/{name}/reset (Next proxies in app/api/learning/*; fixed double body-read bug in route.ts).
### New: discuss subagent (skills/discuss.py)
- Consent-gated like web_search: main AI delegates a topic → Advocate/Critic/Pragmatist debate on the LOCAL fallback model → `delegation_completed` event → DebateBlock inside the AI message (collapsible speeches + synthesis). Schema: topic (3-220 chars, required), speakers 2-3.
### New: thinking styles (request.thinking_style)
- concise | balanced | deep | creative — injected as a thinking-profile hint in scout/main/synthesizer prompts; selector in settings, live status line under the input.
### Tests: 26 passed (11 new: lesson extraction, dedupe, prompt block, debate parse/skill, memory injection, delegation event). Typecheck clean. Frontend+backend HTTP 200.
### Note
- `freebuff-preview` CLI missing in restored sandbox; verified via direct HTTP (frontend 3000 + uvicorn 8001) instead.


## Agent skills (.claude/skills/ — invoked by typing / in chat)
Created 8 repo-native skills (Freebuff loads `.claude/skills/<name>/SKILL.md`):
- `bug-hunter` — systematic Bugsuche: reproduce → isolate → classify → minimal fix → verify; grounded in this repo's real past bugs (duplicated state in page.tsx, browser provider sent to FastAPI, run_complete double-message).
- `tool-consent` — consent laws: tools never run silently; Deny = explicit tool result; invalid calls rejected pre-modal with self-correction.
- `agent-orchestration` — Single AI = exactly one bubble with visible subagent delegation; two-agents = Scout→Synthesizer; browser-vs-server routing law; SSE lifecycle rules.
- `provider-registry` — real endpoint probing, no invented model IDs, verified WebLLM catalog (Android: SmolLM2 360M / Qwen 0.5B), honest readiness states.
- `repetition-guard` — degenerate-output detection, token caps, mini-model prompting, amber tiny-model warning.
- `mobile-first-ui` — portrait-first, sticky bottom bar, drawer must not shift layout on hover, zero text overflow at 360 px, glassmorphism tokens.
- `verify-stack` — no false claims: typecheck + test:python + freebuff-preview status with real output before "done".
- `context-compression` — compress traces/summaries but never drop decisions, constraints, consent results.
- `web-research` — anti-hallucination protocol: mandatory verification before dependencies/models/APIs.
- `session-memory` — this file's maintenance rules (append-only, verified states only).

## Goal
A local-first, multi-agent AI web app: two agent minds (Scout + Synthesizer) that research and answer
through local runtimes, with explicit user consent for every tool call, a privacy-first mobile UI, and
optional in-browser (WebGPU) inference. Zero mandatory API keys.

## Stack (decided after web research, 2026)
- Frontend: Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Framer Motion
- Backend: Python 3.11, FastAPI, Uvicorn, Pydantic v2, httpx
- Local models: Ollama native API (`/api/tags`, `/api/pull`, `/api/chat`) — primary
- Browser models: WebLLM (`@mlc-ai/web-llm`) via WebGPU, no server needed
- Other local runtimes: any OpenAI-compatible base URL (LM Studio, llama.cpp, LocalAI, vLLM)
- External providers: optional, user-supplied keys via env-var names only (server-side)
- Web search: `ddgs` (zero API key), consent-gated
- Persistence: local SQLite (standard library)
- Custom provider adapters: Deno as a separate, permission-scoped process (planned; not yet wired into UI)

## Architecture decisions
- Provider registry with capability detection (`/providers`, `/providers/detect`, `/providers/{id}/models`).
- Two execution modes:
  - **Multi-agent** (`single_agent=false`): Scout (web research + consent) → Synthesizer (final answer).
  - **Single AI** (`single_agent=true`): one main agent that may delegate to the `web_search` subagent;
    delegation appears as a collapsible block inside the AI message ("Subagent beauftragt · web_search"),
    result is delivered back to the model, which then answers correctly.
- Shared tool loop: `run_agent_loop()` in `python_backend/main.py` powers both modes
  (consent broker, JSON-schema validation, self-correction, fallback, context packing).
- Tool-call validation: unknown skills or invalid arguments emit `tool_error`, are never sent to consent,
  and the error is fed back to the model as a tool result so the agent retries (capped by `MAX_TOOL_ROUNDS`).
- Streaming: SSE events (`agent_delta`, `agent_think`, `tool_call`, `tool_result`, `tool_error`,
  `fallback`, `agent_reset`, `scout_complete`, `run_complete`, `error`).
- UI: glassmorphism, mobile-first; settings drawer (no mouse-drag), floating Sub-Agent panel
  (live thinking/tool/decision/error feed), collapsible delegation blocks in messages.

## Files created (key)
- `python_backend/main.py`, `types.py`, `config.py`, `provider_*.py`, `skills/web_search.py`, `tools.py`
- `python_backend/agents/scout.py`, `agents/synthesizer.py`, `agents/main_agent.py`
- `python_backend/tests/test_orchestration.py`, `test_consent_pipeline.py`
- `app/page.tsx`, `app/components/{ChatMessage,AgentStatus,SettingsDrawer,SubAgentPanel,SubAgentDelegation,ToolConsentModal,TracePanel,ProviderManager,ModelSelector,BrowserLocalProvider}.tsx`
- `app/lib/browser-agent.ts`, `app/api/{chat,providers}/route.ts`
- `sessions.md` (this file)

## Skills
- `web_search` (ddgs): keyless DuckDuckGo metasearch; requires explicit user approval each call.

## Tests
- `bun run typecheck` — TypeScript project check
- `bun run test:python` — 15 pytest cases (consent pipeline, tool validation, fallback, single-agent
  delegation, provider models, context packing)

## Localization & docs
- All user-facing UI copy is in English (incl. the "Single AI" toggle and subagent delegation blocks).
- `README.md` documents setup, configuration, modes, providers, consent flow, API/SSE reference, testing and troubleshooting.

## WebGPU diagnosis round (2026-08-27, mobile "WebGPU unavailable" fix)
- Web research verified:
  - WebGPU ships by default in Chrome 121+ on Android, but ONLY on Android 12+ with Qualcomm (Adreno)
    or ARM (Mali) GPUs (web.dev/blog/webgpu-supported-major-browsers, developer.chrome.com/blog/new-in-webgpu-121).
    MediaTek/PowerVR devices are NOT allowlisted; Samsung Xclipse needs Chrome 139+ on Android 16+ (gpuweb wiki).
  - shader-f16 is missing on many Adreno adapters (Vulkan 16-bit storage gap, gpuweb#5006); q4f16_1 WebLLM
    models fail with "This model requires WebGPU extension shader-f16" (web-llm#254) → q4f32_1 variants bypass it.
  - Recent Qualcomm init failures even with f16 reported (web-llm#836, Jun 2026).
- `BrowserLocalProvider.tsx` rewritten:
  - Deep GPU probe: staged requestAdapter (high-performance → low-power → default, 6s timeout each),
    adapter.info/requestAdapterInfo label, shader-f16 feature check, Chrome version + Android detection.
  - Targeted advice per failure reason (no-navigator-gpu / adapter-null / adapter-timeout) incl. copyable
    flags `chrome://flags/#enable-unsafe-webgpu` + `chrome://flags/#ignore-gpu-blocklist` (chrome:// cannot be linked) and
    real links: webgpureport.org, Chrome troubleshooting docs, web.dev support matrix.
  - Model slots now carry f16 + f32 IDs; auto-switch to q4f32 when the adapter lacks shader-f16 (and on
    init error containing "shader-f16"). All 4 f32 IDs verified in web-llm 0.2.84 prebuiltAppConfig:
    SmolLM2-360M, Llama-3.2-1B, SmolLM2-1.7B, Llama-3.2-3B (q4f32_1).
  - New export `DEFAULT_BROWSER_MODEL`; page.tsx default no longer hardcodes the ID.
- Verified: typecheck clean, 42 python tests pass, frontend/backend HTTP 200.

## Flag copy-chips round (2026-08-27, user webgpureport showed "api exists / requestAdapter failed")
- User's webgpureport.org result confirmed the adapter-null blocklist case: WebGPU API present,
  requestAdapter failed in dedicated/shared/service workers → flags can force it on.
- Added `CopyFlagChip` (clipboard API + execCommand fallback for old Android WebViews) with one-tap
  copy for `chrome://flags/#enable-unsafe-webgpu`, `chrome://flags/#ignore-gpu-blocklist`,
  `chrome://flags/#enable-vulkan` (Android last resort), plus step-by-step instructions
  (chrome:// can never be opened by a link — Chrome blocks navigation to internal pages).
- Verified: typecheck clean, 42 tests pass, frontend/backend HTTP 200.

## Fallback-everywhere + stall watchdogs + run timer (2026-08-27)
- User confirmed WebGPU now works on their Android device (flags fixed it).
- Backend (`collect_turn`): per-chunk stall watchdog via `asyncio.wait_for(anext(...), GENERATION_STALL_TIMEOUT_SECONDS=45s,
  env-tunable)` — a hung provider now raises and `collect_with_fallback` transparently retries on the fallback model
  (fallbacks now also cover hangs, not just crashes; `run_analyst` degrades gracefully, 3-agent run continues without review).
- Browser agent (`browser-agent.ts`): parity protections — 25s no-token stall watchdog that calls
  `engine.interruptGenerate()` and throws so callers can fall back (on top of repetition guard + token caps).
- page.tsx: browser-run failure (uninitialized engine, OOM, stall) now falls back automatically to a server
  provider (fallback provider first, else first non-browser) with a transparent system note + activity chip;
  server request uses fallback provider/model overrides.
- Run timer: ChatMessage now carries startedAt/elapsedMs; a live ⏱ timer ticks under assistant messages while
  generating and freezes as "generation time" when committed.
- Tests: 3 new stall-watchdog tests (stall raises, stall → fallback model + fallback event, slow-but-alive stream OK). 45 passed.

## Stop button, free auto-translate, load toast, copy-everything (2026-08-27)
- STOP button: send button swaps to ■ while a run is active. Server path aborts the SSE fetch
  (AbortController → FastAPI CancelledError → consent cleanup); browser path calls
  `engine.interruptGenerate()`. Aborted runs KEEP the partial answer (⏹ system note) instead of
  showing an error — AbortError is handled explicitly, not as a failure.
- Free auto-translate (zero API keys): `python_backend/translate.py` — heuristic language detection
  (scripts + Latin hints + English markers), translation via the user's OWN local model
  (fallback provider/model, 20s cap). Enabled via Settings → "Auto-translate input"
  (`translate_input` in OrchestrateRequest). Agents get English + a "reply in <language>" note;
  learning extracts from the ORIGINAL message; UI shows "🌐 German → English · …" under the user
  bubble + activity chip; `input_translated` SSE event. Failure ⇒ original text, run continues.
- Model-load background indicator: BrowserLocalProvider reports BrowserLoadState
  (progress/label/model/done) → floating toast bottom-left stays visible with the drawer closed;
  "✓ Model ready" auto-hides after 4.5s; failures shown too.
- Copy-everything: shared CopyButton (clipboard API + execCommand fallback) on system/error messages
  ("Copy error"), tool-consent modal ("Copy call" JSON) and every activity inspector entry (full JSON).
- Tests: 8 new translation tests (detection DE/EN/Cyrillic, note, translation, English pass-through
  without model call, failure resilience, implausible output rejection). 53 passed, typecheck clean,
  frontend/backend 200, /api/chat accepts translate_input.

## FS-team scheduling + subagent messaging + fallow dead-code (2026-08-27)
- New FS-agent tools (handled in the runner, no consent needed — they never touch disk):
  - `schedule_task {description, delay_seconds 1..300}` + `wait_for_schedule` — REAL waiting
    (async polling) bounded by a 90s per-run budget; due tasks are delivered as tool results.
    Module: `fs_agent/scheduler.py` (MAX_TASKS=8, ScheduleError fed back to the model).
  - `message_subagent {todo_id, message}` — root writes to `subagent:` todos; the subagent
    gets its OWN focused turn (SUBAGENT_SYSTEM_PROMPT: read messages directly, adjust plan,
    reply PLAN/STATUS/NOTE). Thread stored on the todo (📨 badge in panel), reply injected
    into the root conversation. Outage-resilient (failed turn ⇒ error-as-reply).
- Fixed a real double-collect bug in `Scheduler.wait_for_due` (while-condition consumed due
  tasks; final collect returned empty) — caught by the new integration tests.
- Frontend: FS panel shows ⏱ scheduled/waiting/due, 📨 subagent send/reply feed items and a
  message-thread badge on todos; FsTodo type carries messages.
- fallow dead-code (as requested): removed unused exports `browserModels` export, `PipelineAgent`,
  `ModelInfo` + the unused SettingsDrawer import; re-ran fallow → clean (tailwindcss-in-prod note
  documented as a known false positive in README).
- Docs: README section "Filesystem agent team: scheduling & subagent messaging" incl. fallow usage.
- Verified: 58 tests passed (5 new team-coordination integration tests), typecheck clean,
  frontend/backend 200, /fs/settings responds.

## Bug round: stop-the-load, translation routing, toast z-index (2026-08-27, user reports)
- Translation "doesn't work" — ROOT CAUSE: it was hardwired to the FALLBACK provider (usually ollama
  = dead on browser-only setups) and failed silently. Fixes:
  - Backend: `translation_routes()` — scout (answering) provider/model FIRST, fallback second, deduped;
    `translate_message_best_effort()` walks routes in order. 5 new route tests.
  - Browser mode: full client-side translation (`app/lib/translate-client.ts`) using the WebLLM engine
    itself (heuristics ported + strict translate pass); translated message + "reply in <language>" note
    feed the browser agents; visible chips for translating/succeeded/failed.
- Model load could not be stopped ("frozen"): WebLLM cannot abort engine creation → cancel flag +
  "■ Stop" (in provider card AND global toast AND composer ■), on completion the engine is unloaded
  and an honest "Load stopped — detached" state is shown. stopRun also detaches loads.
- Toast z-index bug: toast was z-40, same as the full-height settings drawer → invisible while the
  drawer was open. Now z-[60], shows exact % number + label + stop button; drawer badge shows
  "Loading N%" live.
- Skills improved with the new hard rules: provider-registry (feature routing follows the answering
  model; browser features must be client-capable; visible degradation), mobile-first-ui (toast
  z-law, exact live values, mandatory Stop for long ops), verify-stack (test the user's actual path).
- Verified: 63 tests passed, typecheck clean, frontend/backend 200, fallow clean.

## Stop freeze + translation routing + UI progress audit (2026-08-27)
- Fixed FS Agent stop behavior: `/api/fs/run` now uses an AbortController in page.tsx;
  Stop cancels chat, WebLLM generation, model loading, and FS-team SSE. Partial state/todos
  remain visible and a clear stopped feed event is emitted.
- Fixed translation provider selection: server translation routes now prefer the actual
  answering Scout provider/model, then the fallback; browser runs use the client WebLLM
  translator. Added route priority/dedup/failure tests.
- Fixed progress visibility: model loading shows exact percentage in both the open provider
  card and z-[60] global toast above the drawer; both expose Stop loading.
- Added schedule/subagent integration UI and tests from previous round.
- Verification this round: `bun run typecheck` clean; `pytest` 63 passed; frontend HTTP 200;
  backend /health HTTP 200; `fallow dead-code` has no unused-code findings (only Tailwind
  build dependency advisory, documented in README).

## Preview process diagnosis (2026-08-27)
- User reported that the dev server could not be stopped. Checked the managed preview interface:
  initial status was `running:false`, `listening:true`, `statusCode:200`, no preview logs. This means
  the managed process state had drifted, not that the Next.js app had a runtime error.
- Used the supported `freebuff-preview restart` operation (not pkill/kill). It returned:
  `Preview is ready`, `running:true`, `listening:true`, port 3000.
- No Git/PR action taken: workspace has no repository and generated `.next`/state changes are not
  source changes for a PR.

## GitHub integration (2026-08-27)
- Implemented server-side GitHub REST client (`python_backend/github_service.py`): repo info,
  branch creation, pull-request creation; token read only from `GITHUB_TOKEN`, never logged;
  input validation for owner/repo, SHA, refs and title.
- FastAPI endpoints: `/github/status`, `/github/repo`, `/github/branch`, `/github/pr`;
  Next.js proxy routes under `app/api/github/*`.
- Tests: `python_backend/tests/test_github_service.py` (6 tests); full suite 69 passed,
  `tsc` clean.
- Git hygiene: added `.gitignore` (`.next`, `__pycache__`, `.venv`, `tsconfig.tsbuildinfo`,
  `.local_agent_studio`, env files) and untracked generated artifacts; two commits on branch
  `feature/github-integration` (6644d29, c30f9fe).
- BLOCKED on push: Freebuff workspace reports "This blank Cloud project is not connected to
  GitHub yet" for any git network operation; no `GITHUB_TOKEN` env var present. User must
  connect the repository in the Freebuff UI or set `GITHUB_TOKEN` in Keys; then push branch
  and open PR against `main` (remote repo `JONIMONI09/agent-nexus2.0` currently empty).

## Session: provider-config hardening (browser-webllm "not configured")

**Bug:** Backend raised `Provider 'browser-webllm' is not configured.` twice per run when a
browser-only run leaked the browser provider id to the server.

**Root cause:** Translation routes and the fallback path treated `browser-webllm` like a normal
server provider, and the frontend sent the browser provider id to the backend even when the
run was browser-local. There was no pre-flight check and no dedupe of repeated error text.

**Fixes (backend):**
- `provider_runtime.py`: `has_provider()` helper; `get_provider` now raises an actionable
  error ("select a configured provider or load the browser model in Settings").
- `main.py`: pre-flight provider validation before orchestrate; fallback engine skips
  browser-only providers (they can never answer server-side) and emits one clean error.
- `translate.py`: translation routes skip browser-only providers entirely.

**Fixes (frontend):**
- `app/page.tsx`: browser runs no longer send `browser-webllm` to the server; repeated
  error text is deduplicated before display.
- `app/components/SettingsDrawer.tsx`: warning shown when the fallback route is set to
  the browser provider.

**Tests:** `python_backend/tests/test_provider_config.py` (7 new: has_provider, actionable
error, pre-flight rejection, fallback skips browser provider, single clean error,
translation route skipping). Full suite: **76 passed**, `tsc` clean.

## Pending issues / next steps
- Custom Deno adapter editor: detection/probe wired in backend; Deno execution path not yet fully exercised.
## Session: model-discovery JSON-500 fix ("Unexpected token 'I', Internal S...")

**Reported bug:** `Cannot discover provider models: Unexpected token 'I', "Internal S"...
 is not valid JSON` when clicking Discover on a provider.

**Root cause (2 layers):**
1. `provider_runtime.py` had a silent structural bug: everything after `_profile`
   (`_headers`, `_ollama_stream`, `_openai_stream`, `_parse_openai_line`,
   `_openai_payload_to_event`, `_script_call`) was indented INSIDE the module-level
   function `provider_unconfigured_message` — so `ProviderRuntime` had no `_headers`
   and no streaming methods. Every chat request and every model discovery raised
   `AttributeError: 'ProviderRuntime' object has no attribute '_headers'`.
2. That bare exception escaped the endpoint (only `ProviderRuntimeError` was caught)
   → Starlette answered plain-text `Internal Server Error` → the Next.js proxy's
   `response.json()` failed with the cryptic "Unexpected token 'I'..." message.

**Fixes:**
- `provider_runtime.py`: rewrote the file with correct class structure; all methods
  are real `ProviderRuntime` members again. URL building in `list_models` moved
  inside the try/except so an empty/malformed `base_url` becomes a user-safe
  `ProviderRuntimeError` instead of a bare `ValueError`.
- `main.py`: `/providers/{id}/models` and `/models` now catch broad `Exception` as a
  last-resort guard and always answer structured JSON (502/503) — never plain text.
- `app/api/providers/backend-json.ts` (new): shared helper that parses backend bodies
  defensively; `[providerId]/models`, `detect`, and `providers` (GET/POST) routes use
  it, so any non-JSON backend body surfaces as a readable, copyable error.

**Tests:** `python_backend/tests/test_provider_models.py` (7 new): empty/invalid URL
→ ProviderRuntimeError, missing profile, plain-text-500 provider detail passthrough
(monkeypatched client), endpoint returns JSON 502 for empty URL / unknown provider,
and the "never plain-text 500" guard (generic RuntimeError → JSON 502). Full suite:
**83 passed**, `tsc` clean, backend imports verified.

## Pending issues / next steps
- Browser (WebLLM) mode has no web-search delegation yet (browser agents state this limitation in UI).
- Ollama is not present in the Freebuff sandbox; expected 502 on `/providers/ollama/models` until the
  user points the app at a real Ollama host (env `OLLAMA_BASE_URL`).
