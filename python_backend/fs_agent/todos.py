"""Mandatory todo management for FS-agent runs.

Complex tasks MUST be tracked as todos; the runner refuses to finish while
todos are still open. Todos are streamed to the UI so the user can audit them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

COMPLEXITY_HINTS = (
    "project", "team", "app", "build", "website", "server", "api", "multi",
    "several", "each", "all files", "structure", "refactor", "migrate", "scaffold",
)

MIN_MESSAGE_CHARS_FOR_TODOS = 400


@dataclass
class Todo:
    id: str
    task: str
    completed: bool = False
    origin: str = "model"  # model | system
    # Coordination thread between the root agent and a commissioned subagent:
    # [{"from": "root" | "subagent", "text": str}]
    messages: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "completed": self.completed,
            "origin": self.origin,
            "messages": [dict(item) for item in self.messages],
        }


@dataclass
class TodoBoard:
    items: list[Todo] = field(default_factory=list)
    _seq: int = 0

    def looks_complex(self, message: str) -> bool:
        lowered = message.lower()
        if len(message) >= MIN_MESSAGE_CHARS_FOR_TODOS:
            return True
        return sum(1 for hint in COMPLEXITY_HINTS if hint in lowered) >= 2

    def add(self, task: str, origin: str = "model") -> Todo | None:
        task = task.strip()[:240]
        if not task:
            return None
        self._seq += 1
        todo = Todo(id=f"todo-{self._seq}", task=task, origin=origin)
        self.items.append(todo)
        return todo

    def complete(self, todo_id: str) -> bool:
        for todo in self.items:
            if todo.id == todo_id:
                todo.completed = True
                return True
        return False

    def get(self, todo_id: str) -> Todo | None:
        for todo in self.items:
            if todo.id == todo_id:
                return todo
        return None

    def add_message(self, todo_id: str, sender: str, text: str) -> Todo | None:
        """Append a coordination message to a todo; returns the todo or None if unknown."""
        text = text.strip()[:2000]
        if not text:
            return None
        todo = self.get(todo_id)
        if todo is None:
            return None
        todo.messages.append({"from": sender, "text": text})
        return todo

    def set_all(self, tasks: list[str]) -> int:
        created = 0
        for task in tasks:
            if self.add(task) is not None:
                created += 1
        return created

    def open_items(self) -> list[Todo]:
        return [todo for todo in self.items if not todo.completed]

    def as_list(self) -> list[dict[str, Any]]:
        return [todo.as_dict() for todo in self.items]

    def summary(self) -> str:
        done = sum(1 for todo in self.items if todo.completed)
        return f"{done}/{len(self.items)} todos completed"
