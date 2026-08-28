---
name: context-compression
description: Summarize/compress long conversations, agent traces or context windows without losing decisions, constraints or open bugs. Use when context grows huge, before continuing long tasks, or when condensing the sub-agent trace.
---

# Context Compression — lose noise, keep truth

## What must survive compression (in priority order)
1. **Decisions made** and why (e.g. "browser providers never go to FastAPI").
2. **Constraints** (free/local-only, consent-gated tools, portrait-first, no Ollama in sandbox).
3. **Open bugs / pending steps** with their exact repro state.
4. **File map**: which files own which behavior.
5. Recent user instructions, verbatim where short.

## What may be dropped
- Verbose tool output, full file dumps, long logs (keep one-line outcomes).
- Superseded attempts: keep the final approach + one line on why earlier ones failed.

## Format
Condense to:
```text
GOAL: …
DECISIONS: numbered, with reason
CONSTRAINTS: bullet list
FILES: path → responsibility
OPEN: bugs/steps with state
NEXT: single concrete next action
```

## In-product rule
The app's own context handling (`python_backend/context.py`, trace panel) follows the same law: older turns/traces may be summarized, but tool consent decisions, delegation results and error events are never silently dropped — users must be able to expand and see them.
