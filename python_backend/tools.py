from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol


class Skill(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class _PendingApproval:
    run_id: str
    event: asyncio.Event
    approved: bool | None = None


class ConsentBroker:
    """Keeps a pending decision in memory until the browser explicitly resolves it."""

    def __init__(self) -> None:
        self._pending: dict[str, _PendingApproval] = {}

    def create(self, call_id: str, run_id: str) -> None:
        self._pending[call_id] = _PendingApproval(run_id=run_id, event=asyncio.Event())

    async def wait(self, call_id: str, timeout_seconds: float) -> tuple[bool, str]:
        pending = self._pending.get(call_id)
        if pending is None:
            return False, "missing_request"
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=timeout_seconds)
            if pending.approved:
                return True, "approved"
            return False, "denied"
        except asyncio.TimeoutError:
            return False, "expired"
        finally:
            self._pending.pop(call_id, None)

    def resolve(self, call_id: str, approved: bool) -> bool:
        pending = self._pending.get(call_id)
        if pending is None:
            return False
        pending.approved = approved
        pending.event.set()
        return True

    def cancel_run(self, run_id: str) -> None:
        for call_id, pending in list(self._pending.items()):
            if pending.run_id == run_id:
                pending.approved = False
                pending.event.set()
                self._pending.pop(call_id, None)


class ToolRegistry:
    def __init__(self, skills: list[Skill] | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in skills or []:
            self.register(skill)

    def register(self, skill: Skill) -> None:
        if not skill.name or skill.name in self._skills:
            raise ValueError(f"Skill name must be unique: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": skill.parameters,
                },
            }
            for skill in self._skills.values()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        skill = self.get(name)
        if skill is None:
            return {"ok": False, "error": f"Skill '{name}' is not registered."}
        return await skill.execute(arguments)
