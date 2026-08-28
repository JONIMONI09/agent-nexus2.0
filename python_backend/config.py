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
