"""Stall-watchdog tests: hung providers must trigger the fallback engine, never hang."""
from __future__ import annotations

import asyncio

import pytest

from python_backend import main


class _StubRuntime:
    """Minimal provider_runtime stand-in with per-model stream routes."""

    def __init__(self, routes: dict[str, object]) -> None:
        self._routes = routes
        self.calls: list[str] = []

    def chat_stream(self, provider_id: str, model: str, messages, tools=None, think=True, **kwargs):
        self.calls.append(model)
        factory = self._routes[model]
        assert factory is not None, f"no stream route for {model}"
        return factory()

    def has_provider(self, provider_id: str) -> bool:
        return True


def _hanging_stream():
    async def stream(**kwargs):
        await asyncio.sleep(3600)
        yield {"message": {"content": "never"}, "done": True}  # pragma: no cover

    return stream()


def _content_stream(text: str):
    async def stream(**kwargs):
        yield {"message": {"content": text}, "done": True}

    return stream()


def test_collect_turn_raises_on_stalled_provider(monkeypatch) -> None:
    """A provider that never streams a chunk must raise instead of hanging forever."""
    monkeypatch.setattr(main, "GENERATION_STALL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(main, "provider_runtime", _StubRuntime({"primary": lambda: _hanging_stream()}))

    async def emit(event_type: str, **payload: object) -> None:
        return None

    with pytest.raises(main.OllamaError, match="stalled"):
        asyncio.run(
            main.collect_turn("primary", [{"role": "user", "content": "hi"}], emit, "scout", provider_id="test")
        )


def test_stalled_primary_falls_back_to_fallback_model(monkeypatch) -> None:
    """Stall on the primary model must transparently retry on the fallback model."""
    monkeypatch.setattr(main, "GENERATION_STALL_TIMEOUT_SECONDS", 0.05)
    runtime = _StubRuntime(
        {
            "primary": lambda: _hanging_stream(),
            "fallback": lambda: _content_stream("rescued answer"),
        }
    )
    monkeypatch.setattr(main, "provider_runtime", runtime)

    events: list[tuple[str, dict[str, object]]] = []

    async def emit(event_type: str, **payload: object) -> None:
        events.append((event_type, payload))

    turn = asyncio.run(
        main.collect_with_fallback(
            "primary",
            "fallback",
            [],
            emit,
            "scout",
            primary_provider_id="test",
            fallback_provider_id="test",
        )
    )

    assert turn.content == "rescued answer"
    assert runtime.calls == ["primary", "fallback"]
    assert any(event_type == "fallback" for event_type, _payload in events)


def test_slow_but_alive_stream_is_not_flagged_as_stalled(monkeypatch) -> None:
    """Chunks arriving within the stall window must stream normally."""
    monkeypatch.setattr(main, "GENERATION_STALL_TIMEOUT_SECONDS", 1.0)

    async def slow_stream(**kwargs):
        for word in ["hello ", "world"]:
            await asyncio.sleep(0.01)
            yield {"message": {"content": word}}

    monkeypatch.setattr(main, "provider_runtime", _StubRuntime({"primary": lambda: slow_stream()}))

    async def emit(event_type: str, **payload: object) -> None:
        return None

    turn = asyncio.run(
        main.collect_turn("primary", [{"role": "user", "content": "hi"}], emit, "main", provider_id="test")
    )

    assert turn.content == "hello world"
