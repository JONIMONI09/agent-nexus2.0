from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"

FILE_NAMES = {"learn": "learn.md", "rules": "Rules.md", "agent": "Agent.md"}

DEFAULT_CONTENT = {
    "learn": (
        "# Learning journal\n\n"
        "Insights the AI extracted from your conversations. While Learning is enabled, the newest "
        "entries are injected into every agent run so the AI improves over time.\n"
    ),
    "rules": (
        "# Standing rules\n\n"
        "These rules are injected into every agent run while Learning is enabled. "
        "Edit them freely - the AI obeys them.\n\n"
        "- Answer in the language the user writes in.\n"
        "- Never invent sources, tool results, or capabilities.\n"
        "- Never run a tool without explicit user consent (the consent modal enforces this).\n"
    ),
    "agent": (
        "# Agent profile\n\n"
        "Persona and thinking profile for the AI, injected while Learning is enabled.\n\n"
        "## Identity\n"
        "A precise, honest, local research assistant. You improve over time by following the "
        "learning journal and the standing rules.\n"
    ),
}

MAX_LESSONS_PER_RUN = 5
MAX_RULES_PER_RUN = 3
MAX_LEARN_BODY_LINES = 200
MAX_MEMORY_PROMPT_CHARS = 2400

_RULE_MARKERS = ("always", "never", "don't", "do not", "stop ", "instead", "from now on", "in future", "in the future", "prefer", "act as")
_LESSON_MARKERS = _RULE_MARKERS + ("be more", "be less", "shorter", "longer", "simpler", "wrong", "actually", "i meant", "i want", "i like", "i don't like", "no, ")


@dataclass
class LearningOutcome:
    lessons: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    added_lessons: int = 0
    added_rules: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "lessons": self.lessons,
            "rules": self.rules,
            "added_lessons": self.added_lessons,
            "added_rules": self.added_rules,
        }


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [part.strip() for part in parts if part.strip()]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).lstrip("- ").strip()


def _strip_bullet_stamp(line: str) -> str:
    """Normalize a stored bullet to its bare text (drop marker and timestamp) for dedupe."""
    text = re.sub(r"^\s*-\s*\[[^\]]*\]\s*", "", line)
    return _normalize(text)


class MemoryStore:
    """Reads and writes the three learning files (learn.md, Rules.md, Agent.md)."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or MEMORY_DIR
        self._ensure()

    def _ensure(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        for key, filename in FILE_NAMES.items():
            path = self.directory / filename
            if not path.exists():
                path.write_text(DEFAULT_CONTENT[key], encoding="utf-8")

    def path(self, name: str) -> Path:
        if name not in FILE_NAMES:
            raise ValueError(f"Unknown memory file '{name}'.")
        return self.directory / FILE_NAMES[name]

    def read(self, name: str) -> str:
        return self.path(name).read_text(encoding="utf-8")

    def write(self, name: str, content: str) -> None:
        self.path(name).write_text(content, encoding="utf-8")

    def reset(self, name: str) -> None:
        self.write(name, DEFAULT_CONTENT[name])


def extract_lessons(user_message: str, assistant_answer: str = "") -> LearningOutcome:
    """Deterministic lesson extraction from the user's own words (no model call)."""
    lessons: list[str] = []
    rules: list[str] = []
    seen: set[str] = set()
    for sentence in _sentences(user_message):
        lowered = sentence.lower()
        if not 8 <= len(sentence) <= 300:
            continue
        if not any(marker in lowered for marker in _LESSON_MARKERS):
            continue
        normalized = _normalize(sentence)
        if normalized in seen:
            continue
        seen.add(normalized)
        lessons.append(sentence[:300])
        if any(marker in lowered for marker in ("always", "never", "from now on", "in future", "in the future", "don't", "do not")) and len(rules) < MAX_RULES_PER_RUN:
            rules.append(sentence[:300])
        if len(lessons) >= MAX_LESSONS_PER_RUN:
            break
    return LearningOutcome(lessons=lessons, rules=rules)


def _append_bullets(store: MemoryStore, name: str, lines: list[str], max_body_lines: int | None = None) -> int:
    if not lines:
        return 0
    existing = store.read(name)
    existing_normalized = {_strip_bullet_stamp(line) for line in existing.splitlines() if line.strip().startswith("-")}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    added: list[str] = []
    for line in lines:
        if _normalize(line) in existing_normalized:
            continue
        added.append(f"- [{stamp}] {line}")
    if not added:
        return 0
    updated = existing.rstrip("\n") + "\n" + "\n".join(added) + "\n"
    if max_body_lines is not None:
        all_lines = updated.splitlines()
        headers = [line for line in all_lines if line.startswith("#")]
        body = [line for line in all_lines if not line.startswith("#")]
        updated = "\n".join(headers + body[-max_body_lines:]) + "\n"
    store.write(name, updated)
    return len(added)


def record_lessons(store: MemoryStore, user_message: str, assistant_answer: str = "") -> LearningOutcome:
    """Extract lessons from a finished turn and persist them. Idempotent per content."""
    outcome = extract_lessons(user_message, assistant_answer)
    outcome.added_lessons = _append_bullets(store, "learn", outcome.lessons, max_body_lines=MAX_LEARN_BODY_LINES)
    outcome.added_rules = _append_bullets(store, "rules", outcome.rules)
    return outcome


def prompt_block(store: MemoryStore) -> str:
    """Build the memory block injected into system prompts while Learning is enabled."""
    parts: list[str] = []
    rules = store.read("rules").strip()
    agent = store.read("agent").strip()
    learn_lines = [line.strip() for line in store.read("learn").splitlines() if line.strip().startswith("-")][-12:]
    if rules:
        parts.append(f"Standing rules from the user's Rules.md (obey them):\n{rules}")
    if agent:
        parts.append(f"Agent profile from the user's Agent.md (follow this persona):\n{agent}")
    if learn_lines:
        parts.append("Recent lessons from the learning journal (learn.md) - apply them:\n" + "\n".join(learn_lines))
    if not parts:
        return ""
    return "\n\n".join(parts)[:MAX_MEMORY_PROMPT_CHARS]
