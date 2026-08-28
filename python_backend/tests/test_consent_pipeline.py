from __future__ import annotations

import asyncio

from python_backend import main
from python_backend.tools import ConsentBroker, ToolRegistry
from python_backend.types import OrchestrateRequest


class FakeSearchSkill:
    name = "web_search"
    description = "Fake search used only for consent pipeline tests."
    parameters = {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}

    def __init__(self) -> None:
        self.executed: list[dict[str, object]] = []

    async def execute(self, arguments: dict[str, object]) -> dict[str, object]:
        self.executed.append(arguments)
        return {
            "ok": True,
            "results": [{"title": "Test source", "url": "https://example.com", "snippet": "Evidence"}],
        }


def test_scout_waits_for_explicit_consent_before_skill_execution(monkeypatch) -> None:
    async def run() -> tuple[main.ScoutResult, list[tuple[str, dict[str, object]]], list[dict[str, object]]]:
        broker = ConsentBroker()
        skill = FakeSearchSkill()
        monkeypatch.setattr(main, "consent_broker", broker)
        monkeypatch.setattr(main, "skills", ToolRegistry([skill]))

        turns = [
            main.Turn(
                tool_calls=[
                    {"index": 0, "name": "web_search", "arguments": {"query": "consent test"}}
                ],
                model="scout",
            ),
            main.Turn(content="Evidence brief", model="scout"),
        ]
        events: list[tuple[str, dict[str, object]]] = []

        async def fake_collect_with_fallback(*args, **kwargs) -> main.Turn:
            return turns.pop(0)

        async def emit(event_type: str, **payload: object) -> None:
            events.append((event_type, payload))

        monkeypatch.setattr(main, "collect_with_fallback", fake_collect_with_fallback)
        request = OrchestrateRequest(message="Need current evidence", scout_model="scout", fallback_model="fallback")
        task = asyncio.create_task(main.run_scout(request, "run-1", emit, []))

        for _ in range(20):
            if any(event_type == "tool_call" for event_type, _ in events):
                break
            await asyncio.sleep(0)

        tool_event = next(payload for event_type, payload in events if event_type == "tool_call")
        assert skill.executed == []
        assert broker.resolve(str(tool_event["call_id"]), True) is True
        result = await task
        return result, events, skill.executed

    result, events, executed = asyncio.run(run())
    assert result.brief == "Evidence brief"
    assert executed == [{"query": "consent test"}]
    assert any(event_type == "tool_result" and payload["approved"] is True for event_type, payload in events)
