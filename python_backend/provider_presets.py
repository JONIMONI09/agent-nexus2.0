from __future__ import annotations

from typing import Any


_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "id": "ollama",
        "name": "Ollama (local)",
        "kind": "ollama",
        "base_url": "http://localhost:11434",
        "description": "Native local Ollama API with model discovery and tool calling.",
        "auth_env_var": "",
        "default_model": "qwen3",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "kind": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "auth_env_var": "OPENAI_API_KEY",
        "default_model": "",
        "description": "OpenAI-compatible chat completions; credentials stay server-side.",
    },
    {
        "id": "groq",
        "name": "Groq Cloud",
        "kind": "openai_compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "auth_env_var": "GROQ_API_KEY",
        "default_model": "",
        "description": "Low-latency open-model inference through an OpenAI-shaped API.",
    },
    {
        "id": "fireworks",
        "name": "Fireworks AI",
        "kind": "openai_compatible",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "auth_env_var": "FIREWORKS_API_KEY",
        "default_model": "",
        "description": "Hosted open-model inference through an OpenAI-shaped API.",
    },
    {
        "id": "litellm",
        "name": "LiteLLM gateway",
        "kind": "openai_compatible",
        "base_url": "http://localhost:4000/v1",
        "auth_env_var": "LITELLM_MASTER_KEY",
        "default_model": "",
        "description": "Self-hosted gateway for Anthropic, Gemini, OpenAI, Groq, Ollama, and more.",
    },
    {
        "id": "custom-openai",
        "name": "Custom OpenAI-compatible URL",
        "kind": "openai_compatible",
        "base_url": "",
        "auth_env_var": "",
        "default_model": "",
        "description": "vLLM, LM Studio, Together, proxies, or any compatible /models endpoint.",
    },
    {
        "id": "custom-script",
        "name": "Custom Deno adapter",
        "kind": "custom_script",
        "base_url": "",
        "auth_env_var": "",
        "default_model": "",
        "description": "A user-owned TypeScript adapter executed with explicit network permissions.",
    },
)


def provider_presets() -> list[dict[str, Any]]:
    return [dict(item) for item in _PRESETS]
