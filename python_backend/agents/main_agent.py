from __future__ import annotations

from typing import Any

from ..types import HistoryMessage


MAIN_AGENT_SYSTEM_PROMPT = """You are the main AI assistant in a private local workspace.

Answer the user's request directly and completely. When the request needs fresh, current web evidence, delegate to the web_search subagent: call web_search with one focused query. The subagent's result is delivered back to you as a tool message. Wait for it, then incorporate the delivered evidence into your final answer. Do not claim a search ran if no result was delivered, never invent sources or facts, and cite supplied URLs only when a search actually returned them.

For questions with real trade-offs, competing approaches, or that explicitly ask for debate or multiple perspectives, delegate to the discuss subagent: call discuss with a focused topic (and optional speaker count 2-3). The panel's speeches and synthesis are delivered back as a tool message; weave the strongest points into your answer and say the perspectives came from your local debate panel.

If no fresh evidence or debate is needed, answer immediately without calling any tool. Keep the answer self-contained and readable, using short headings or bullets where they help scanning."""


def build_messages(
    history: list[HistoryMessage],
    user_message: str,
    custom_prompt: str = "",
    memory_block: str = "",
    thinking_hint: str = "",
) -> list[dict[str, Any]]:
    system = MAIN_AGENT_SYSTEM_PROMPT
    extras = ""
    if thinking_hint.strip():
        extras += f"\n\nThinking profile for this run:\n{thinking_hint.strip()}"
    if memory_block.strip():
        extras += f"\n\n{memory_block.strip()}"
    if custom_prompt.strip():
        extras += f"\n\nAdditional workspace instruction:\n{custom_prompt.strip()}"
    return [
        {"role": "system", "content": system + extras},
        *[_history_item(item) for item in history],
        {"role": "user", "content": user_message},
    ]


def _history_item(item: HistoryMessage) -> dict[str, str]:
    return {"role": item.role, "content": item.content}
