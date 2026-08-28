"""Tests for the provider-configuration guard rails.

Regression scope: the frontend-only provider ``browser-webllm`` used to reach the
backend and surface as a cryptic, doubled ``Provider 'browser-webllm' is not
configured.`` error. These tests pin down the new behavior: actionable messages,
fail-fast fallback logic, no duplicated error text, and exactly one error event.
"""

from __future__ import annotations

import asyncio
import json
import tempfile

import httpx
import pytest

from python_backend import main
from python_backend.ollama_client import OllamaError
from python_backend.provider_runtime import (
    ProviderRuntime,
    ProviderRuntimeError,
    is_browser_only_provider,
    provider_unconfigured_message,
)
from python_backend.provider_store import ProviderStore
from python_backend.translate import translation_routes
from python_backend.types import OrchestrateRequest


def _isolated_runtime() -> ProviderRuntime:
    return ProviderRuntime(ProviderStore(path=f"{tempfile.mkdtemp()}/state.db"))


def test_browser_provider_message_is_actionable_and_single() -> None:
    message = provider_unconfigured_message("browser-webllm")
    assert "browser" in message
    # The provider id must appear exactly once — the old bug duplicated the whole text.
    assert message.count("browser-webllm") == 1
    assert is_browser_only_provider("browser-webllm") is True
    assert is_browser_only_provider("ollama") is False


def test_provider_runtime_browser_profile_raises_actionable_error() -> None:
    runtime = _isolated_runtime()
    assert runtime.has_provider("browser-webllm") is False
    assert runtime.has_provider("ollama") is False  # empty store
    with pytest.raises(ProviderRuntimeError) as excinfo:
        runtime._profile("browser-webllm")
    assert "browser" in str(excinfo.value)
    assert str(excinfo.value).count("browser-webllm") == 1


def test_collect_with_fallback_unknown_primary_fails_fast(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    attempted: list[str] = []

    async def fake_collect_turn(model, messages, emit, agent, tools=None, think=True, provider_id="ollama"):
        attempted.append(provider_id)
        raise AssertionError("collect_turn must never run for an unknown primary provider")

    def fake_has_provider(provider_id: str) -> bool:
        return provider_id != "browser-webllm"

    monkeypatch.setattr(main, "collect_turn", fake_collect_turn)
    monkeypatch.setattr(main.provider_runtime, "has_provider", fake_has_provider)

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    with pytest.raises(OllamaError) as excinfo:
        asyncio.run(
            main.collect_with_fallback(
                "model",
                "fallback",
                [],
                emit,
                "scout",
                primary_provider_id="browser-webllm",
                fallback_provider_id="ollama",
            )
        )

    message = str(excinfo.value)
    assert "browser" in message
    assert message.count("browser-webllm") == 1
    assert attempted == []
    assert events == []


def test_collect_with_fallback_unknown_fallback_is_never_attempted(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    attempts: list[str] = []

    async def fake_collect_turn(model, messages, emit, agent, tools=None, think=True, provider_id="ollama"):
        attempts.append(provider_id)
        if model == "primary":
            raise RuntimeError("primary down")
        return main.Turn(content="ok", model=model)

    def fake_has_provider(provider_id: str) -> bool:
        return provider_id != "browser-webllm"

    monkeypatch.setattr(main, "collect_turn", fake_collect_turn)
    monkeypatch.setattr(main.provider_runtime, "has_provider", fake_has_provider)

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    with pytest.raises(OllamaError) as excinfo:
        asyncio.run(
            main.collect_with_fallback(
                "primary",
                "fallback",
                [],
                emit,
                "scout",
                primary_provider_id="ollama",
                fallback_provider_id="browser-webllm",
            )
        )

    message = str(excinfo.value)
    assert "not configured" in message
    assert "browser-webllm" in message
    assert attempts == ["ollama"], "only the known primary may be attempted"
    assert events == [], "no redundant fallback events may be emitted for an unknown fallback"


def test_translation_routes_skip_browser_only_providers() -> None:
    default = "qwen2.5:3b"
    assert translation_routes("browser-webllm", "SmolLM2-360M-Instruct-q4f16_1-MLC", "ollama", "qwen3", default) == [("ollama", "qwen3")]
    assert translation_routes("browser-webllm", "m1", "browser-webllm", "m2", default) == [("ollama", default)]
    assert translation_routes("ollama", "qwen3", "browser-webllm", "m2", default) == [("ollama", "qwen3")]
    assert translation_routes("", "", "", "", default) == [("ollama", default)]


def test_provider_problems_flags_browser_and_unknown_slots() -> None:
    problems = main.provider_problems(
        OrchestrateRequest(
            message="hi",
            scout_provider_id="browser-webllm",
            synthesizer_provider_id="browser-webllm",
            fallback_provider_id="browser-webllm",
        )
    )
    assert len(problems) == 3
    assert all("browser" in problem for problem in problems)
    assert all(problem.count("browser-webllm") == 1 for problem in problems)

    problems = main.provider_problems(OrchestrateRequest(message="hi", scout_provider_id="no-such-provider"))
    assert len(problems) == 1
    assert "no-such-provider" in problems[0]

    assert main.provider_problems(OrchestrateRequest(message="hi")) == []


def test_orchestrate_stream_emits_exactly_one_error_for_browser_provider() -> None:
    async def run() -> tuple[list[str], list[str]]:
        transport = httpx.ASGITransport(app=main.app)
        errors: list[str] = []
        types: list[str] = []
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/orchestrate",
                json={"message": "hi", "scout_provider_id": "browser-webllm", "synthesizer_provider_id": "ollama"},
            ) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = json.loads(line[5:].strip())
                    types.append(payload.get("type", ""))
                    if payload.get("type") == "error":
                        errors.append(payload.get("message", ""))
        return types, errors

    types, errors = asyncio.run(run())
    assert types == ["run_started", "error"], "the run must fail fast with a single error"
    assert len(errors) == 1
    assert "browser" in errors[0]
    assert errors[0].count("browser-webllm") == 1
