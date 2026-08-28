"""Free, keyless input translation backed by the user's own local models.

When "Auto-translate" is enabled, non-English messages are translated to English
before the agent run so small local models work with the language they handle best.
The answer language stays the user's own: agents receive a short note telling them
which language the user wrote in.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable

from .ollama_client import OllamaError
from .provider_runtime import BROWSER_ONLY_PROVIDER_IDS, ProviderRuntime, ProviderRuntimeError

TRANSLATION_TIMEOUT_SECONDS = 20.0

TRANSLATE_SYSTEM_PROMPT = (
    "You are a translation engine. Translate the user's text into natural English. "
    "Preserve meaning, tone, technical terms, URLs, file paths and code identifiers. "
    "Output ONLY the translation — no preamble, no quotes, no notes, no explanations. "
    "If the text is already English, output it unchanged."
)

# Script-level detection: if the text uses a non-Latin script it is definitely not English.
_SCRIPT_TESTS: tuple[tuple[str, str], ...] = (
    ("Cyrillic", r"[\u0400-\u04FF]"),
    ("Greek", r"[\u0370-\u03FF]"),
    ("Arabic", r"[\u0600-\u06FF]"),
    ("Hebrew", r"[\u0590-\u05FF]"),
    ("Chinese", r"[\u4E00-\u9FFF]"),
    ("Japanese", r"[\u3040-\u30FF]"),
    ("Korean", r"[\uAC00-\uD7AF]"),
    ("Thai", r"[\u0E00-\u0E7F]"),
)

# Latin-script languages: distinctive letters plus high-signal stop words.
_LATIN_HINTS: tuple[tuple[str, str], ...] = (
    ("German", r"\u00e4|\u00f6|\u00fc|\u00df|der |die |das |und |nicht |ist |ich |bitte |danke |schreibe|mache|funktioniert|warum |wie kann "),
    ("French", r"\u00e9|\u00e8|\u00e7|\u00e0| le | la | les | une | des |est |pour |avec |pas les|je |nous |pourquoi |comment "),
    ("Spanish", r"\u00f1|\u00bf|\u00a1| el | los | las | una | para | con | que |es |por favor|gracias|por qu\u00e9|c\u00f3mo "),
    ("Italian", r" il | lo | gli | una | per | con | che | non | sono | perch\u00e9|grazie|come "),
    ("Portuguese", r"\u00e3|\u00e7| os | as | uma | para | com | que | n\u00e3o |est\u00e1|por favor|obrigado|por que|como "),
    ("Dutch", r" het | een | niet | zijn | met | voor | waarom |hoe kan |alsjeblieft|dank "),
    ("Polish", r" nie | jest | si\u0119| dla | jak | dlaczego|prosz\u0119|dzi\u0119k"),
    ("Turkish", r" bir | i\u00e7in | de\u011fil| nas\u0131l| neden |l\u00fctfen|te\u015fekk\u00fcr"),
    ("Russian (latin)", r" chto | kak | pochemu|pozhaluysta|spasibo"),
)

ENGLISH_MARKERS = re.compile(
    r"\b(the|and|is|are|you|please|thanks|how|what|why|can|could|would|should|need|want|help|make|write|find|explain|build)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> tuple[bool, str]:
    """Return (is_non_english, language_name). Heuristic, fast, no network."""
    sample = f" {text.strip().lower()} "
    for name, pattern in _SCRIPT_TESTS:
        if re.search(pattern, text):
            return True, name
    for name, pattern in _LATIN_HINTS:
        if re.search(pattern, sample):
            # Umlaut words like "f\u00fcr" are strong; bare hints need an English-marker miss
            # to avoid flagging English text that merely contains " die " inside a word.
            if not ENGLISH_MARKERS.search(text) or re.search(r"[\u00e4\u00f6\u00fc\u00df\u00e9\u00e8\u00e7\u00f1\u00e3\u00bf\u00e0]", text):
                return True, name
    return False, "English"


def language_note(language: str, translated: str) -> str:
    """Suffix added to the translated message so agents answer in the user's language."""
    if language == "English":
        return translated
    return (
        f"{translated}\n\n"
        f"[Context note: the user wrote the original message in {language}. "
        f"Reply in {language}. The text above is its English translation for your processing.]"
    )


async def _collect_plain(stream: Any) -> str:
    chunks: list[str] = []
    async for chunk in stream:
        message = chunk.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            chunks.append(message["content"])
        if chunk.get("done") is True:
            break
    return "".join(chunks)


async def translate_message(
    runtime: ProviderRuntime,
    provider_id: str,
    model: str,
    text: str,
) -> tuple[str, str, bool]:
    """Translate `text` to English via the local model. Returns (final_text, language, translated).

    Never raises: on any failure the original text is returned unchanged — translation
    is an enhancement, the run must go through regardless.
    """
    is_non_english, language = detect_language(text)
    if not is_non_english or not text.strip():
        return text, language, False
    try:
        stream = runtime.chat_stream(
            provider_id=provider_id,
            model=model,
            messages=[
                {"role": "system", "content": TRANSLATE_SYSTEM_PROMPT},
                {"role": "user", "content": text[:4000]},
            ],
            tools=None,
            think=False,
        )
        translated = (await asyncio.wait_for(_collect_plain(stream), timeout=TRANSLATION_TIMEOUT_SECONDS)).strip()
    except (OllamaError, ProviderRuntimeError, asyncio.TimeoutError, Exception):  # noqa: BLE001 - translation must never break a run
        return text, language, False
    if not translated or len(translated) > max(len(text) * 6, 4000):
        # Empty or implausible output (model babbled) — fall back to the original.
        return text, language, False
    return language_note(language, translated), language, True


def translation_routes(
    scout_provider_id: str,
    scout_model: str,
    fallback_provider_id: str,
    fallback_model: str,
    default_fallback_model: str,
) -> list[tuple[str, str]]:
    """Ordered (provider_id, model) routes: the ANSWERING scout provider first, the
    fallback provider second, deduplicated. Translation must use the model the run
    actually talks to, or it silently fails on browser-only setups."""
    routes = [
        (
            scout_provider_id.strip() or "ollama",
            scout_model.strip() or fallback_model.strip() or default_fallback_model,
        )
    ]
    fallback_route = (fallback_provider_id.strip() or "ollama", fallback_model.strip() or default_fallback_model)
    if fallback_route not in routes:
        routes.append(fallback_route)
    # Browser-only providers (browser-webllm) cannot be reached by the server: the browser
    # translates client-side with its own engine, so these routes are skipped entirely.
    routes = [route for route in routes if route[0] not in BROWSER_ONLY_PROVIDER_IDS]
    if not routes:
        routes = [("ollama", default_fallback_model)]
    return routes


async def translate_message_best_effort(
    runtime: ProviderRuntime,
    routes: list[tuple[str, str]],
    text: str,
) -> tuple[str, str, bool]:
    """Try translation through each (provider_id, model) route in order.

    The FIRST route should be the provider the run actually answers with (scout),
    so translation works even when the fallback provider is unreachable. Never raises.
    """
    is_non_english, language = detect_language(text)
    if not is_non_english or not text.strip():
        return text, language, False
    for provider_id, model in routes:
        result, _lang, translated = await translate_message(runtime, provider_id, model, text)
        if translated:
            return result, _lang, True
    return text, language, False
