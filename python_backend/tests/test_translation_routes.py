"""Tests for translation route priority: the answering provider is tried first."""
from __future__ import annotations

import asyncio

from python_backend.translate import detect_language, translation_routes, translate_message_best_effort


class _RoutedRuntime:
    """Fails for one provider, translates for another — routes must be tried in order."""

    def __init__(self, dead_provider: str, translation: str) -> None:
        self._dead = dead_provider
        self._translation = translation
        self.tried: list[str] = []

    def chat_stream(self, provider_id: str, model: str, messages, tools=None, think=True, **kwargs):
        self.tried.append(provider_id)

        async def stream(**kwargs):
            if provider_id == self._dead:
                raise RuntimeError(f"provider {provider_id} unreachable")
            yield {"message": {"content": self._translation}, "done": True}

        return stream()


def test_scout_provider_is_the_first_translation_route() -> None:
    routes = translation_routes("my-openai-server", "qwen3", "ollama", "qwen2.5:3b", "qwen2.5:3b")
    assert routes == [("my-openai-server", "qwen3"), ("ollama", "qwen2.5:3b")]


def test_fallback_route_is_dropped_when_identical_to_scout() -> None:
    assert translation_routes("ollama", "qwen3", "ollama", "qwen3", "qwen2.5:3b") == [("ollama", "qwen3")]


def test_empty_fields_default_to_ollama_and_default_model() -> None:
    assert translation_routes("", "", "", "", "qwen2.5:3b") == [("ollama", "qwen2.5:3b")]


def test_dead_primary_provider_falls_through_to_second_route() -> None:
    runtime = _RoutedRuntime("ollama", "How do I fix the error?")
    final, language, translated = asyncio.run(translate_message_best_effort(runtime, [("ollama", "qwen3"), ("my-openai-server", "qwen2.5:3b")], "Wie behebe ich die Fehlermeldung?"))
    assert translated is True
    assert language == "German"
    assert final.startswith("How do I fix the error?")
    assert runtime.tried == ["ollama", "my-openai-server"]


def test_all_routes_dead_returns_original_silently() -> None:
    runtime = _RoutedRuntime("ollama", "unused")
    original = "Wie behebe ich die Fehlermeldung?"
    final, language, translated = asyncio.run(translate_message_best_effort(runtime, [("ollama", "qwen3"), ("ollama", "qwen2.5:3b")], original))
    assert translated is False
    assert language == "German"
    assert final == original
    assert detect_language(original) == (True, "German")
