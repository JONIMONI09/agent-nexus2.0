---
name: mobile-first-ui
description: Portrait-first UI laws for this app (Android Chrome + desktop) — sticky bottom chat bar, drawers, glassmorphism, no text overflow, hover stability. Use when touching layout, styling, or any visible component.
---

# Mobile-First UI — portrait is the primary target

## Layout laws
- Portrait phone first; desktop is the adaptation, not the other way round.
- Sticky bottom input bar; messages scroll above it with smooth autoscroll to the newest.
- All settings live in the off-canvas drawer behind the animated hamburger; drawers must never shift page content on hover.
- Past bug: hover/typing moved the sidebar — overlays must be position-fixed, out of layout flow, and hover states must never trigger layout or translate containers.

## Text containment (zero tolerance)
No text may escape its container at any width. For every message/panel element:
- `min-w-0` on flex children so truncation works;
- `break-words` / `overflow-wrap:anywhere` on free text;
- `truncate` or line-clamp for labels, never raw overflow;
- code blocks scroll horizontally inside their own box;
- test at 360 px width (small Android) AND desktop before claiming done.

## Visual system
- Dark glassmorphism: translucent panels + `backdrop-blur`, thin borders, soft glow accents; consistent Tailwind tokens from `app/globals.css`.
- Framer Motion for micro-interactions (message entry, drawer, consent modal, agent pulses). Motion must not fight scrolling.
- Agent states animate visibly: "Agent A is browsing…", "Agent B is drafting…", thinking streams in `SubAgentPanel`.
- Consent modal is high-priority, unmistakable, touch-friendly buttons (Allow / Deny).
- Valid Tailwind classes only; no invented utilities; keep the global stylesheet imports intact.

## Overlay & progress laws (added after real bugs)
- **Floating toasts must sit ABOVE every overlay**: app drawers/panels are z-40; global toasts/indicators use z-[60]. Bug precedent: the model-load toast shared z-40 with the settings drawer (which is full-height on the left) and was invisible exactly while loading.
- **Long-running operations show the EXACT live value** (percent number, not just a bar) in BOTH places: the in-panel card (e.g. badge "Loading 42%") and the global toast.
- **Every long-running operation gets a visible Stop** — model loads included. If the underlying API cannot abort (WebLLM engine creation), detach on completion: cancel flag → `engine.unload()` → honest "stopped" state. A UI that cannot be stopped reads as "frozen".
- **Never freeze the input**: Stop must be reachable without closing/reopening any panel (the composer's ■ button and the toast's stop both cancel the active work).
