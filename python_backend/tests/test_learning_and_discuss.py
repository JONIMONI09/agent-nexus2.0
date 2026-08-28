from __future__ import annotations

import asyncio

from python_backend import main
from python_backend.learning import MemoryStore, extract_lessons, prompt_block, record_lessons
from python_backend.skills.discuss import DebateSkill, parse_debate
from python_backend.types import OrchestrateRequest

import pytest


def test_extract_lessons_picks_up_user_preferences() -> None:
    outcome = extract_lessons(
        "From now on always answer in German. Be shorter. The weather is nice today.",
        "Sure.",
    )
    assert outcome.lessons, "preference sentences must be captured"
    assert any("German" in lesson for lesson in outcome.lessons)
    assert outcome.rules, "'From now on always' must become a standing rule"
    assert not any("weather" in lesson for lesson in outcome.lessons), "small talk must not become a lesson"


def test_extract_lessons_ignores_smalltalk_and_duplicates() -> None:
    first = extract_lessons("Always cite sources.")
    second = extract_lessons("Always cite sources.")
    assert first.lessons == ["Always cite sources."]
    assert second.lessons == first.lessons  # extraction is deterministic; dedupe happens on persist


def test_record_lessons_dedupes_and_appends(tmp_path) -> None:
    store = MemoryStore(directory=tmp_path)
    first = record_lessons(store, "Never run tools silently.")
    second = record_lessons(store, "Never run tools silently.")
    assert first.added_lessons == 1
    assert second.added_lessons == 0 or store.read("learn").count("Never run tools silently.") == 1, "identical lessons must never be stored twice"
    assert store.read("learn").count("Never run tools silently.") == 1


def test_prompt_block_contains_rules_agent_and_lessons(tmp_path) -> None:
    store = MemoryStore(directory=tmp_path)
    record_lessons(store, "Always answer briefly.")
    block = prompt_block(store)
    assert "Rules.md" in block or "Standing rules" in block
    assert "Agent.md" in block or "Agent profile" in block
    assert "Always answer briefly." in block
    assert len(block) <= 2400


def test_prompt_block_defaults_only_to_seed_rules(tmp_path) -> None:
    store = MemoryStore(directory=tmp_path)
    block = prompt_block(store)
    # Fresh stores contain only the seeded default rules - no lessons yet.
    assert "lessons" not in block.lower().split("rules")[0]


def test_parse_debate_splits_speeches_and_synthesis() -> None:
    raw = (
        "[The Advocate] Local models keep data private and costs near zero.\n"
        "[The Critic] They need RAM and quality lags hosted frontier models.\n"
        "[The Pragmatist] For drafts and research briefs local models are already enough.\n"
        "[Synthesis] Local-first wins for privacy-sensitive work; hybrid remains pragmatic."
    )
    parsed = parse_debate(raw, 3)
    assert [s["role"] for s in parsed["speeches"]] == ["The Advocate", "The Critic", "The Pragmatist"]
    assert "privacy-sensitive" in parsed["synthesis"]


def test_parse_debate_survives_missing_format() -> None:
    parsed = parse_debate("just a wall of text with no structure", 2)
    assert len(parsed["speeches"]) == 2


def test_debate_skill_rejects_empty_topic() -> None:
    skill = DebateSkill(chat=None)  # type: ignore[arg-type]
    result = asyncio.run(skill.execute({"topic": "  "}))
    assert result["ok"] is False
    assert "empty" in result["error"]


def test_debate_skill_calls_local_model_and_returns_panel(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_chat(system: str, user: str, history: list) -> str:
        captured["user"] = user
        return "[The Advocate] A\n[The Critic] B\n[Synthesis] C"

    skill = DebateSkill(chat=fake_chat)
    result = asyncio.run(skill.execute({"topic": "local vs hosted models", "speakers": 2}))
    assert result["ok"] is True
    assert result["speakers"] == 2
    assert "local vs hosted models" in captured["user"]
    assert parsed_ok(result)


def parsed_ok(result: dict) -> bool:
    return result["synthesis"] == "C" and len(result["speeches"]) == 2


def test_run_agent_loop_injects_memory_and_thinking(monkeypatch, tmp_path) -> None:
    seen: dict[str, str] = {}

    def fake_build_messages(history, user_message, custom_prompt="", memory_block="", thinking_hint=""):
        seen["memory"] = memory_block
        seen["thinking"] = thinking_hint
        return [{"role": "user", "content": user_message}]

    class Turn:
        content = "final"
        thinking = ""
        tool_calls: list = []

    async def fake_collect(*args, **kwargs):
        return Turn()

    monkeypatch.setattr(main, "collect_with_fallback", fake_collect)
    request = OrchestrateRequest(message="hello", learning_enabled=True, thinking_style="deep")
    main.memory_store = MemoryStore(directory=tmp_path)
    record_lessons(main.memory_store, "Always answer briefly.")
    events: list = []

    async def emit(event_type, **payload):
        events.append((event_type, payload))

    asyncio.run(
        main.run_agent_loop(
            request=request,
            run_id="run-x",
            emit=emit,
            history=[],
            agent="main",
            build_messages=fake_build_messages,
            primary_model="m",
            fallback_model="f",
            primary_provider_id="ollama",
            fallback_provider_id="ollama",
            working_label="The AI is working",
            limit_message="limit",
            collect_delegations=False,
        )
    )
    assert "Always answer briefly." in seen["memory"]
    assert "edge cases" in seen["thinking"]  # deep style instruction present


def test_discuss_delegation_emits_delegation_completed(monkeypatch) -> None:
    class Turn:
        content = ""
        thinking = ""
        tool_calls = [{"name": "discuss", "arguments": {"topic": "triangulation vs stars"}}]

    async def fake_collect(*args, **kwargs):
        return Turn()

    async def fake_execute(name, arguments):
        return {
            "ok": True,
            "topic": arguments["topic"],
            "speeches": [{"role": "The Advocate", "speech": "a"}],
            "synthesis": "s",
        }

    async def fake_wait(call_id, timeout_seconds):
        return True, "approved"

    monkeypatch.setattr(main, "collect_with_fallback", fake_collect)
    monkeypatch.setattr(main.skills, "execute", fake_execute)
    monkeypatch.setattr(main.consent_broker, "wait", fake_wait)
    events: list = []

    async def emit(event_type, **payload):
        events.append((event_type, payload))

    request = OrchestrateRequest(message="debate navigation methods", single_agent=True)
    answer, delegations = asyncio.run(main.run_single_agent(request, "run-d", emit, []))
    completed = [payload for event_type, payload in events if event_type == "delegation_completed"]
    assert completed and completed[0]["topic"] == "triangulation vs stars"
    assert delegations[0]["ok"] is True
    assert answer  # loop returned the limit message on capped rounds
