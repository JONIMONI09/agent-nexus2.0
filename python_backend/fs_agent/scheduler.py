"""Task scheduler for FS-agent runs: the root agent can schedule delayed tasks.

Scheduling is REAL waiting inside the run (bounded by a per-run budget so a
model that schedules endlessly can never hang the run). Due tasks are delivered
back to the model as tool results it can act on.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

MAX_DELAY_SECONDS = 300
MAX_TASKS = 8
POLL_INTERVAL_SECONDS = 0.25
# Total wall-clock a single run may spend waiting for scheduled tasks. Keeps a
# schedule-happy model from stalling the run forever.
MAX_WAIT_BUDGET_SECONDS = 90


class ScheduleError(ValueError):
    """Raised for invalid scheduling requests; the text is fed back to the model."""


@dataclass
class ScheduledTask:
    id: str
    description: str
    delay_seconds: float
    due_at: float  # monotonic deadline

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "delay_seconds": round(self.delay_seconds, 1),
            "due_in": round(max(0.0, self.due_at - time.monotonic()), 1),
        }


@dataclass
class Scheduler:
    tasks: list[ScheduledTask] = field(default_factory=list)
    waited_seconds: float = 0.0
    _seq: int = 0

    def schedule(self, description: str, delay_seconds: float) -> ScheduledTask:
        description = description.strip()[:240]
        if not description:
            raise ScheduleError("description must not be empty.")
        if len(self.tasks) >= MAX_TASKS:
            raise ScheduleError(f"schedule is full ({MAX_TASKS} tasks); use wait_for_schedule to collect due ones first.")
        try:
            delay = float(delay_seconds)
        except (TypeError, ValueError) as exc:
            raise ScheduleError("delay_seconds must be a number.") from exc
        if delay <= 0:
            raise ScheduleError("delay_seconds must be > 0 (run wait_for_schedule immediately for 'now' work).")
        if delay > MAX_DELAY_SECONDS:
            raise ScheduleError(f"delay_seconds is capped at {MAX_DELAY_SECONDS}s in a run.")
        self._seq += 1
        task = ScheduledTask(
            id=f"task-{self._seq}",
            description=description,
            delay_seconds=delay,
            due_at=time.monotonic() + delay,
        )
        self.tasks.append(task)
        return task

    def pending(self) -> list[ScheduledTask]:
        return list(self.tasks)

    def collect_due(self) -> list[ScheduledTask]:
        """Remove and return all tasks whose deadline has passed."""
        now = time.monotonic()
        due = [task for task in self.tasks if task.due_at <= now]
        self.tasks = [task for task in self.tasks if task.due_at > now]
        return due

    def has_pending(self) -> bool:
        return bool(self.tasks)

    async def wait_for_due(self) -> list[ScheduledTask]:
        """Await due tasks with REAL waiting, bounded by the per-run budget."""
        while True:
            due = self.collect_due()
            if due:
                return due
            if self.waited_seconds >= MAX_WAIT_BUDGET_SECONDS:
                return []
            remaining_budget = MAX_WAIT_BUDGET_SECONDS - self.waited_seconds
            await asyncio.sleep(min(POLL_INTERVAL_SECONDS, remaining_budget))
            self.waited_seconds = min(MAX_WAIT_BUDGET_SECONDS, self.waited_seconds + POLL_INTERVAL_SECONDS)

    def summary(self) -> str:
        if not self.tasks:
            return "no scheduled tasks"
        return "; ".join(f"{task.id}: {task.description} (due in {round(max(0.0, task.due_at - time.monotonic()), 1)}s)" for task in self.tasks)
