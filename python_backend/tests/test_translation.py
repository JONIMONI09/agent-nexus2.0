"""Tests for the free, keyless auto-translate layer."""
from __future__ import annotations

import asyncio

from python_backend import translate
from python_backend.translate import detect_language, language_note, translate_message


class _FakeRuntime:
    """Provider-runtime stand-in returning a canned translation."""

    def __init__(self, output: str) -> None:
        self._output = output
        self.calls: list[dict[str, object]] = []

    def chat_stream(self, provider_id: str, model: str, messages, tools=None, think=True, **kwargs):
        self.calls.append({"provider_id": provider_id, "model": model, "messages": messages})
        async def stream(**kwargs):
            yield {"message": {"content": self._output}, "done": True}
        return stream()


class _BrokenRuntime:
    def chat_stream(self, provider_id: str, model: str, messages, tools=None, think=True, **kwargs):
        async def stream(**kwargs):
            raise RuntimeError("provider dead")
            yield {}  # pragma: no cover - makes this an async generator
        return stream()


def test_german_is_detected_as_non_english() -> None:
    is_non_english, language = detect_language("Wie kann ich die Fehlermeldung beheben? Danke!")
    assert is_non_english is True
    assert language == "German"


def test_german_greeting_is_not_mistaken_for_spanish() -> None:
    # Regression: "geht es dir" used to match the Spanish hint " es " (the German word
    # "it"), so this plain German greeting was reported as Spanish.
    is_non_english, language = detect_language("Hallo wie geht es dir ?")
    assert is_non_english is True
    assert language == "German"


def test_german_es_is_not_spanish() -> None:
    is_non_english, language = detect_language("Es geht mir gut, und dir?")
    assert is_non_english is True
    assert language == "German"


def test_spanish_uses_distinctive_markers() -> None:
    is_non_english, language = detect_language("¿Qué tal? ¡Hola!")
    assert is_non_english is True
    assert language == "Spanish"


def test_english_is_detected_as_english() -> None:
    is_non_english, language = detect_language("How can I fix this error message please?")
    assert is_non_english is False
    assert language == "English"


def test_cyrillic_script_is_detected() -> None:
    is_non_english, language = detect_language("Как исправить эту ошибку?")
    assert is_non_english is True
    assert language == "Cyrillic"


def test_language_note_tells_agents_to_answer_in_user_language() -> None:
    note = language_note("German", "How can I fix it?")
    assert "How can I fix it?" in note
    assert "Reply in German" in note


def test_translate_message_translates_and_notes_language() -> None:
    runtime = _FakeRuntime("How do I fix the error message?")
    final, language, translated = asyncio.run(
        translate_message(runtime, "ollama", "qwen2.5:3b", "Wie behebe ich die Fehlermeldung?")
    )
    assert translated is True
    assert language == "German"
    assert final.startswith("How do I fix the error message?")
    assert "Reply in German" in final
    assert runtime.calls[0]["model"] == "qwen2.5:3b"


def test_english_input_is_passed_through_without_model_call() -> None:
    runtime = _FakeRuntime("should never be called")
    final, language, translated = asyncio.run(
        translate_message(runtime, "ollama", "qwen2.5:3b", "This is already English.")
    )
    assert translated is False
    assert language == "English"
    assert final == "This is already English."
    assert runtime.calls == []


def test_failed_translation_returns_original_message() -> None:
    final, language, translated = asyncio.run(
        translate_message(_BrokenRuntime(), "ollama", "qwen2.5:3b", "Wie behebe ich die Fehlermeldung?")
    )
    assert translated is False
    assert language == "German"
    assert final == "Wie behebe ich die Fehlermeldung?"


def test_implausible_translation_output_is_rejected() -> None:
    runtime = _FakeRuntime("x" * 10_000)
    final, _language, translated = asyncio.run(
        translate_message(runtime, "ollama", "qwen2.5:3b", "Wie behebe ich die Fehlermeldung?")
    )
    assert translated is False
    assert final == "Wie behebe ich die Fehlermeldung?"


def test_echo_output_is_rejected_as_not_a_translation() -> None:
    runtime = _FakeRuntime("Wie behebe ich die Fehlermeldung?")
    final, language, translated = asyncio.run(
        translate_message(runtime, "ollama", "qwen2.5:3b", "Wie behebe ich die Fehlermeldung?")
    )
    assert translated is False
    assert language == "German"
    assert final == "Wie behebe ich die Fehlermeldung?"


def test_wrapped_echo_output_is_rejected() -> None:
    runtime = _FakeRuntime('Here is the translation: "Wie behebe ich die Fehlermeldung?"')
    final, _language, translated = asyncio.run(
        translate_message(runtime, "ollama", "qwen2.5:3b", "Wie behebe ich die Fehlermeldung?")
    )
    assert translated is False
    assert final == "Wie behebe ich die Fehlermeldung?"


def test_repeated_word_babble_is_rejected() -> None:
    runtime = _FakeRuntime("yes yes yes yes yes yes")
    final, _language, translated = asyncio.run(
        translate_message(runtime, "ollama", "qwen2.5:3b", "Wie behebe ich die Fehlermeldung?")
    )
    assert translated is False
    assert final == "Wie behebe ich die Fehlermeldung?"


def test_repeating_trigram_loop_is_rejected() -> None:
    runtime = _FakeRuntime("hello there friend hello there friend hello there friend")
    final, _language, translated = asyncio.run(
        translate_message(runtime, "ollama", "qwen2.5:3b", "Wie behebe ich die Fehlermeldung?")
    )
    assert translated is False
    assert final == "Wie behebe ich die Fehlermeldung?"


def test_sane_translation_passes_plausibility_check() -> None:
    runtime = _FakeRuntime("How can I fix this error message?")
    final, language, translated = asyncio.run(
        translate_message(runtime, "ollama", "qwen2.5:3b", "Wie behebe ich diese Fehlermeldung?")
    )
    assert translated is True
    assert language == "German"
    assert final.startswith("How can I fix this error message?")
