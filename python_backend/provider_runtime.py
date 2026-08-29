from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import ALLOWED_CREDENTIAL_ENV_VARS, OLLAMA_TIMEOUT_SECONDS, SCRIPT_TIMEOUT_SECONDS
from .provider_models import ProviderProfile, join_endpoint, validate_credential_transport_security
from .provider_probe import ProviderProbe
from .provider_store import ProviderStore


class ProviderRuntimeError(RuntimeError):
    """A user-safe provider runtime error."""


# Providers that only exist in the browser tab and can NEVER be reached by the server.
# The frontend must not send them to /orchestrate; if one arrives anyway, the backend
# reports a clear, actionable error instead of the generic "not configured" message.
BROWSER_ONLY_PROVIDER_IDS = frozenset({"browser-webllm"})


def is_browser_only_provider(provider_id: str) -> bool:
    return provider_id in BROWSER_ONLY_PROVIDER_IDS


class ProviderRuntime:
    def __init__(self, store: ProviderStore, timeout_seconds: float = OLLAMA_TIMEOUT_SECONDS) -> None:
        self.store = store
        self.timeout_seconds = timeout_seconds
        self.probe = ProviderProbe(timeout_seconds=min(timeout_seconds, 8.0))

    async def list_models(self, provider_id: str) -> list[dict[str, Any]]:
        profile = self._profile(provider_id)
        if profile.kind == "custom_script":
            return []
        headers = self._headers(profile)
        path = profile.models_path.strip()
        if not path:
            path = "/api/tags" if profile.kind == "ollama" else "/models"
        timeout = httpx.Timeout(self.timeout_seconds, connect=5.0)
        try:
            # URL building runs INSIDE the guard: an empty or malformed base_url raises
            # ValueError from normalize_base_url, which must surface as a user-safe
            # ProviderRuntimeError — never as a bare exception that escapes the endpoint
            # and turns into a plain-text "Internal Server Error" for the frontend.
            url = join_endpoint(profile.normalized_base_url(), path)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code >= 400:
                    detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                    raise ProviderRuntimeError(f"Provider rejected model discovery ({response.status_code}): {detail}")
                payload = response.json()
        except ProviderRuntimeError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRuntimeError(f"Model discovery failed for {profile.name}: {exc}") from exc

        if profile.kind == "ollama":
            models = payload.get("models", []) if isinstance(payload, dict) else []
        else:
            models = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(models, list):
            raise ProviderRuntimeError("Provider returned an invalid model list.")
        return [item for item in models if isinstance(item, dict) and (item.get("name") or item.get("id"))]

    async def chat_stream(
        self,
        provider_id: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        profile = self._profile(provider_id)
        if profile.kind == "ollama":
            async for event in self._ollama_stream(profile, model, messages, tools, think):
                yield event
            return
        if profile.kind == "openai_compatible":
            async for event in self._openai_stream(profile, model, messages, tools):
                yield event
            return
        if profile.kind == "custom_script":
            yield await self._script_call(profile, model, messages, tools)
            return
        raise ProviderRuntimeError(f"Unsupported provider kind: {profile.kind}")

    def has_provider(self, provider_id: str) -> bool:
        return self.store.get(provider_id) is not None

    def _profile(self, provider_id: str) -> ProviderProfile:
        profile = self.store.get(provider_id)
        if profile is None:
            raise ProviderRuntimeError(provider_unconfigured_message(provider_id))
        return profile

    @staticmethod
    def _headers(profile: ProviderProfile) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if profile.auth_env_var:
            # Security: Validate that the environment variable is in the approved allowlist.
            # This check is defense-in-depth; ProviderProfile validation should have already
            # rejected unauthorized variables, but we verify again at runtime.
            if profile.auth_env_var not in ALLOWED_CREDENTIAL_ENV_VARS:
                raise ProviderRuntimeError(
                    f"Environment variable '{profile.auth_env_var}' is not in the approved credential allowlist."
                )
            # Security: Enforce HTTPS when credentials are being transmitted
            validate_credential_transport_security(profile.base_url, profile.auth_env_var)
            
            token = os.getenv(profile.auth_env_var, "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _ollama_stream(
        self,
        profile: ProviderProfile,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        think: bool,
    ) -> AsyncIterator[dict[str, Any]]:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": True, "think": think}
        if tools:
            body["tools"] = tools
        url = join_endpoint(profile.normalized_base_url(), profile.chat_path or "/api/chat")
        timeout = httpx.Timeout(self.timeout_seconds, connect=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=body, headers=self._headers(profile)) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        raise ProviderRuntimeError(f"Ollama rejected the request ({response.status_code}): {detail}")
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ProviderRuntimeError("Ollama returned malformed streaming JSON.") from exc
                        if isinstance(chunk, dict) and chunk.get("error"):
                            raise ProviderRuntimeError(str(chunk["error"]))
                        if isinstance(chunk, dict):
                            yield chunk
        except ProviderRuntimeError:
            raise
        except (httpx.HTTPError, UnicodeError) as exc:
            raise ProviderRuntimeError(f"Ollama chat request failed: {exc}") from exc

    async def _openai_stream(
        self,
        profile: ProviderProfile,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> AsyncIterator[dict[str, Any]]:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            body["tools"] = tools
        url = join_endpoint(profile.normalized_base_url(), profile.chat_path or "/chat/completions")
        timeout = httpx.Timeout(self.timeout_seconds, connect=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=body, headers=self._headers(profile)) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        raise ProviderRuntimeError(f"Provider rejected the request ({response.status_code}): {detail}")
                    content_type = response.headers.get("content-type", "")
                    if "text/event-stream" not in content_type and "application/json" in content_type:
                        raw = await response.aread()
                        payload = json.loads(raw.decode("utf-8"))
                        yield self._openai_payload_to_event(payload, done=True)
                        return
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        event = self._parse_openai_line(line)
                        if event is not None:
                            yield event
        except ProviderRuntimeError:
            raise
        except (httpx.HTTPError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderRuntimeError(f"OpenAI-compatible chat request failed: {exc}") from exc

    @classmethod
    def _parse_openai_line(cls, line: str) -> dict[str, Any] | None:
        value = line.strip()
        if value.startswith("data:"):
            value = value[5:].strip()
        if value == "[DONE]":
            return {"message": {}, "done": True}
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return None
        return cls._openai_payload_to_event(payload, done=False)

    @staticmethod
    def _openai_payload_to_event(payload: dict[str, Any], done: bool) -> dict[str, Any]:
        choices = payload.get("choices") if isinstance(payload, dict) else []
        choice = choices[0] if isinstance(choices, list) and choices else {}
        delta = choice.get("delta") if isinstance(choice, dict) else {}
        delta = delta if isinstance(delta, dict) else {}
        message: dict[str, Any] = {}
        content = delta.get("content")
        if isinstance(content, str) and content:
            message["content"] = content
        reasoning = delta.get("reasoning_content") or delta.get("thinking")
        if isinstance(reasoning, str) and reasoning:
            message["thinking"] = reasoning
        tool_calls = delta.get("tool_calls")
        if isinstance(tool_calls, list):
            message["tool_calls"] = tool_calls
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        return {"message": message, "done": done or finish_reason is not None}

    async def _script_call(
        self,
        profile: ProviderProfile,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        executable = shutil.which("deno")
        if not executable:
            raise ProviderRuntimeError("Deno is required for custom provider scripts but was not found on PATH.")
        if not profile.script.strip():
            raise ProviderRuntimeError("Custom provider has no adapter script.")

        # Security: Validate credential variable and transport security before passing to script
        api_key = ""
        if profile.auth_env_var:
            if profile.auth_env_var not in ALLOWED_CREDENTIAL_ENV_VARS:
                raise ProviderRuntimeError(
                    f"Environment variable '{profile.auth_env_var}' is not in the approved credential allowlist."
                )
            validate_credential_transport_security(profile.base_url, profile.auth_env_var)
            api_key = os.getenv(profile.auth_env_var, "")
        
        input_payload = {
            "model": model,
            "messages": messages,
            "tools": tools or [],
            "base_url": profile.base_url,
            "api_key": api_key,
        }
        hosts = list(profile.allowed_hosts)
        if profile.base_url:
            try:
                from .provider_models import host_from_url

                base_host = host_from_url(profile.base_url)
                if base_host and base_host not in hosts:
                    hosts.append(base_host)
            except ValueError:
                pass

        with tempfile.TemporaryDirectory(prefix="agent-adapter-") as directory:
            script_path = os.path.join(directory, "adapter.ts")
            with open(script_path, "w", encoding="utf-8") as script_file:
                script_file.write(profile.script)
            command = [executable, "run", "--no-config", "--no-remote"]
            if hosts:
                command.append("--allow-net=" + ",".join(hosts))
            command.append(script_path)
            process: asyncio.subprocess.Process | None = None
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(json.dumps(input_payload, ensure_ascii=True).encode("utf-8")),
                    timeout=SCRIPT_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError as exc:
                if process is not None and process.returncode is None:
                    process.kill()
                    await process.wait()
                raise ProviderRuntimeError("Custom provider script timed out.") from exc
            except OSError as exc:
                raise ProviderRuntimeError(f"Could not start custom provider script: {exc}") from exc

        if process is None or process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[:500] if process is not None else "unknown Deno error"
            raise ProviderRuntimeError(f"Custom provider script failed: {detail or 'unknown Deno error'}")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderRuntimeError("Custom provider script must print one JSON response.") from exc
        if not isinstance(payload, dict):
            raise ProviderRuntimeError("Custom provider script returned an invalid response.")
        if payload.get("error"):
            raise ProviderRuntimeError(str(payload["error"]))
        event: dict[str, Any] = {"message": {}, "done": True}
        if isinstance(payload.get("content"), str):
            event["message"]["content"] = payload["content"]
        if isinstance(payload.get("thinking"), str):
            event["message"]["thinking"] = payload["thinking"]
        if isinstance(payload.get("tool_calls"), list):
            event["message"]["tool_calls"] = payload["tool_calls"]
        if not event["message"]:
            raise ProviderRuntimeError("Custom provider script returned no content or tool calls.")
        return event


def provider_unconfigured_message(provider_id: str) -> str:
    """User-facing explanation for a provider the backend cannot run."""
    if is_browser_only_provider(provider_id):
        return (
            f"The '{provider_id}' provider runs only inside the browser tab and cannot be used "
            "for a server-side run. Initialize the browser model and keep every agent route on "
            "'Browser local', or choose a configured server provider (for example Ollama) in "
            "Settings. The browser provider also cannot serve as the fallback route."
        )
    return (
        f"The provider '{provider_id}' is not configured in the registry. Open Settings → "
        "Providers to add it, or pick an already configured provider for this agent route."
    )
