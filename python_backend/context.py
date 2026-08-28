from __future__ import annotations

from dataclasses import dataclass

from .types import HistoryMessage


@dataclass(frozen=True)
class PackedContext:
    messages: list[dict[str, str]]
    compacted: bool
    dropped_count: int
    retained_chars: int


def pack_history(history: list[HistoryMessage], max_chars: int) -> PackedContext:
    """Keep the newest complete turns that fit, preserving an explicit compacted marker."""
    if max_chars < 800:
        max_chars = 800

    normalized = [{"role": item.role, "content": item.content.strip()} for item in history if item.content.strip()]
    total_chars = sum(len(item["content"]) for item in normalized)
    if total_chars <= max_chars:
        return PackedContext(normalized, False, 0, total_chars)

    marker_budget = min(1200, max(220, max_chars // 6))
    message_budget = max(100, max_chars - marker_budget)
    retained: list[dict[str, str]] = []
    used = 0
    for item in reversed(normalized):
        item_size = len(item["content"])
        if retained and used + item_size > message_budget:
            break
        if not retained and item_size > message_budget:
            item = {**item, "content": item["content"][-message_budget:]}
            item_size = len(item["content"])
        retained.append(item)
        used += item_size

    retained.reverse()
    dropped_count = len(normalized) - len(retained)
    dropped = normalized[:dropped_count]
    marker_base = f"[Earlier context compacted: retained the newest {len(retained)} messages from {len(normalized)}.]"
    summary_budget = max(0, marker_budget - len(marker_base) - 1)
    summary_parts: list[str] = []
    summary_size = 0
    for item in dropped:
        excerpt = " ".join(item["content"].split())
        if len(excerpt) > 180:
            excerpt = f"{excerpt[:177]}..."
        part = f"{item['role']}: {excerpt}"
        part_size = len(part) + (1 if summary_parts else 0)
        if summary_size + part_size > summary_budget:
            break
        summary_parts.append(part)
        summary_size += part_size
    marker_content = marker_base
    if summary_parts:
        marker_content += "\n" + "\n".join(summary_parts)
    marker = {"role": "assistant", "content": marker_content}
    packed = [marker, *retained]
    return PackedContext(packed, True, dropped_count, sum(len(item["content"]) for item in packed))
