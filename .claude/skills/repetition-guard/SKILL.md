---
name: repetition-guard
description: Detects and stops degenerate LLM output (repetition loops from tiny models), applies token caps and mini-model prompting. Use when a model output loops, rambles, or the user reports "the AI is spinning out".
---

# Repetition Guard — stopping model meltdown

## Known failure signature
Tiny browser models (360M–0.5B) collapse on complex prompts into endless fragments:
`"...latest things online, I'vea,///latest things online..."`. This is model degeneration, not an app bug — but the app MUST contain it.

## Mandatory safeguards (keep them wired)
1. **Runtime repetition detection** in `app/lib/browser-agent.ts`: watch the stream; low character diversity or the same ≥24-char fragment repeating ≥3× → abort generation immediately and emit a visible system notice ("the browser model began repeating itself…").
2. **Token cap**: every generation capped (≈384–640 tokens). An infinite loop must be physically impossible.
3. **Mini-model prompt mode**: for 360M/0.5B class models use an ultra-short system prompt ("Answer briefly. Never repeat yourself.") and low temperature (≈0.1). Long instruction blocks trigger tangling.
4. **Settings warning**: selecting a tiny model shows an amber hint recommending Qwen 1.5B / Llama 3.2 3B for real tasks.

## When users report looping
- Identify which model + provider produced it (check trace/panel).
- Confirm the caps above are active on that path (browser AND server).
- Fix at the guard layer — never by silently truncating user-visible text elsewhere.
- Recommend the right model for the job; server providers + web_search are the correct path for live-data questions.
