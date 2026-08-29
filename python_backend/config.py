from __future__ import annotations

import os


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_TIMEOUT_SECONDS = env_float("OLLAMA_TIMEOUT_SECONDS", 90.0)
APPROVAL_TIMEOUT_SECONDS = env_float("APPROVAL_TIMEOUT_SECONDS", 300.0)
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "18000"))
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "3"))
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "qwen2.5:3b")
STATE_DB_PATH = os.getenv("AGENT_STATE_DB", ".local_agent_studio/state.db")
SCRIPT_TIMEOUT_SECONDS = env_float("SCRIPT_TIMEOUT_SECONDS", 8.0)
PROVIDER_PROBE_TIMEOUT_SECONDS = env_float("PROVIDER_PROBE_TIMEOUT_SECONDS", 5.0)
# If a provider streams nothing for this long, the turn is considered stalled and the
# fallback engine retries with the fallback model (collect_with_fallback handles it).
GENERATION_STALL_TIMEOUT_SECONDS = env_float("GENERATION_STALL_TIMEOUT_SECONDS", 45.0)

# Security: Allowlist of environment variables that may be used for provider credentials.
# This prevents credential exfiltration attacks where an attacker could probe arbitrary
# environment variables and send their values to attacker-controlled endpoints.
# Only explicitly approved credential variable names are permitted.
ALLOWED_CREDENTIAL_ENV_VARS = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "FIREWORKS_API_KEY",
        "TOGETHER_API_KEY",
        "DEEPSEEK_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "REPLICATE_API_TOKEN",
        "HUGGINGFACE_API_KEY",
        "LITELLM_MASTER_KEY",
        "OPENROUTER_API_KEY",
        "PERPLEXITY_API_KEY",
        "AI21_API_KEY",
        "ANYSCALE_API_KEY",
        "BASETEN_API_KEY",
        "CLOUDFLARE_API_KEY",
        "VOYAGE_API_KEY",
        "WRITER_API_KEY",
    }
)
