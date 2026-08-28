from __future__ import annotations

import asyncio

import pytest

from python_backend.context import pack_history
from python_backend.tools import ConsentBroker, ToolRegistry
from python_backend.types import HistoryMessage


class EchoSkill:
    name = "echo"
    description = "Return the supplied value."
    parameters = {"type": "object", "properties": {"value": {"type": "string"}}}

    async def execute(self, arguments: dict[str, object]) -> dict[str, object]:
        return {"ok": True, "value": arguments.get("value")}


def test_pack_history_retains_newest_messages_with_marker() -> None:
    history = [
        HistoryMessage(role="user", content="a" * 500),
        HistoryMessage(role="assistant", content="b" * 500),
        HistoryMessage(role="user", content="c" * 500),
    ]
    packed = pack_history(history, max_chars=1000)

    assert packed.compacted is True
    assert packed.dropped_count == 2
    assert packed.messages[0]["content"].startswith("[Earlier context compacted")
    assert packed.messages[-1]["content"] == "c" * 500


def test_tool_registry_exposes_schema_and_executes_skill() -> None:
    async def run() -> dict[str, object]:
        registry = ToolRegistry([EchoSkill()])
        assert registry.get("echo") is not None
        assert registry.schemas()[0]["function"]["name"] == "echo"
        return await registry.execute("echo", {"value": "ok"})

    assert asyncio.run(run()) == {"ok": True, "value": "ok"}


def test_tool_registry_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError):
        ToolRegistry([EchoSkill(), EchoSkill()])


def test_consent_broker_resolves_approval() -> None:
    async def run() -> tuple[bool, str]:
        broker = ConsentBroker()
        broker.create("call-1", "run-1")
        decision = asyncio.create_task(broker.wait("call-1", 1))
        await asyncio.sleep(0)
        assert broker.resolve("call-1", True) is True
        return await decision

    assert asyncio.run(run()) == (True, "approved")


def test_consent_broker_denial_and_missing_request() -> None:
    async def run() -> tuple[tuple[bool, str], tuple[bool, str]]:
        broker = ConsentBroker()
        broker.create("call-2", "run-2")
        decision = asyncio.create_task(broker.wait("call-2", 1))
        await asyncio.sleep(0)
        broker.resolve("call-2", False)
        return await decision, await broker.wait("missing", 0.01)

    assert asyncio.run(run()) == ((False, "denied"), (False, "missing_request"))
