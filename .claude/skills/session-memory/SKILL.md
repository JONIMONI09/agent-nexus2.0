---
name: session-memory
description: Keeps sessions.md (project memory) truthful and current — files created, decisions, verified state, open issues. Use after completing any meaningful change, and when resuming work after an interruption or sandbox restore.
---

# Session Memory — continuous project tracking

## The file
`sessions.md` at repo root is the build journal required by this project's mission. It is the single source of truth for "where are we".

## After every meaningful change, append/update:
- **What changed**: files created/edited (paths), features added/fixed.
- **Decisions**: structural choices + the reason (which research/sources backed them).
- **Verified state**: what was actually run and passed (typecheck, pytest count, preview status) — copied from real command output, never estimated.
- **Open issues**: pending bugs, known limitations (e.g. Ollama absent in sandbox), next steps.

## On resume/interruption
1. Read `sessions.md` first, then inspect actual files — memory can be stale after a sandbox restore.
2. Continue from the recorded NEXT step; never redo verified work.
3. Correct the file if reality diverged (sandbox wiped, files restored differently).

## Laws
- Append, don't rewrite history — prior entries are the audit trail.
- No optimistic claims: only record states that were verified.
- Keep it compact: tables/short bullets, newest section first or clearly dated.
