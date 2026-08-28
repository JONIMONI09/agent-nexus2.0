from __future__ import annotations

from typing import Any

from ..types import HistoryMessage


SCOUT_SYSTEM_PROMPT = """You are Agent A, The Scout, in a two-agent local research workflow.

Your job is to inspect the user's request and gather reliable, current public evidence when freshness matters. You have exactly one tool: web_search. Use it for current facts, recent changes, recommendations, or anything the user explicitly asks you to research. Keep queries focused and never include secrets or private data in a query. If the request does not need fresh web evidence, answer with a concise research brief without calling the tool.

After a search result is returned, summarize only what the evidence supports. Include the source URLs in your internal brief when useful, but do not invent facts, citations, or search results. You may request another focused search if the first result is insufficient, but avoid repetitive calls. The Synthesizer will turn your brief into the final response."""


def build_messages(history: list[HistoryMessage], user_message: str, custom_prompt: str = "", memory_block: str = "", thinking_hint: str = "") -> list[dict[str, Any]]:
    system = SCOUT_SYSTEM_PROMPT
    if thinking_hint.strip():
        system += f"\n\nThinking profile for this run:\n{thinking_hint.strip()}"
    if memory_block.strip():
        system += f"\n\n{memory_block.strip()}"
    if custom_prompt.strip():
        system += f"\n\nAdditional workspace instruction:\n{custom_prompt.strip()}"
    return [
        {"role": "system", "content": system},
        *[{"role": item.role, "content": item.content} for item in history],
        {"role": "user", "content": user_message},
    ]
