"""FS-agent team runner.

A run spawns a ROOT AGENT that works on the jailed projects/ workspace with the
filesystem tool set. Following the Antigravity 2.0 pattern, the root agent
orchestrates optional named subagents (planner / builder / reviewer); the
original user request is stored verbatim in docs/original_request.md and every
agent is instructed to read it and follow AGENTS.md rules in every folder.

Events (SSE): fs_started, fs_todo_list, fs_todo_update, fs_agent_started,
fs_tool_call (consent-gated), fs_tool_result, fs_tool_mismatch, fs_loop_notice,
fs_agent_finished, fs_complete, fs_error.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from .fs_tools import ToolFailure, build_tool_registry
from .jail import PathJail
from .loop import LoopDetector
from .scheduler import MAX_WAIT_BUDGET_SECONDS, ScheduleError, Scheduler, ScheduledTask
from .todos import Todo, TodoBoard

EventEmitter = Callable[..., Awaitable[None]]

MAX_FS_ROUNDS = 24

ROOT_SYSTEM_PROMPT = """You are the ROOT AGENT of the Local Agent Studio filesystem team. You work inside a strictly jailed "projects" workspace: every tool path is relative to it and escaping is impossible and forbidden.

Your protocol (follow it exactly):
1. COMPLEXITY: For any non-trivial task, FIRST call todo_add with a numbered plan (4-8 steps). You MUST keep this list updated (todo_done) - the run cannot finish with open todos unless you explain why in finish.
2. TEAM: You may commission subagents via todo_add entries prefixed "subagent:" (e.g. "subagent: reviewer checks all files"). They work under your direction; you remain responsible.
3. DOCS: Create the project with fs_create_project - the user's original request is stored verbatim in docs/original_request.md. Before building, fs_read_file it. Every folder you create via fs_create_folder automatically receives an AGENTS.md; read AGENTS.md files before working in a folder.
4. FILES: fs_write_file only for NEW complete files (placeholders are rejected). fs_edit_file requires the EXACT old_string from the current file. If the tool answers MISMATCH or AMBIGUOUS: immediately fs_read_file the file and retry with corrected text - do not guess.
5. LOOPS: If you receive a ⚠️ SYSTEM loop notice, change your approach visibly: different arguments, re-read, or finish with an honest summary.
6. VERIFY: Before finishing, use fallow_analyze on the project when it contains code. Call finish with a short report of what was created and where."""

SUBAGENT_NOTE = """

TEAM CHANNEL: todos prefixed 'subagent:' are your commissioned specialists. Send them instructions with message_subagent - they read every message directly, may adjust their own plan, and reply to you. Their reply arrives as a message; coordinate visibly.

SCHEDULING: schedule_task registers a delayed task (max 300s, max 8 tasks). Call wait_for_schedule to REALLY wait for due tasks and then act on them. The per-run wait budget is limited, so schedule only what this run itself must handle."""

SUBAGENT_SYSTEM_PROMPT = """You are a SUBAGENT specialist commissioned by the ROOT AGENT of the filesystem team. You receive your commissioned task plus the message thread with the root agent. Read every message directly - if a message changes the requirements, ADJUST YOUR PLAN and say so explicitly.

Reply in exactly this shape:
PLAN: your numbered steps (adjusted if a root message requires it)
STATUS: what you will do next or what you need
NOTE FOR ROOT: one short paragraph with what the root must know.

Be concise and concrete. Never claim you modified the filesystem in this reply - you only plan and report here."""


@dataclass
class FsRunState:
    run_id: str
    todos: TodoBoard = field(default_factory=TodoBoard)
    scheduler: Scheduler = field(default_factory=Scheduler)
    tools_used: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False


class FsAgentTeam:
    """Runs the filesystem agent against a local model via the provider runtime."""

    def __init__(self, jail: PathJail, chat_fn: Callable[[list[dict[str, str]]], Awaitable[str]]) -> None:
        self.jail = jail
        self._chat = chat_fn
        self._schemas, self._executor = build_tool_registry(jail)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return self._schemas

    def extra_tools(self) -> list[dict[str, Any]]:
        """todo_add / todo_done / finish descriptors appended to the model tools."""
        return [
            {
                "name": "todo_add",
                "description": "MANDATORY for complex tasks: register your plan as todos (4-8 steps). Prefix entries with 'subagent:' to commission a specialist.",
                "parameters": {"type": "object", "required": ["tasks"], "properties": {"tasks": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 8}}, "additionalProperties": False},
            },
            {
                "name": "todo_done",
                "description": "Mark one todo completed by id. The run cannot finish while todos are open.",
                "parameters": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}, "additionalProperties": False},
            },
            {
                "name": "finish",
                "description": "End the run with a final report. Requires a summary; open todos must be explained.",
                "parameters": {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string"}}, "additionalProperties": False},
            },
            {
                "name": "schedule_task",
                "description": "Schedule a delayed task for THIS run (real waiting, capped). Use wait_for_schedule afterwards to act on due tasks.",
                "parameters": {"type": "object", "required": ["description", "delay_seconds"], "properties": {"description": {"type": "string", "maxLength": 240}, "delay_seconds": {"type": "number", "minimum": 1, "maximum": 300}}, "additionalProperties": False},
            },
            {
                "name": "wait_for_schedule",
                "description": "Really wait until at least one scheduled task is due (bounded by the per-run wait budget), then act on the delivered descriptions.",
                "parameters": {"type": "object", "required": [], "properties": {}, "additionalProperties": False},
            },
            {
                "name": "message_subagent",
                "description": "Send an instruction to a commissioned subagent todo (id prefixed 'subagent:'). The subagent reads it directly, may adjust its plan, and replies to you.",
                "parameters": {"type": "object", "required": ["todo_id", "message"], "properties": {"todo_id": {"type": "string"}, "message": {"type": "string", "maxLength": 2000}}, "additionalProperties": False},
            },
        ]

    def all_schemas(self) -> list[dict[str, Any]]:
        return self.schemas + self.extra_tools()

    async def run(self, message: str, emit: EventEmitter, needs_consent) -> FsRunState:  # noqa: ANN001
        """Execute one FS-agent run; ``needs_consent(tool, args)`` gates real execution."""
        run_id = str(uuid.uuid4())
        state = FsRunState(run_id=run_id)
        loop_guard = LoopDetector()
        board = state.todos
        messages: list[dict[str, str]] = [
            {"role": "system", "content": ROOT_SYSTEM_PROMPT + SUBAGENT_NOTE},
            {"role": "user", "content": f"User request:\n{message}"},
        ]

        await emit("fs_started", run_id=run_id)
        await emit("fs_agent_started", agent="root", role="Root Agent — orchestrates the team")

        for _round in range(MAX_FS_ROUNDS):
            raw = await self._chat(messages)
            call = _parse_tool_call(raw)
            if call is None:
                # Plain prose: accept as the final report.
                await emit("fs_complete", run_id=run_id, summary=raw.strip()[:4000], todos=board.as_list())
                state.finished = True
                return state

            tool = call.get("tool", "")
            arguments = call.get("arguments", {}) if isinstance(call.get("arguments"), dict) else {}

            if tool == "finish":
                summary = str(arguments.get("summary", "")).strip()
                open_items = board.open_items()
                if open_items and not any(keyword in summary.lower() for keyword in ("open todo", "unfinished", "blocked")):
                    notice = f"⚠️ SYSTEM: {len(open_items)} todos are still open ({', '.join(item.task[:40] for item in open_items[:3])}). Either complete them with todo_done or explain in the finish summary why they stay open."
                    await emit("fs_loop_notice", reason=notice)
                    messages.append({"role": "user", "content": notice})
                    continue
                await emit("fs_complete", run_id=run_id, summary=summary[:4000], todos=board.as_list())
                state.finished = True
                return state

            if tool == "todo_add":
                tasks = arguments.get("tasks")
                created = board.set_all([str(task) for task in tasks] if isinstance(tasks, list) else [])
                await emit("fs_todo_list", todos=board.as_list(), created=created)
                messages.append({"role": "assistant", "content": raw.strip()[:1200]})
                messages.append({"role": "user", "content": f"todo_add accepted: {created} todos registered. Work through them one by one."})
                continue

            if tool == "todo_done":
                todo_id = str(arguments.get("id", ""))
                ok = board.complete(todo_id)
                await emit("fs_todo_update", todos=board.as_list(), id=todo_id, ok=ok)
                messages.append({"role": "user", "content": f"todo_done {todo_id}: {'marked completed' if ok else 'UNKNOWN id - use an existing todo id'}. Board: {board.summary()}"})
                continue

            if tool == "schedule_task":
                loop_notice = loop_guard.record(tool, arguments)
                if loop_notice:
                    await emit("fs_loop_notice", reason=loop_notice, tool=tool)
                    messages.append({"role": "user", "content": loop_notice})
                    continue
                try:
                    task = state.scheduler.schedule(str(arguments.get("description", "")), arguments.get("delay_seconds", 0))
                except ScheduleError as exc:
                    messages.append({"role": "user", "content": f"schedule_task rejected: {exc}"})
                    continue
                await emit("fs_scheduled", task=task.as_dict(), schedule=state.scheduler.summary())
                messages.append({"role": "assistant", "content": raw.strip()[:1200]})
                messages.append({"role": "user", "content": f"scheduled {task.id}: '{task.description}' due in {round(task.delay_seconds, 1)}s. Call wait_for_schedule when you want to act on due tasks."})
                continue

            if tool == "wait_for_schedule":
                if not state.scheduler.has_pending():
                    messages.append({"role": "user", "content": "wait_for_schedule: nothing is scheduled. Use schedule_task first, or continue with other work."})
                    continue
                await emit("fs_schedule_wait", budget_left=round(MAX_WAIT_BUDGET_SECONDS - state.scheduler.waited_seconds, 1))
                due: list[ScheduledTask] = await state.scheduler.wait_for_due()
                if due:
                    await emit("fs_schedule_due", tasks=[item.as_dict() for item in due])
                    lines = "\n".join(f"- {item.id}: {item.description}" for item in due)
                    messages.append({"role": "user", "content": f"wait_for_schedule returned: these tasks are NOW DUE - act on them:\n{lines}"})
                else:
                    messages.append({"role": "user", "content": "wait_for_schedule: the per-run wait budget is exhausted and nothing became due. Continue with other work or finish."})
                continue

            if tool == "message_subagent":
                loop_notice = loop_guard.record(tool, arguments)
                if loop_notice:
                    await emit("fs_loop_notice", reason=loop_notice, tool=tool)
                    messages.append({"role": "user", "content": loop_notice})
                    continue
                todo_id = str(arguments.get("todo_id", ""))
                note = str(arguments.get("message", ""))
                target = board.get(todo_id)
                if target is None or not target.task.lower().startswith("subagent:"):
                    messages.append({"role": "user", "content": f"message_subagent rejected: '{todo_id}' is not a commissioned subagent todo (entries prefixed 'subagent:'). Board: {board.summary()}"})
                    continue
                board.add_message(todo_id, "root", note)
                await emit("fs_subagent_message", todo_id=todo_id, agent=_subagent_role(target), text=note[:500])
                reply = await self._subagent_turn(target)
                board.add_message(todo_id, "subagent", reply)
                await emit("fs_subagent_reply", todo_id=todo_id, agent=_subagent_role(target), text=reply[:800])
                messages.append({"role": "assistant", "content": raw.strip()[:1200]})
                messages.append({"role": "user", "content": f"subagent {todo_id} ({_subagent_role(target)}) read your message directly and replied:\n{reply[:1500]}\nIf the reply changes the work, adjust the plan and continue."})
                continue

            loop_notice = loop_guard.record(tool, arguments)
            if loop_notice:
                await emit("fs_loop_notice", reason=loop_notice, tool=tool)
                messages.append({"role": "user", "content": loop_notice})
                continue

            await emit("fs_tool_call", run_id=run_id, tool=tool, arguments=arguments, agent="root")
            if not await needs_consent(tool, arguments):
                result: dict[str, Any] = {"ok": False, "error": "Denied by user - the tool did not run."}
            else:
                try:
                    result = self._executor(tool, arguments)
                    loop_guard.record_success()
                except ToolFailure as exc:
                    result = {"ok": False, "error": str(exc)}
                    mismatch_notice = loop_guard.record_error()
                    await emit("fs_tool_mismatch", tool=tool, reason=str(exc))
                    if mismatch_notice:
                        await emit("fs_loop_notice", reason=mismatch_notice)
                except Exception as exc:  # noqa: BLE001 - fed back to the model
                    result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

            state.tools_used.append({"tool": tool, "arguments": arguments, "ok": bool(result.get("ok"))})
            await emit("fs_tool_result", tool=tool, ok=bool(result.get("ok")), brief=_brief_result(tool, result))
            messages.append({"role": "assistant", "content": raw.strip()[:1200]})
            messages.append({"role": "user", "content": f"tool result for {tool}:\n{json.dumps(result, ensure_ascii=True)[:4000]}"})

        timeout_notice = "⚠️ SYSTEM: the FS agent reached the tool-round limit. Finish now with your best result via finish."
        await emit("fs_loop_notice", reason=timeout_notice)
        messages.append({"role": "user", "content": timeout_notice})
        raw = await self._chat(messages)
        call = _parse_tool_call(raw)
        summary = call.get("arguments", {}).get("summary", raw) if call and call.get("tool") == "finish" else raw
        await emit("fs_complete", run_id=run_id, summary=str(summary)[:4000], todos=board.as_list())
        state.finished = True
        return state


    async def _subagent_turn(self, todo: Todo) -> str:
        """Give the commissioned subagent a focused turn: it reads the thread (root
        messages included) and answers with an adjusted plan. Never raises."""
        thread = "\n".join(f"[{item['from']}] {item['text']}" for item in todo.messages) or "(no messages yet)"
        sub_messages = [
            {"role": "system", "content": SUBAGENT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Your commissioned task:\n{todo.task}\n\nMessage thread with the root agent:\n{thread}"},
        ]
        try:
            reply = await self._chat(sub_messages)
        except Exception as exc:  # noqa: BLE001 - a failed subagent must not kill the run
            return f"subagent failed to respond: {type(exc).__name__}: {exc}"
        return reply.strip()[:2000] or "(empty reply - the root should retry or do the work itself)"


def _subagent_role(todo: Todo) -> str:
    """Human-readable specialist name from a 'subagent: <role> ...' todo."""
    lowered = todo.task.lower()
    if lowered.startswith("subagent:") and ":" in todo.task:
        return todo.task.split(":", 1)[1].strip()[:40] or "specialist"
    return todo.task[:40] or "specialist"


def _parse_tool_call(raw: str) -> dict[str, Any] | None:
    """Parse a JSON tool call from the model text (tolerates code fences)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("tool"), str):
        return parsed
    return None


def _brief_result(tool: str, result: dict[str, Any]) -> str:
    if result.get("ok"):
        if "entries" in result:
            return f"{len(result['entries'])} entries"
        if "created" in result:
            return f"created: {', '.join(result['created'])}"
        if "path" in result:
            return str(result["path"])
        return "ok"
    return str(result.get("error", "failed"))[:200]
