from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT_SECONDS


class OllamaError(RuntimeError):
    """A user-safe error raised for local Ollama connectivity or API failures."""


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, timeout_seconds: float = OLLAMA_TIMEOUT_SECONDS) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def list_models(self) -> list[dict[str, Any]]:
        timeout = httpx.Timeout(self.timeout_seconds, connect=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OllamaError(f"Ollama model discovery failed: {exc}") from exc

        models = payload.get("models", [])
        if not isinstance(models, list):
            raise OllamaError("Ollama returned an invalid model list.")
        return [model for model in models if isinstance(model, dict) and isinstance(model.get("name"), str)]

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": think,
        }
        if tools:
            body["tools"] = tools

        timeout = httpx.Timeout(self.timeout_seconds, connect=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=body,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        raise OllamaError(f"Ollama rejected the request ({response.status_code}): {detail}")
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise OllamaError("Ollama returned malformed streaming JSON.") from exc
                        if isinstance(chunk, dict) and chunk.get("error"):
                            raise OllamaError(str(chunk["error"]))
                        if isinstance(chunk, dict):
                            yield chunk
        except OllamaError:
            raise
        except (httpx.HTTPError, UnicodeError) as exc:
            raise OllamaError(f"Ollama chat request failed: {exc}") from exc
