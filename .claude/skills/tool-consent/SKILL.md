---
name: tool-consent
description: Rules for consent-gated tool execution. Every tool call (web_search, etc.) must pause and ask the user Allow/Deny before running. Use when adding or modifying tools, consent flow, or tool validation.
---

# Tool Consent — privacy-first execution (never silent)

## Hard laws (never break)
1. Tools NEVER execute silently in the background. No exceptions.
2. Execution only continues after an explicit user click: **Allow** or **Deny**.
3. A **Deny** is not an error: it becomes an explicit tool result the agent must acknowledge and answer without live data.
4. Invalid calls are rejected BEFORE the consent modal (no modal for garbage).

## Flow that must stay intact
```text
model emits tool call (JSON)
  → validate name + args against the skill registry (python_backend/tools.py)
      invalid → tool_error event → feed error text back to the model → self-correction (max MAX_TOOL_ROUNDS)
      valid   → tool_consent_required event → UI pauses (ToolConsentModal)
  → user Allow  → run skill (python_backend/skills/web_search.py) → tool_result event
  → user Deny   → tool result "denied by user" → agent answers without live evidence, says so honestly
```

## When changing anything here
- Keep every decision visible in the Sub-Agent trace (`SubAgentPanel`, `SubAgentDelegation`).
- Every call gets an ID; SSE events: `tool_call_requested`, `tool_consent_required`, `tool_result`, `tool_error`, `tool_call_rejected`.
- Tests live in `python_backend/tests/test_consent_pipeline.py` and `test_orchestration.py` — extend them, never delete the coverage for unknown-skill and invalid-args rejection.
- The browser path (`app/lib/browser-agent.ts`) has no web access by design: it must state honestly that live search is unavailable, never fake results.
