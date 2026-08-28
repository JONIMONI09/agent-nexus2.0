---
name: web-research
description: Forced web-research protocol before architecture, library or model decisions. Zero guessed facts — verify versions, APIs and model IDs in real sources. Use before adopting any dependency, endpoint or model, and whenever uncertain.
---

# Web Research — anti-hallucination protocol

## When research is MANDATORY
- Before adding any library/dependency or writing code against an unfamiliar API.
- Before putting model IDs in catalogs (WebLLM prebuilt list, Ollama registry) — check the actual current list.
- Before claiming what a tool/framework supports (tool-calling? streaming? WebGPU on Android Chrome?).
- When the user asks "what's possible" — answer from sources, not memory.

## Method
1. Search the web with precise, current queries (include the year when freshness matters).
2. Prefer primary sources: official docs, GitHub repos/issues, changelogs, package registries.
3. Cross-check anything load-bearing in a second source.
4. State findings with the source; mark anything unverified as UNVERIFIED — never present a guess as fact.

## Repo-specific checks this skill has caught
- WebLLM model IDs that look plausible but don't exist in the installed prebuilt list → verify against the installed `@mlc-ai/web-llm` package before adding.
- Ollama vs OpenAI-compatible endpoint shapes (`/api/chat` vs `/v1/chat/completions`) — never mix them.
- Self-correction loops for invalid tool calls — confirmed as the standard pattern via research before implementing.

## Anti-patterns (forbidden)
- Inventing endpoints, flags or "2026 best practices" from memory.
- Placeholder code, simulated tools, fake readiness states.
- Recommending paid/keyed services when the constraint is free & local.
