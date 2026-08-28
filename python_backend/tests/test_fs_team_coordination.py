"""Integration tests: root-agent scheduling and subagent messaging in FS runs."""
from __future__ import annotations

import asyncio
import json
import tempfile
from typing import Any

from python_backend.fs_agent.jail import PathJail
from python_backend.fs_agent.team import FsAgentTeam


def _jail() -> PathJail:
    return PathJail(root=tempfile.mkdtemp())


def _scripted_chat():
    """Chat stub walking the root agent through todo -> message -> schedule -> wait -> finish.

    Subagent calls are detected by the SUBAGENT system prompt and get their own reply.
    """
    calls: list[str] = []

    async def chat(messages: list[dict[str, str]]) -> str:
        system = messages[0]["content"]
        last = messages[-1]["content"]
        if system.startswith("You are a SUBAGENT"):
            calls.append("subagent")
            assert "subagent: reviewer checks README" in last
            assert "[root] Please focus on the README structure." in last
            return "PLAN: 1. Read the message. 2. Adjust plan to README structure.\nSTATUS: ready.\nNOTE FOR ROOT: plan adjusted as requested."
        calls.append("root:" + last[:24])
        if "User request" in last and len(messages) == 2:
            return json.dumps({"tool": "todo_add", "arguments": {"tasks": ["subagent: reviewer checks README"]}})
        if last.startswith("todo_add accepted"):
            return json.dumps({"tool": "message_subagent", "arguments": {"todo_id": "todo-1", "message": "Please focus on the README structure."}})
        if last.startswith("subagent todo-1"):
            return json.dumps({"tool": "schedule_task", "arguments": {"description": "verify output later", "delay_seconds": 1}})
        if last.startswith("scheduled task-1"):
            return json.dumps({"tool": "wait_for_schedule", "arguments": {}})
        if last.startswith("wait_for_schedule returned"):
            return json.dumps({"tool": "todo_done", "arguments": {"id": "todo-1"}})
        if last.startswith("todo_done todo-1"):
            return json.dumps({"tool": "finish", "arguments": {"summary": "All work coordinated and finished."}})
        return json.dumps({"tool": "finish", "arguments": {"summary": "unexpected state, finishing"}})

    return chat, calls


def _emit_capture():
    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(event_type: str, **payload: Any) -> None:
        events.append((event_type, payload))

    return events, emit


def test_root_messages_subagent_and_gets_reply() -> None:
    chat, _calls = _scripted_chat()
    events, emit = _emit_capture()
    team = FsAgentTeam(jail=_jail(), chat_fn=chat)

    state = asyncio.run(team.run("Create a README project", emit, needs_consent=lambda tool, args: asyncio.sleep(0, True)))

    kinds = [kind for kind, _payload in events]
    assert "fs_subagent_message" in kinds
    assert "fs_subagent_reply" in kinds
    assert state.finished
    todo = state.todos.get("todo-1")
    assert todo is not None
    senders = [item["from"] for item in todo.messages]
    assert senders == ["root", "subagent"]
    assert "PLAN:" in todo.messages[1]["text"]
    reply_event = next(payload for kind, payload in events if kind == "fs_subagent_reply")
    assert reply_event["agent"] == "reviewer checks README"


def test_root_schedules_and_waits_for_due_task() -> None:
    chat, _calls = _scripted_chat()
    events, emit = _emit_capture()
    team = FsAgentTeam(jail=_jail(), chat_fn=chat)

    state = asyncio.run(team.run("Create a README project", emit, needs_consent=lambda tool, args: asyncio.sleep(0, True)))

    kinds = [kind for kind, _payload in events]
    assert "fs_scheduled" in kinds
    assert "fs_schedule_wait" in kinds
    assert "fs_schedule_due" in kinds
    scheduled = next(payload for kind, payload in events if kind == "fs_scheduled")
    assert scheduled["task"]["delay_seconds"] == 1
    assert state.scheduler.tasks == []  # due task was collected


def test_new_tools_bypass_consent_gate() -> None:
    """schedule_task / wait_for_schedule / message_subagent never touch disk, so they must NOT open the consent modal."""
    chat, _calls = _scripted_chat()
    events, emit = _emit_capture()

    consent_requests: list[str] = []

    async def needs_consent(tool: str, args: dict[str, Any]) -> bool:
        consent_requests.append(tool)
        return True

    team = FsAgentTeam(jail=_jail(), chat_fn=chat)
    asyncio.run(team.run("Create a README project", emit, needs_consent=needs_consent))

    assert "message_subagent" not in consent_requests
    assert "schedule_task" not in consent_requests
    assert "wait_for_schedule" not in consent_requests


def test_message_to_non_subagent_todo_is_rejected() -> None:
    events, emit = _emit_capture()
    attempts: list[str] = []

    async def chat(messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"]
        if "User request" in last and len(messages) == 2:
            return json.dumps({"tool": "todo_add", "arguments": {"tasks": ["plain task without prefix"]}})
        if last.startswith("todo_add accepted"):
            return json.dumps({"tool": "message_subagent", "arguments": {"todo_id": "todo-1", "message": "hello"}})
        if last.startswith("message_subagent rejected"):
            attempts.append("rejected")
            return json.dumps({"tool": "finish", "arguments": {"summary": "stopped, open todo explained: rejected message test"}})
        return json.dumps({"tool": "finish", "arguments": {"summary": "unexpected"}})

    team = FsAgentTeam(jail=_jail(), chat_fn=chat)
    state = asyncio.run(team.run("simple task", emit, needs_consent=lambda tool, args: asyncio.sleep(0, True)))

    assert attempts == ["rejected"]
    assert state.finished
    kinds = [kind for kind, _payload in events]
    assert "fs_subagent_message" not in kinds


def test_subagent_outage_is_graceful() -> None:
    """If the model dies mid-subagent-turn, the root gets the failure as a message and the run survives."""
    events, emit = _emit_capture()
    flaky = {"broken": True}

    async def chat(messages: list[dict[str, str]]) -> str:
        system = messages[0]["content"]
        last = messages[-1]["content"]
        if system.startswith("You are a SUBAGENT") and flaky["broken"]:
            raise RuntimeError("provider died")
        if system.startswith("You are a SUBAGENT"):
            return "PLAN: 1. ok\nSTATUS: fine\nNOTE FOR ROOT: recovered."
        if "User request" in last and len(messages) == 2:
            return json.dumps({"tool": "todo_add", "arguments": {"tasks": ["subagent: builder writes files"]}})
        if last.startswith("todo_add accepted"):
            return json.dumps({"tool": "message_subagent", "arguments": {"todo_id": "todo-1", "message": "go"}})
        if last.startswith("subagent todo-1") and "failed to respond" in last:
            flaky["broken"] = False
            return json.dumps({"tool": "message_subagent", "arguments": {"todo_id": "todo-1", "message": "retry please"}})
        if last.startswith("subagent todo-1"):
            return json.dumps({"tool": "finish", "arguments": {"summary": "subagent recovered and answered, open todo finished"}})
        return json.dumps({"tool": "finish", "arguments": {"summary": "unexpected"}})

    team = FsAgentTeam(jail=_jail(), chat_fn=chat)
    state = asyncio.run(team.run("build files", emit, needs_consent=lambda tool, args: asyncio.sleep(0, True)))

    assert state.finished
    todo = state.todos.get("todo-1")
    assert todo is not None
    assert any("failed to respond" in item["text"] for item in todo.messages)
    assert any("recovered" in item["text"] for item in todo.messages)
