from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

ChatFn = Callable[[str, str, list[dict[str, str]]], Awaitable[str]]

MAX_TOPIC_CHARS = 220
MAX_SPEAKERS = 3
SPEECH_CHAR_LIMIT = 900
SYNTHESIS_CHAR_LIMIT = 1800

SCHEMA = {
    "type": "object",
    "required": ["topic"],
    "additionalProperties": False,
    "properties": {
        "topic": {"type": "string", "minLength": 3, "maxLength": MAX_TOPIC_CHARS},
        "speakers": {"type": "integer", "minimum": 2, "maximum": MAX_SPEAKERS},
    },
}

PERSPECTIVES = [
    ("The Advocate", "argues the strongest case FOR the position, with concrete reasons"),
    ("The Critic", "attacks weak points, names risks, flaws and failure modes"),
    ("The Pragmatist", "focuses on what actually works in practice, trade-offs and effort"),
]

DEBATE_SYSTEM_PROMPT = (
    "You simulate a short structured debate between distinct subagent perspectives on one topic. "
    "Each speaks once, in character, then you deliver a neutral synthesis. "
    f"Keep every speech under {SPEECH_CHAR_LIMIT} characters, the synthesis under {SYNTHESIS_CHAR_LIMIT}. "
    "Use the exact format:\n"
    "[<Role>] <speech>\n"
    "[<Role>] <speech>\n"
    "[<Role>] <speech>\n"
    "[Synthesis] <balanced conclusion naming the strongest points and the open questions>."
)


def _clamp(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_debate(raw: str, speakers: int) -> dict[str, Any]:
    """Split the model output into speeches + synthesis; tolerant to missing roles."""
    speeches: list[dict[str, str]] = []
    synthesis = ""
    role_pattern = re.compile(r"^\s*\[([^\]\n]{2,40})\]\s*(.+)$", re.DOTALL)
    synthesis_split = re.split(r"\[\s*Synthesis\s*\]", raw, maxsplit=1, flags=re.IGNORECASE)
    debate_body = synthesis_split[0]
    if len(synthesis_split) > 1:
        synthesis = synthesis_split[1]

    current_role = ""
    current_body: list[str] = []
    for line in debate_body.splitlines():
        match = role_pattern.match(line)
        if match:
            if current_role and current_body:
                speeches.append({"role": current_role, "speech": _clamp(" ".join(current_body), SPEECH_CHAR_LIMIT)})
            current_role = match.group(1).strip()
            current_body = [match.group(2).strip()]
        elif current_role and line.strip():
            current_body.append(line.strip())
    if current_role and current_body:
        speeches.append({"role": current_role, "speech": _clamp(" ".join(current_body), SPEECH_CHAR_LIMIT)})

    if not speeches:
        # Model ignored the format - fall back to perspectives with the raw text as one speech.
        speeches = [
            {"role": PERSPECTIVES[index][0], "speech": _clamp(raw, SPEECH_CHAR_LIMIT)}
            for index in range(min(speakers, MAX_SPEAKERS))
        ]
    if synthesis:
        synthesis = _clamp(synthesis, SYNTHESIS_CHAR_LIMIT)
    return {"speeches": speeches[:MAX_SPEAKERS], "synthesis": synthesis}


class DebateSkill:
    """Consent-gated skill: 2-3 subagent perspectives debate a topic on the local model."""

    name = "discuss"
    description = (
        "Commission a panel of 2-3 local subagent perspectives (Advocate, Critic, Pragmatist) that debate "
        "a topic and return their arguments plus a neutral synthesis. Use for multi-angle analysis, "
        "brainstorming or decisions with trade-offs."
    )
    parameters = SCHEMA

    def __init__(self, chat: ChatFn) -> None:
        self._chat = chat

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        topic = str(arguments.get("topic", "")).strip()
        speakers = int(arguments.get("speakers") or 3)
        speakers = max(2, min(MAX_SPEAKERS, speakers))
        if not topic:
            return {"ok": False, "error": "The debate topic was empty."}
        roles = [PERSPECTIVES[index][0] for index in range(speakers)]
        user_prompt = (
            f"Topic: {topic}\n\n"
            f"Debate it with exactly {speakers} speeches in this order: {', '.join(roles)}. "
            "Then one [Synthesis]. Follow the system format exactly."
        )
        try:
            raw = await self._chat(DEBATE_SYSTEM_PROMPT, user_prompt, [])
        except Exception as exc:  # noqa: BLE001 - surfaced to the model, never crash the loop
            return {"ok": False, "error": f"The debate subagents failed locally: {exc}"}
        parsed = parse_debate(raw, speakers)
        return {
            "ok": True,
            "topic": topic[:MAX_TOPIC_CHARS],
            "speakers": speakers,
            "speeches": parsed["speeches"],
            "synthesis": parsed["synthesis"],
        }
