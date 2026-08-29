from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .agents import analyst, main_agent, scout, synthesizer
from .config import APPROVAL_TIMEOUT_SECONDS, FALLBACK_MODEL, GENERATION_STALL_TIMEOUT_SECONDS, MAX_CONTEXT_CHARS, MAX_TOOL_ROUNDS, OLLAMA_BASE_URL, PROVIDER_PROBE_TIMEOUT_SECONDS, ALLOW_CUSTOM_PROVIDERS
from .context import pack_history
from .fs_agent.jail import PathJail
from .fs_agent.team import FsAgentTeam
from .learning import MemoryStore, extract_lessons, prompt_block, record_lessons
from .ollama_client import OllamaClient, OllamaError
from .provider_models import ProviderProfile, generated_provider_id, host_from_url, normalize_base_url
from .provider_presets import provider_presets
from .provider_probe import ProviderProbe
from .provider_runtime import ProviderRuntime, ProviderRuntimeError, is_browser_only_provider, provider_unconfigured_message
from .provider_store import ProviderStore
from .skills.discuss import DebateSkill
from .skills.web_search import WebSearchSkill
from .tools import ConsentBroker, ToolRegistry
from .translate import translation_routes, translate_message_best_effort
from .github_service import GitHubService, GitHubServiceError
from .types import ApprovalRequest, FsRunRequest, FsSettingsRequest, GitHubBranchRequest, GitHubPullRequestRequest, GitHubRepositoryRequest, HistoryMessage, LearningSettingsRequest, LearningUpdateRequest, OrchestrateRequest, ProviderDetectionRequest, ProviderModelsRequest, ProviderUpsertRequest

app = FastAPI(title="Local Agent Studio API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["DELETE", "GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

ollama = OllamaClient(base_url=OLLAMA_BASE_URL)
provider_store = ProviderStore()
provider_probe = ProviderProbe(timeout_seconds=PROVIDER_PROBE_TIMEOUT_SECONDS)
provider_runtime = ProviderRuntime(provider_store)


def seed_builtin_providers() -> None:
    for preset in provider_presets()[:5]:
        payload = {
            **preset,
            "base_url": OLLAMA_BASE_URL if preset["id"] == "ollama" else preset["base_url"],
            "capabilities": {},
            "builtin": True,
        }
        provider_store.upsert(ProviderProfile.model_validate(payload))


seed_builtin_providers()
consent_broker = ConsentBroker()
memory_store = MemoryStore()
learning_enabled = {"on": False}


async def _debate_chat_async(system: str, user: str, history: list[dict[str, str]]) -> str:
    """Run the debate panel on the local fallback model via the provider runtime."""
    chunks: list[str] = []
    async for chunk in provider_runtime.chat_stream(provider_id="ollama", model=FALLBACK_MODEL, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], tools=None, think=False):
        message = chunk.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            chunks.append(message["content"])
        if chunk.get("done") is True:
            break
    return "".join(chunks)


debate_skill = DebateSkill(chat=_debate_chat_async)
skills = ToolRegistry([WebSearchSkill(), debate_skill])

EventEmitter = Callable[..., Awaitable[None]]

THINKING_STYLES: dict[str, dict[str, str]] = {
    "concise": {
        "label": "Concise",
        "instruction": "Think and answer in the fewest words possible. No preamble, no repetition. Lead with the direct answer, then at most 3 short supporting bullets.",
    },
    "balanced": {
        "label": "Balanced",
        "instruction": "Think through the request step by step internally, then answer in a compact, well-structured way. Cover what matters, skip filler.",
    },
    "deep": {
        "label": "Deep",
        "instruction": "Think carefully and exhaustively before answering. Examine edge cases, assumptions and counterarguments. Structure the answer with headings; make reasoning explicit but never reveal hidden chain-of-thought - summarize the conclusions your deliberation reached.",
    },
    "creative": {
        "label": "Creative",
        "instruction": "Brainstorm broadly before answering. Generate several distinct angles or alternatives, pick the strongest, and mention one unconventional option the user may not have considered.",
    },
}


def thinking_instruction(style: str) -> str:
    return THINKING_STYLES.get(style, THINKING_STYLES["balanced"])["instruction"]


@dataclass
class Turn:
    content: str = ""
    thinking: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""


@dataclass
class ScoutResult:
    brief: str
    sources: list[dict[str, str]]


def event_payload(event_type: str, **payload: Any) -> str:
    return f"data: {json.dumps({'type': event_type, **payload}, ensure_ascii=True)}\n\n"


def validate_arguments(arguments: Any, schema: dict[str, Any]) -> str:
    """Return an error message when the model's tool arguments violate the skill schema."""
    if not isinstance(arguments, dict):
        return "arguments must be a JSON object."
    properties = schema.get("properties", {})
    for required in schema.get("required", []):
        if required not in arguments:
            return f"missing required argument '{required}'."
    for name, value in arguments.items():
        if name not in properties:
            if schema.get("additionalProperties") is False:
                return f"unexpected argument '{name}' is not allowed."
            continue
        prop = properties[name]
        expected = prop.get("type")
        if expected == "string" and not isinstance(value, str):
            return f"argument '{name}' must be a string."
        if expected == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
            return f"argument '{name}' must be an integer."
        if expected == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            return f"argument '{name}' must be a number."
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            if minimum is not None and value < minimum:
                return f"argument '{name}' must be at least {minimum}."
            if maximum is not None and value > maximum:
                return f"argument '{name}' must be at most {maximum}."
    return ""


def normalize_tool_calls(raw_calls: list[Any]) -> list[dict[str, Any]]:
    """Merge streamed argument fragments while retaining parallel tool calls."""
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for position, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            continue
        function = raw_call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        call_key: Any = None
        for candidate in (raw_call.get("index"), function.get("index"), raw_call.get("id"), raw_call.get("_batch_index")):
            if candidate is not None:
                call_key = candidate
                break
        if call_key is None:
            call_key = position
        key = str(call_key)
        if key not in grouped:
            grouped[key] = {
                "index": raw_call.get("index", function.get("index", position)),
                "id": raw_call.get("id"),
                "name": name.strip() if isinstance(name, str) else "",
                "argument_text": "",
                "arguments": {},
            }
            order.append(key)

        entry = grouped[key]
        if raw_call.get("id"):
            entry["id"] = raw_call["id"]
        if isinstance(name, str) and name.strip():
            entry["name"] = name.strip()
        arguments = function.get("arguments", {})
        if isinstance(arguments, dict):
            entry["arguments"].update(arguments)
        elif isinstance(arguments, str):
            if entry["arguments"]:
                try:
                    parsed = json.loads(arguments)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    entry["arguments"].update(parsed)
            else:
                entry["argument_text"] += arguments

    normalized: list[dict[str, Any]] = []
    for key in order:
        entry = grouped[key]
        parsed_arguments: dict[str, Any] = dict(entry["arguments"])
        argument_text = entry["argument_text"].strip()
        if argument_text:
            try:
                parsed = json.loads(argument_text)
            except json.JSONDecodeError:
                parsed = {"raw": argument_text}
            if isinstance(parsed, dict):
                parsed_arguments.update(parsed)
            else:
                parsed_arguments["value"] = parsed
        if not entry["name"]:
            continue
        normalized.append(
            {
                "index": entry["index"],
                "id": entry.get("id"),
                "name": entry["name"],
                "arguments": parsed_arguments,
            }
        )
    return normalized


async def collect_turn(
    model: str,
    messages: list[dict[str, Any]],
    emit: EventEmitter,
    agent: str,
    tools: list[dict[str, Any]] | None = None,
    think: bool = True,
    provider_id: str = "ollama",
) -> Turn:
    turn = Turn(model=model)
    raw_calls: list[Any] = []
    thinking_notice_sent = False

    # Stall watchdog: a hung provider (dead model server, wedged GPU driver) must never
    # hang the whole run. Each wait for the next chunk is bounded; on stall we raise so
    # collect_with_fallback retries transparently with the fallback model.
    loop = asyncio.get_running_loop()
    iterator = provider_runtime.chat_stream(provider_id=provider_id, model=model, messages=messages, tools=tools, think=think).__aiter__()
    while True:
        try:
            chunk = await asyncio.wait_for(anext(iterator), timeout=GENERATION_STALL_TIMEOUT_SECONDS)
        except StopAsyncIteration:
            break
        except asyncio.TimeoutError:
            raise OllamaError(
                f"{agent} stalled: no model output for {GENERATION_STALL_TIMEOUT_SECONDS:.0f}s "
                f"(provider '{provider_id}', model '{model}')."
            )
        message = chunk.get("message")
        if not isinstance(message, dict):
            continue
        thinking = message.get("thinking")
        if isinstance(thinking, str) and thinking:
            turn.thinking += thinking
            if not thinking_notice_sent:
                thinking_notice_sent = True
                await emit(
                    "agent_status",
                    agent=agent,
                    phase="working",
                    label="Reasoning locally",
                    detail="Keeping the private model trace on this machine.",
                )
            await emit("agent_think", agent=agent, content=thinking)
        content = message.get("content")
        if isinstance(content, str) and content:
            turn.content += content
            await emit("agent_delta", agent=agent, content=content)
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for batch_index, tool_call in enumerate(tool_calls):
                if isinstance(tool_call, dict):
                    raw_calls.append({**tool_call, "_batch_index": batch_index})
        if chunk.get("done") is True:
            break

    turn.tool_calls = normalize_tool_calls(raw_calls)
    if not turn.content.strip() and not turn.tool_calls:
        raise OllamaError(f"Ollama returned no usable content for {agent}.")
    return turn


async def collect_with_fallback(
    primary_model: str,
    fallback_model: str,
    messages: list[dict[str, Any]],
    emit: EventEmitter,
    agent: str,
    tools: list[dict[str, Any]] | None = None,
    primary_provider_id: str = "ollama",
    fallback_provider_id: str = "ollama",
) -> Turn:
    # Fail fast on providers the server cannot reach at all (e.g. the frontend-only
    # browser-webllm). One clear error replaces the old cascade where the same
    # "not configured" text surfaced twice (primary + fallback attempt).
    if not provider_runtime.has_provider(primary_provider_id):
        raise OllamaError(provider_unconfigured_message(primary_provider_id))
    if not provider_runtime.has_provider(fallback_provider_id):
        # Keep the run alive on the primary only; never attempt the unknown fallback.
        try:
            return await collect_turn(primary_model, messages, emit, agent, tools=tools, think=True, provider_id=primary_provider_id)
        except Exception as primary_error:
            raise OllamaError(
                f"{agent} failed on model '{primary_model}' via provider '{primary_provider_id}': "
                f"{primary_error} The fallback provider '{fallback_provider_id}' is not configured, "
                "so no fallback was attempted."
            ) from primary_error

    primary_error: Exception | None = None
    try:
        return await collect_turn(primary_model, messages, emit, agent, tools=tools, think=True, provider_id=primary_provider_id)
    except Exception as exc:
        primary_error = exc

    if fallback_provider_id == primary_provider_id and fallback_model == primary_model:
        raise OllamaError(f"{agent} failed on model '{primary_model}' via provider '{primary_provider_id}': {primary_error}") from primary_error

    await emit(
        "fallback",
        agent=agent,
        from_model=primary_model,
        to_model=fallback_model,
        from_provider=primary_provider_id,
        to_provider=fallback_provider_id,
        reason=str(primary_error),
    )
    await emit(
        "agent_reset",
        agent=agent,
        reason="The primary local model failed; the fallback response replaces the incomplete turn.",
    )
    await emit(
        "agent_status",
        agent=agent,
        phase="working",
        label="Fallback model active",
        detail=f"Retrying locally with {fallback_model}.",
    )
    try:
        return await collect_turn(fallback_model, messages, emit, agent, tools=tools, think=False, provider_id=fallback_provider_id)
    except Exception as fallback_error:
        raise OllamaError(
            f"{agent} failed on '{primary_model}' via '{primary_provider_id}' and fallback '{fallback_model}' via '{fallback_provider_id}' also failed: {fallback_error}"
        ) from fallback_error


async def run_agent_loop(
    *,
    request: OrchestrateRequest,
    run_id: str,
    emit: EventEmitter,
    history: list[Any],
    agent: str,
    build_messages: Callable[..., list[dict[str, Any]]],
    primary_model: str,
    fallback_model: str,
    primary_provider_id: str,
    fallback_provider_id: str,
    working_label: str,
    limit_message: str,
    collect_delegations: bool,
) -> tuple[str, list[dict[str, str]], list[dict[str, Any]]]:
    """Run the tool-capable agent loop with consent gating. Returns (final_content, sources, delegations)."""
    memory_block = prompt_block(memory_store) if (request.learning_enabled or learning_enabled["on"]) and prompt_block(memory_store) else ""
    thinking_hint = thinking_instruction(request.thinking_style)
    messages = build_messages(history, request.message, request.system_prompt, memory_block=memory_block, thinking_hint=thinking_hint)
    sources: list[dict[str, str]] = []
    delegations: list[dict[str, Any]] = []
    tool_schemas = skills.schemas()

    for round_number in range(MAX_TOOL_ROUNDS):
        # Silent phase: the model is only THINKING here. No status event is emitted, so the
        # strip above the chat box stays empty unless the agent actually uses a tool.
        turn = await collect_with_fallback(
            primary_model,
            fallback_model,
            messages,
            emit,
            agent,
            tools=tool_schemas,
            primary_provider_id=primary_provider_id,
            fallback_provider_id=fallback_provider_id,
        )
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": turn.content,
        }
        if turn.thinking:
            assistant_message["thinking"] = turn.thinking
        if turn.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "type": "function",
                    "id": call.get("id"),
                    "function": {"name": call["name"], "arguments": call["arguments"]},
                }
                for call in turn.tool_calls
            ]
        messages.append(assistant_message)

        if not turn.tool_calls:
            return turn.content.strip(), sources, delegations

        for tool_call in turn.tool_calls:
            call_id = str(uuid.uuid4())
            tool_name = tool_call["name"]
            arguments = tool_call["arguments"]

            skill = skills.get(tool_name)
            validation_error = ""
            if skill is None:
                validation_error = f"'{tool_name}' is not a registered skill. The agent must retry with a valid skill name."
            elif skill.parameters:
                validation_error = validate_arguments(arguments, skill.parameters)
            if validation_error:
                await emit(
                    "tool_error",
                    call_id=call_id,
                    run_id=run_id,
                    agent=agent,
                    tool=tool_name,
                    arguments=arguments,
                    reason=validation_error,
                )
                await emit(
                    "agent_status",
                    agent=agent,
                    phase="working",
                    label="Correcting course",
                    detail=f"Invalid tool call detected: {validation_error}",
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": tool_name,
                        "content": json.dumps({"ok": False, "error": validation_error}, ensure_ascii=True),
                        **( {"tool_call_id": tool_call.get("id")} if tool_call.get("id") else {}),
                    }
                )
                continue

            consent_broker.create(call_id, run_id)
            await emit(
                "agent_status",
                agent=agent,
                phase="working",
                label=f"Commissioning {tool_name}",
                detail=f"The agent needs its {tool_name} subagent.",
            )
            await emit(
                "tool_call",
                call_id=call_id,
                run_id=run_id,
                agent=agent,
                tool=tool_name,
                arguments=arguments,
            )
            await emit(
                "agent_status",
                agent=agent,
                phase="waiting",
                label="Waiting for permission",
                detail=f"The agent requested {tool_name}.",
            )
            approved, reason = await consent_broker.wait(call_id, APPROVAL_TIMEOUT_SECONDS)
            if approved:
                result = await skills.execute(tool_name, arguments)
            else:
                result = {"ok": False, "error": f"Tool request {reason}; no external call was executed."}
            result_sources = result.get("results", []) if isinstance(result, dict) else []
            if isinstance(result_sources, list):
                for result_item in result_sources:
                    if isinstance(result_item, dict) and all(isinstance(result_item.get(key), str) for key in ("title", "url", "snippet")):
                        if result_item not in sources:
                            sources.append(result_item)
            if collect_delegations:
                delegations.append(
                    {
                        "tool": tool_name,
                        "arguments": arguments,
                        "approved": approved,
                        "reason": reason,
                        "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
                        "error": result.get("error") if isinstance(result, dict) else "Invalid tool result",
                        "sources": result_sources if isinstance(result_sources, list) else [],
                    }
                )
            await emit(
                "tool_result",
                call_id=call_id,
                tool=tool_name,
                agent=agent,
                approved=approved,
                reason=reason,
                ok=bool(result.get("ok")) if isinstance(result, dict) else False,
                sources=result_sources if isinstance(result_sources, list) else [],
                error=result.get("error") if isinstance(result, dict) else "Invalid tool result",
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": json.dumps(result, ensure_ascii=True),
                    **( {"tool_call_id": tool_call.get("id")} if tool_call.get("id") else {}),
                }
            )
            if tool_name == "discuss" and isinstance(result, dict) and result.get("ok"):
                await emit(
                    "delegation_completed",
                    agent=agent,
                    tool=tool_name,
                    topic=result.get("topic", ""),
                    speeches=result.get("speeches", []),
                    synthesis=result.get("synthesis", ""),
                )

    return limit_message, sources, delegations


async def run_scout(request: OrchestrateRequest, run_id: str, emit: EventEmitter, history: list[Any]) -> ScoutResult:
    fallback_model = request.fallback_model.strip() or FALLBACK_MODEL
    brief, sources, _delegations = await run_agent_loop(
        request=request,
        run_id=run_id,
        emit=emit,
        history=history,
        agent="scout",
        build_messages=scout.build_messages,
        primary_model=request.scout_model.strip() or fallback_model,
        fallback_model=fallback_model,
        primary_provider_id=request.scout_provider_id.strip() or "ollama",
        fallback_provider_id=request.fallback_provider_id.strip() or "ollama",
        working_label="Scout is scanning",
        limit_message="The Scout reached the configured tool-call limit before producing a final brief.",
        collect_delegations=False,
    )
    return ScoutResult(brief=brief, sources=sources)


async def run_single_agent(
    request: OrchestrateRequest,
    run_id: str,
    emit: EventEmitter,
    history: list[Any],
) -> tuple[str, list[dict[str, Any]]]:
    fallback_model = request.fallback_model.strip() or FALLBACK_MODEL
    answer, _sources, delegations = await run_agent_loop(
        request=request,
        run_id=run_id,
        emit=emit,
        history=history,
        agent="main",
        build_messages=main_agent.build_messages,
        primary_model=request.synthesizer_model.strip() or fallback_model,
        fallback_model=fallback_model,
        primary_provider_id=request.synthesizer_provider_id.strip() or "ollama",
        fallback_provider_id=request.fallback_provider_id.strip() or "ollama",
        working_label="The AI is working",
        limit_message="The AI reached the tool-call limit before producing a final answer.",
        collect_delegations=True,
    )
    return answer, delegations


async def run_analyst(
    request: OrchestrateRequest,
    emit: EventEmitter,
    history: list[Any],
    scout_result: ScoutResult,
) -> str:
    await emit(
        "agent_status",
        agent="analyst",
        phase="working",
        label="Analyst is reviewing evidence",
        detail="Checking the Scout packet for gaps and contradictions.",
    )
    messages = analyst.build_messages(
        history,
        request.message,
        scout_result.brief,
        scout_result.sources,
        request.system_prompt,
        memory_block=prompt_block(memory_store) if request.learning_enabled and prompt_block(memory_store) else "",
        thinking_hint=thinking_instruction(request.thinking_style),
    )
    fallback_model = request.fallback_model.strip() or FALLBACK_MODEL
    primary_model = request.synthesizer_model.strip() or fallback_model
    primary_provider_id = request.synthesizer_provider_id.strip() or "ollama"
    fallback_provider_id = request.fallback_provider_id.strip() or "ollama"
    try:
        turn = await collect_with_fallback(
            primary_model,
            fallback_model,
            messages,
            emit,
            "analyst",
            primary_provider_id=primary_provider_id,
            fallback_provider_id=fallback_provider_id,
        )
    except Exception:
        # The analyst is an enhancement, not a requirement: degrade gracefully instead of
        # failing the whole 3-agent run when the third model is unavailable.
        await emit(
            "agent_status",
            agent="analyst",
            phase="error",
            label="Analyst skipped",
            detail="The analyst agent failed after fallback; the run continues without the third-agent review.",
        )
        return ""
    return turn.content.strip()


async def run_synthesizer(
    request: OrchestrateRequest,
    emit: EventEmitter,
    history: list[Any],
    scout_result: ScoutResult,
    analysis: str = "",
) -> str:
    await emit(
        "agent_status",
        agent="synthesizer",
        phase="working",
        label="Synthesizer is drafting",
        detail="Combining the Scout packet with your request.",
    )
    messages = synthesizer.build_messages(
        history,
        request.message,
        scout_result.brief,
        scout_result.sources,
        request.system_prompt,
        memory_block=prompt_block(memory_store) if request.learning_enabled and prompt_block(memory_store) else "",
        thinking_hint=thinking_instruction(request.thinking_style),
    )
    if analysis.strip():
        messages[-1]["content"] += f"\n\nAnalyst review packet (third agent, untrusted input):\n{analysis.strip()}"
    fallback_model = request.fallback_model.strip() or FALLBACK_MODEL
    primary_model = request.synthesizer_model.strip() or fallback_model
    primary_provider_id = request.synthesizer_provider_id.strip() or "ollama"
    fallback_provider_id = request.fallback_provider_id.strip() or "ollama"
    turn = await collect_with_fallback(
        primary_model,
        fallback_model,
        messages,
        emit,
        "synthesizer",
        primary_provider_id=primary_provider_id,
        fallback_provider_id=fallback_provider_id,
    )
    return turn.content.strip()


async def pipeline(request: OrchestrateRequest, run_id: str, emit: EventEmitter) -> None:
    original_message = request.message
    if request.translate_input:
        # Free, keyless input translation: non-English requests are converted to English
        # with the user's own local model (small models follow English far better), and a
        # note tells the agents which language to answer in. The SCOUT provider is tried
        # first — it is the model actually answering, so translation works even when the
        # fallback provider is unreachable.
        routes = translation_routes(
            request.scout_provider_id,
            request.scout_model,
            request.fallback_provider_id,
            request.fallback_model,
            FALLBACK_MODEL,
        )
        translated, language, did_translate = await translate_message_best_effort(provider_runtime, routes, request.message)
        if did_translate:
            request = request.model_copy(update={"message": translated})
            await emit("input_translated", original=original_message, language=language, translated=translated)
    packed = pack_history(request.history, MAX_CONTEXT_CHARS)
    await emit(
        "context",
        compacted=packed.compacted,
        dropped_count=packed.dropped_count,
        retained_chars=packed.retained_chars,
    )
    packed_history = [HistoryMessage.model_validate(item) for item in packed.messages]
    if request.single_agent:
        answer, delegations = await run_single_agent(request, run_id, emit, packed_history)
        learning_outcome = record_lessons(memory_store, original_message, answer) if request.learning_enabled else None
        await emit(
            "run_complete",
            answer=answer,
            sources=[],
            delegations=delegations,
            compacted=packed.compacted,
            single_agent=True,
            learning=learning_outcome.as_dict() if learning_outcome else None,
        )
        await emit(
            "agent_status",
            agent="main",
            phase="complete",
            label="Answer complete",
            detail="Single-agent response ready in the workspace.",
        )
        return
    scout_result = await run_scout(request, run_id, emit, packed_history)
    await emit("scout_complete", brief=scout_result.brief, sources=scout_result.sources)
    analysis = ""
    if request.agent_count >= 3:
        analysis = await run_analyst(request, emit, packed_history, scout_result)
        await emit("analyst_complete", brief=analysis)
    final_answer = await run_synthesizer(request, emit, packed_history, scout_result, analysis)
    learning_outcome = record_lessons(memory_store, original_message, final_answer) if request.learning_enabled else None
    await emit(
        "run_complete",
        answer=final_answer,
        sources=scout_result.sources,
        compacted=packed.compacted,
        learning=learning_outcome.as_dict() if learning_outcome else None,
    )
    await emit(
        "agent_status",
        agent="scout",
        phase="complete",
        label="Scout complete",
        detail=f"Collected {len(scout_result.sources)} source(s).",
    )
    await emit(
        "agent_status",
        agent="synthesizer",
        phase="complete",
        label="Synthesis complete",
        detail="Answer ready in the workspace.",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "local-agent-studio"}


fs_jail = PathJail(root=os.path.join(os.getcwd(), "projects"))
fs_settings = {"sandbox": "jailed", "auto_create_projects": True}
fs_pending: dict[str, Any] = {}


async def _fs_chat(messages: list[dict[str, str]]) -> str:
    chunks: list[str] = []
    async for chunk in provider_runtime.chat_stream(provider_id="ollama", model=FALLBACK_MODEL, messages=messages, tools=None, think=False):
        message = chunk.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            chunks.append(message["content"])
        if chunk.get("done") is True:
            break
    return "".join(chunks)


fs_team = FsAgentTeam(jail=fs_jail, chat_fn=_fs_chat)
github_service = GitHubService()


@app.get("/fs/settings")
async def fs_settings_get() -> dict[str, Any]:
    return {
        "ok": True,
        **fs_settings,
        "docker_available": fs_jail.docker_available(),
        "projects_root": str(fs_jail.root),
        "tools": [schema["name"] for schema in fs_team.all_schemas()],
    }


@app.post("/fs/settings")
async def fs_settings_post(request: FsSettingsRequest) -> dict[str, Any]:
    if request.sandbox not in {"jailed", "docker"}:
        raise HTTPException(status_code=422, detail="sandbox must be 'jailed' or 'docker'.")
    if request.sandbox == "docker" and not fs_jail.docker_available():
        raise HTTPException(status_code=409, detail="Docker is not available in this environment; the hardened path jail stays active.")
    fs_settings["sandbox"] = request.sandbox
    fs_settings["auto_create_projects"] = request.auto_create_projects
    return {"ok": True, **fs_settings, "docker_available": fs_jail.docker_available()}


@app.post("/fs/run")
async def fs_run(request: FsRunRequest) -> StreamingResponse:
    """Run the FS agent team; every real tool call pauses for browser consent."""
    run_id = str(uuid.uuid4())
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def emit(event_type: str, **payload: Any) -> None:
        await queue.put(event_payload(event_type, **payload))

    async def needs_consent(tool: str, arguments: dict[str, Any]) -> bool:
        fs_pending[run_id] = {"tool": tool, "arguments": arguments, "event": asyncio.Event(), "approved": None}
        await emit("fs_consent_required", run_id=run_id, tool=tool, arguments=arguments)
        pending = fs_pending[run_id]
        try:
            await asyncio.wait_for(pending["event"].wait(), timeout=APPROVAL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            pending["approved"] = False
        decision = bool(pending["approved"])
        await emit("fs_consent_result", run_id=run_id, tool=tool, approved=decision)
        fs_pending.pop(run_id, None)
        return decision

    async def worker() -> None:
        try:
            await fs_team.run(request.message, emit, needs_consent)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced to the browser
            await emit("fs_error", message=str(exc), run_id=run_id)
        finally:
            fs_pending.pop(run_id, None)
            await queue.put(None)

    task = asyncio.create_task(worker())

    async def stream() -> Any:
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item.encode("utf-8")
        finally:
            if not task.done():
                task.cancel()
            fs_pending.pop(run_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/fs/approve")
async def fs_approve(request: ApprovalRequest) -> dict[str, Any]:
    """Resolve a pending fs_consent_required for the run that owns call_id=run token."""
    pending = fs_pending.get(request.call_id)
    if pending is None:
        raise HTTPException(status_code=404, detail="No pending FS tool request for this run.")
    pending["approved"] = request.approved
    pending["event"].set()
    return {"ok": True}


@app.get("/providers")
async def providers() -> JSONResponse:
    return JSONResponse(content={"ok": True, "providers": [profile.public_dict() for profile in provider_store.list()]})


@app.post("/providers/detect")
async def detect_provider(request: ProviderDetectionRequest) -> JSONResponse:
    if not ALLOW_CUSTOM_PROVIDERS:
        raise HTTPException(
            status_code=403,
            detail="Custom provider management is disabled. Set ALLOW_CUSTOM_PROVIDERS=true to enable (security risk: allows arbitrary code execution and credential access)."
        )
    try:
        result = await provider_probe.detect(request.base_url, request.auth_env_var)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse(content={"ok": True, "result": result.model_dump()})


@app.post("/providers")
async def upsert_provider(request: ProviderUpsertRequest) -> JSONResponse:
    if not ALLOW_CUSTOM_PROVIDERS:
        raise HTTPException(
            status_code=403,
            detail="Custom provider management is disabled. Set ALLOW_CUSTOM_PROVIDERS=true to enable (security risk: allows arbitrary code execution and credential access)."
        )
    provider_id = (request.id or generated_provider_id(request.name)).strip().lower()
    if provider_id in {profile.id for profile in provider_store.list() if profile.builtin}:
        raise HTTPException(status_code=409, detail="Built-in provider profiles cannot be overwritten.")
    if request.kind == "custom_script" and not request.script.strip():
        raise HTTPException(status_code=422, detail="A custom script provider requires adapter source code.")
    try:
        profile = ProviderProfile(
            id=provider_id,
            name=request.name.strip(),
            description=request.description.strip(),
            kind=request.kind,
            base_url=request.base_url.strip(),
            auth_env_var=request.auth_env_var,
            models_path=request.models_path.strip(),
            chat_path=request.chat_path.strip(),
            default_model=request.default_model.strip(),
            script=request.script,
            allowed_hosts=request.allowed_hosts,
            capabilities={},
            builtin=False,
        )
        if profile.kind == "openai_compatible":
            profile.base_url = normalize_base_url(profile.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    saved = provider_store.upsert(profile)
    return JSONResponse(status_code=201, content={"ok": True, "provider": saved.public_dict()})


@app.get("/providers/{provider_id}/models")
async def provider_models(provider_id: str = Path(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")) -> JSONResponse:
    # Security check: prevent model discovery for custom providers when disabled
    if not ALLOW_CUSTOM_PROVIDERS:
        profile = provider_store.get(provider_id)
        if profile and not profile.builtin:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "models": [],
                    "error": "Custom provider model discovery is disabled. Set ALLOW_CUSTOM_PROVIDERS=true to enable (security risk: allows arbitrary code execution and credential access)."
                }
            )
    try:
        discovered = await provider_runtime.list_models(provider_id)
    except ProviderRuntimeError as exc:
        return JSONResponse(status_code=502, content={"ok": False, "models": [], "error": str(exc)})
    except Exception as exc:  # pragma: no cover - last-resort guard
        # Never let an unexpected error escape as a plain-text "Internal Server Error":
        # the frontend proxies parse the body as JSON and would surface a useless
        # "Unexpected token 'I' ... is not valid JSON" message instead of the real cause.
        return JSONResponse(status_code=502, content={"ok": False, "models": [], "error": f"Model discovery failed: {exc}"})
    return JSONResponse(content={"ok": True, "models": discovered})


@app.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str = Path(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")) -> JSONResponse:
    if not ALLOW_CUSTOM_PROVIDERS:
        raise HTTPException(
            status_code=403,
            detail="Custom provider management is disabled. Set ALLOW_CUSTOM_PROVIDERS=true to enable (security risk: allows arbitrary code execution and credential access)."
        )
    if provider_store.get(provider_id) is None:
        raise HTTPException(status_code=404, detail="Provider profile was not found.")
    if not provider_store.delete(provider_id):
        raise HTTPException(status_code=409, detail="Built-in provider profiles cannot be deleted.")
    return JSONResponse(content={"ok": True, "provider_id": provider_id})


@app.get("/models")
async def models() -> JSONResponse:
    try:
        discovered = await ollama.list_models()
    except OllamaError as exc:
        return JSONResponse(status_code=503, content={"ok": False, "models": [], "error": str(exc)})
    except Exception as exc:  # pragma: no cover - last-resort guard
        return JSONResponse(status_code=503, content={"ok": False, "models": [], "error": f"Ollama model discovery failed: {exc}"})
    return JSONResponse(content={"ok": True, "models": discovered})


@app.post("/approve-tool")
async def approve_tool(request: ApprovalRequest) -> dict[str, Any]:
    if not consent_broker.resolve(request.call_id, request.approved):
        raise HTTPException(status_code=404, detail="Tool request is missing, expired, or already resolved.")
    return {"ok": True, "call_id": request.call_id, "approved": request.approved}


@app.get("/learning")
async def learning_status() -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": learning_enabled["on"],
        "files": {name: memory_store.read(name) for name in ("learn", "rules", "agent")},
    }


@app.post("/learning")
async def learning_settings(request: LearningSettingsRequest) -> dict[str, Any]:
    learning_enabled["on"] = request.enabled
    return {"ok": True, "enabled": learning_enabled["on"]}


@app.put("/learning/files/{file_name}")
async def update_learning_file(file_name: str, request: LearningUpdateRequest) -> dict[str, Any]:
    if file_name != request.file:
        raise HTTPException(status_code=422, detail="File name in path and body must match.")
    try:
        memory_store.write(file_name, request.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "file": file_name}


@app.post("/learning/files/{file_name}/reset")
async def reset_learning_file(file_name: str) -> dict[str, Any]:
    try:
        memory_store.reset(file_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "file": file_name}


@app.get("/github/status")
async def github_status() -> dict[str, Any]:
    return {"ok": True, "configured": bool(github_service.token)}


@app.post("/github/repo")
async def github_repo(request: GitHubRepositoryRequest) -> dict[str, Any]:
    try:
        return {"ok": True, **(await github_service.repository(request.repository))}
    except GitHubServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/github/branch")
async def github_branch(request: GitHubBranchRequest) -> dict[str, Any]:
    try:
        return {"ok": True, **(await github_service.create_branch(request.repository, request.branch, request.from_sha))}
    except GitHubServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/github/pr")
async def github_pr(request: GitHubPullRequestRequest) -> dict[str, Any]:
    try:
        return {"ok": True, **(await github_service.create_pull_request(request.repository, request.title, request.body, request.head, request.base))}
    except GitHubServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def provider_problems(request: OrchestrateRequest) -> list[str]:
    """Validate the provider slots of a run request before anything executes."""
    problems: list[str] = []
    for provider_id, role in (
        (request.scout_provider_id.strip(), "Scout"),
        (request.synthesizer_provider_id.strip(), "Synthesizer"),
        (request.fallback_provider_id.strip(), "fallback route"),
    ):
        if not provider_id:
            continue
        if not provider_runtime.has_provider(provider_id):
            problems.append(provider_unconfigured_message(provider_id))
            continue
        # Security check: prevent use of custom providers when disabled
        if not ALLOW_CUSTOM_PROVIDERS:
            profile = provider_store.get(provider_id)
            if profile and not profile.builtin:
                problems.append(
                    f"{role} provider '{provider_id}' is a custom provider. "
                    "Custom providers are disabled for security. Set ALLOW_CUSTOM_PROVIDERS=true to enable "
                    "(security risk: allows arbitrary code execution and credential access)."
                )
    return problems


@app.post("/orchestrate")
async def orchestrate(request: OrchestrateRequest) -> StreamingResponse:
    run_id = str(uuid.uuid4())
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def emit(event_type: str, **payload: Any) -> None:
        await queue.put(event_payload(event_type, **payload))

    async def worker() -> None:
        await queue.put(event_payload("run_started", run_id=run_id))
        # Pre-flight provider check: a frontend-only provider (browser-webllm) or a
        # provider missing from the registry can never be answered server-side. Fail
        # fast with exactly ONE clear error instead of a confusing double report.
        problems = provider_problems(request)
        if problems:
            await emit("error", message="; ".join(problems), run_id=run_id, code="provider_not_configured")
            await queue.put(None)
            return
        try:
            await pipeline(request, run_id, emit)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await emit("error", message=str(exc), run_id=run_id)
        finally:
            consent_broker.cancel_run(run_id)
            await queue.put(None)

    task = asyncio.create_task(worker())

    async def stream() -> Any:
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item.encode("utf-8")
        finally:
            if not task.done():
                task.cancel()
            consent_broker.cancel_run(run_id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
