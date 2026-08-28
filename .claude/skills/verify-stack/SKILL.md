---
name: verify-stack
description: Mandatory verification discipline before claiming anything works — typecheck, Python tests, preview readiness, real output only. Use before finishing ANY change, and whenever you are about to say "done" or "fixed".
---

# Verify Stack — no false claims, ever

## The rule
Never claim code compiles, tests pass, or the preview works unless you ran the command IN THIS TURN and can quote its real output. "Should work" is forbidden.

## Standard gate (run at the end of every change)
```bash
bun run typecheck        # tsc -b --noEmit
bun run test:python      # pytest via scripts/python.sh
freebuff-preview status  # must be Ready, HTTP 200
```
If any fails → fix → rerun until green. A failing gate means the task is NOT done.

## After backend changes
`bun run test:python` is the gate; extend `python_backend/tests/` for new behavior (consent, orchestration, schemas, search skill) instead of only relying on old coverage.

## Preview commands (this workspace)
```bash
freebuff-preview start | restart | status | logs
```
- Diagnose from `logs`, never from imagination.
- `freebuff-preview: not found` in a restored sandbox = environment loss; report it, do not fake a run.
- Ollama 502 in sandbox logs is expected (no Ollama here) — everything else must be clean.

## Test the user's ACTUAL path (added after real bugs)
- Verify features through the setup the user really runs, not only the ideal one. Bug precedent: translation was "tested" server-side while the user ran browser-only WebLLM — the feature silently no-op'd for them. Ask: which providers does this user have alive, and does the feature work with exactly those?
- For every "X doesn't work" report: first reproduce the user's configuration (providers, browser mode, flags), then trace the code path end-to-end before changing anything.

## Honesty annex
- Missing env/keys, flaky file tools, or a wiped sandbox get REPORTED, not papered over.
- If verification was impossible, say exactly what could not be checked and why.
- Update `sessions.md` with what was verified and what remains open.
