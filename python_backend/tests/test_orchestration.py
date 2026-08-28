from __future__ import annotations

import asyncio

from python_backend import main
from python_backend.types import OrchestrateRequest


def test_normalize_tool_calls_merges_stream_fragments_and_deduplicates() -> None:
    calls = main.normalize_tool_calls(
        [
            {"id": "call-0", "index": 0, "function": {"name": "web_search", "arguments": '{"query":"local'}},
            {"id": "call-0", "index": 0, "function": {"name": "web_search", "arguments": ' agents", "max_results": 3}'}},
            {"id": "call-0", "index": 0, "function": {"name": "web_search", "arguments": {"query": "local agents", "max_results": 3}}},
        ]
    )

    assert calls == [            {
                "index": 0,
                "id": "call-0",
                "name": "web_search",
                "arguments": {"query": "local agents", "max_results": 3},
            }

    ]


def test_collect_with_fallback_retries_and_emits_reset(monkeypatch) -> None:
    attempts: list[str] = []
    events: list[tuple[str, dict[str, object]]] = []

    async def fake_collect_turn(model, messages, emit, agent, tools=None, think=True, provider_id="ollama"):
        attempts.append(model)
        if model == "primary":
            raise RuntimeError("primary timed out")
        return main.Turn(content="fallback answer", model=model)

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr(main, "collect_turn", fake_collect_turn)
    result = asyncio.run(
        main.collect_with_fallback(
            "primary",
            "fallback",
            [],
            emit,
            "scout",
        )
    )

    assert result.content == "fallback answer"
    assert attempts == ["primary", "fallback"]
    assert [event[0] for event in events] == ["fallback", "agent_reset", "agent_status"]
    assert events[0][1]["to_model"] == "fallback"


def test_validate_arguments_rejects_wrong_tool_calls() -> None:
    schema = {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 8},
        },
        "additionalProperties": False,
    }

    assert main.validate_arguments({"query": "local agents"}, schema) == ""
    assert main.validate_arguments({"query": "local agents", "max_results": 3}, schema) == ""
    assert "missing required argument" in main.validate_arguments({}, schema)
    assert "must be a string" in main.validate_arguments({"query": 42}, schema)
    assert "must be an integer" in main.validate_arguments({"query": "x", "max_results": "5"}, schema)
    assert "at most 8" in main.validate_arguments({"query": "x", "max_results": 9}, schema)
    assert "unexpected argument" in main.validate_arguments({"query": "x", "extra": True}, schema)
    assert "must be a JSON object" in main.validate_arguments("not-an-object", schema)


def test_run_scout_emits_tool_error_for_unknown_skill_and_keeps_looping(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    messages: list[dict[str, object]] = [{"role": "user", "content": "research this"}]

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    class FakeTurn:
        content = ""
        thinking = ""
        tool_calls = [{"name": "read_files", "arguments": {"path": "/etc/passwd"}}]

    async def fake_collect_with_fallback(primary_model, fallback_model, messages, emit, agent, tools=None, primary_provider_id="ollama", fallback_provider_id="ollama"):
        return FakeTurn()

    async def fake_skills_execute(name, arguments):
        raise AssertionError("unknown skills must never execute")

    monkeypatch.setattr(main, "collect_with_fallback", fake_collect_with_fallback)
    monkeypatch.setattr(main.skills, "execute", fake_skills_execute)

    request = OrchestrateRequest(message="research this")
    result = asyncio.run(main.run_scout(request, "run-1", emit, []))

    assert result.brief == "The Scout reached the configured tool-call limit before producing a final brief."
    tool_errors = [payload for event_type, payload in events if event_type == "tool_error"]
    assert tool_errors, "expected a tool_error event for the unknown skill"
    assert "not a registered skill" in tool_errors[0]["reason"]
    assert all(event_type != "tool_call" for event_type, _ in events), "no consent modal may open for invalid calls"


def test_run_scout_emits_tool_error_for_invalid_arguments(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    class FakeTurn:
        content = ""
        thinking = ""
        tool_calls = [{"name": "web_search", "arguments": {"query": 12345}}]

    async def fake_collect_with_fallback(primary_model, fallback_model, messages, emit, agent, tools=None, primary_provider_id="ollama", fallback_provider_id="ollama"):
        return FakeTurn()

    monkeypatch.setattr(main, "collect_with_fallback", fake_collect_with_fallback)

    request = OrchestrateRequest(message="research this")
    result = asyncio.run(main.run_scout(request, "run-2", emit, []))

    tool_errors = [payload for event_type, payload in events if event_type == "tool_error"]
    assert tool_errors, "expected a tool_error event for invalid arguments"
    assert "must be a string" in tool_errors[0]["reason"]
    assert all(event_type != "tool_call" for event_type, _ in events)
    assert any(event_type == "agent_status" for event_type, _ in events)
    assert result.sources == []


def test_run_single_agent_returns_answer_and_collects_delegations(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    class FirstTurn:
        content = ""
        thinking = ""
        tool_calls = [{"name": "web_search", "arguments": {"query": "latest local ai models"}}]

    class SecondTurn:
        content = "Here is the final answer with evidence."
        thinking = ""
        tool_calls = []

    turns = iter([FirstTurn(), SecondTurn()])

    async def fake_collect_with_fallback(primary_model, fallback_model, messages, emit, agent, tools=None, primary_provider_id="ollama", fallback_provider_id="ollama"):
        return next(turns)

    async def fake_skills_execute(name, arguments):
        return {"ok": True, "results": [{"title": "Result", "url": "https://example.com", "snippet": "Snippet"}]}

    async def fake_wait(call_id: str, timeout_seconds: float) -> tuple[bool, str]:
        return True, "approved"

    monkeypatch.setattr(main, "collect_with_fallback", fake_collect_with_fallback)
    monkeypatch.setattr(main.skills, "execute", fake_skills_execute)
    monkeypatch.setattr(main.consent_broker, "wait", fake_wait)

    request = OrchestrateRequest(message="research this", single_agent=True)
    answer, delegations = asyncio.run(main.run_single_agent(request, "run-3", emit, []))

    assert answer == "Here is the final answer with evidence."
    assert len(delegations) == 1
    assert delegations[0]["tool"] == "web_search"
    assert delegations[0]["approved"] is True
    assert delegations[0]["sources"][0]["url"] == "https://example.com"
    tool_events = [payload for event_type, payload in events if event_type == "tool_call"]
    assert tool_events and tool_events[0]["agent"] == "main"


def test_pipeline_single_agent_skips_scout(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    async def fake_run_single_agent(request, run_id, emit, history):
        return "single answer", [{"tool": "web_search", "arguments": {"query": "x"}, "approved": True, "ok": True, "sources": [], "reason": "approved"}]

    async def fake_run_scout(request, run_id, emit, history):
        raise AssertionError("the scout must not run in single-agent mode")

    monkeypatch.setattr(main, "run_single_agent", fake_run_single_agent)
    monkeypatch.setattr(main, "run_scout", fake_run_scout)

    request = OrchestrateRequest(message="hello", single_agent=True)
    asyncio.run(main.pipeline(request, "run-4", emit))

    event_types = [event_type for event_type, _ in events]
    assert "run_complete" in event_types
    assert "scout_complete" not in event_types
    complete = [payload for event_type, payload in events if event_type == "run_complete"][0]
    assert complete["single_agent"] is True
    assert complete["answer"] == "single answer"
    assert complete["delegations"][0]["tool"] == "web_search"


def test_pipeline_three_agents_runs_analyst(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    async def fake_run_scout(request, run_id, emit, history):
        return main.ScoutResult(brief="scout brief", sources=[])

    async def fake_run_analyst(request, emit, history, scout_result):
        return "analysis packet"

    async def fake_run_synthesizer(request, emit, history, scout_result, analysis=""):
        assert analysis == "analysis packet", "synthesizer must receive the analyst packet"
        return "final answer"

    monkeypatch.setattr(main, "run_scout", fake_run_scout)
    monkeypatch.setattr(main, "run_analyst", fake_run_analyst)
    monkeypatch.setattr(main, "run_synthesizer", fake_run_synthesizer)

    request = OrchestrateRequest(message="hello", agent_count=3)
    asyncio.run(main.pipeline(request, "run-5", emit))

    event_types = [event_type for event_type, _ in events]
    assert "analyst_complete" in event_types
    assert "scout_complete" in event_types
    assert "run_complete" in event_types


def test_pipeline_two_agents_skips_analyst(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    async def fake_run_scout(request, run_id, emit, history):
        return main.ScoutResult(brief="brief", sources=[])

    async def fake_run_analyst(request, emit, history, scout_result):
        raise AssertionError("the analyst must not run with agent_count=2")

    async def fake_run_synthesizer(request, emit, history, scout_result, analysis=""):
        assert analysis == ""
        return "answer"

    monkeypatch.setattr(main, "run_scout", fake_run_scout)
    monkeypatch.setattr(main, "run_analyst", fake_run_analyst)
    monkeypatch.setattr(main, "run_synthesizer", fake_run_synthesizer)

    request = OrchestrateRequest(message="hello", agent_count=2)
    asyncio.run(main.pipeline(request, "run-6", emit))

    assert "analyst_complete" not in [event_type for event_type, _ in events]


def test_analyst_build_messages_contains_evidence() -> None:
    from python_backend.agents import analyst

    messages = analyst.build_messages([], "question", "brief", [{"title": "t", "url": "u", "snippet": "s"}])
    assert "Analyst" in messages[0]["content"]
    assert "brief" in messages[-1]["content"]
    assert "question" in messages[-1]["content"]
