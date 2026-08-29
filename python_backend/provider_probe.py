from __future__ import annotations

from typing import Any

import httpx

from .config import ALLOWED_CREDENTIAL_ENV_VARS
from .provider_models import (
    ProviderDetectionResult,
    ProviderProfile,
    host_from_url,
    join_endpoint,
    normalize_base_url,
    validate_credential_transport_security,
)


class ProviderProbeError(RuntimeError):
    """A safe, user-facing provider probe failure."""


class ProviderProbe:
    def __init__(self, timeout_seconds: float = 5.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _headers(self, auth_env_var: str) -> dict[str, str]:
        import os

        # Security: Validate that the environment variable is in the approved allowlist
        # to prevent credential exfiltration attacks.
        if auth_env_var and auth_env_var not in ALLOWED_CREDENTIAL_ENV_VARS:
            raise ProviderProbeError(
                f"Environment variable '{auth_env_var}' is not in the approved credential allowlist. "
                f"Permitted variables: {', '.join(sorted(ALLOWED_CREDENTIAL_ENV_VARS))}"
            )
        
        token = os.getenv(auth_env_var, "") if auth_env_var else ""
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    async def detect(self, base_url: str, auth_env_var: str = "") -> ProviderDetectionResult:
        # Security: Enforce HTTPS when credentials are being transmitted
        validate_credential_transport_security(base_url, auth_env_var)
        
        normalized = normalize_base_url(base_url)
        checked: list[str] = []
        timeout = httpx.Timeout(self.timeout_seconds, connect=2.0)
        headers = self._headers(auth_env_var)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, transport=self.transport) as client:
            ollama_url = join_endpoint(normalized, "/api/tags")
            checked.append(ollama_url)
            try:
                response = await client.get(ollama_url, headers=headers)
                payload = self._json_or_empty(response)
                if response.status_code == 200 and isinstance(payload.get("models"), list):
                    models = self._model_names(payload.get("models"))
                    return ProviderDetectionResult(
                        detected=True,
                        kind="ollama",
                        normalized_base_url=normalized,
                        name_suggestion="Ollama",
                        models=models,
                        capabilities={"model_discovery": True, "streaming": True, "tools": True, "thinking": True},
                        status_code=response.status_code,
                        message="Ollama API detected.",
                        checked_urls=checked,
                    )
            except httpx.HTTPError:
                pass

            openai_paths = ["/models"]
            if not normalized.endswith("/v1"):
                openai_paths.append("/v1/models")
            for path in openai_paths:
                url = join_endpoint(normalized, path)
                checked.append(url)
                try:
                    response = await client.get(url, headers=headers)
                    payload = self._json_or_empty(response)
                    if response.status_code in {200, 401, 403} and self._looks_openai(payload, response.status_code):
                        models = self._model_names(payload.get("data"))
                        return ProviderDetectionResult(
                            detected=True,
                            kind="openai_compatible",
                            normalized_base_url=normalized if normalized.endswith("/v1") else normalized + "/v1",
                            name_suggestion=self._provider_name(normalized),
                            models=models,
                            capabilities={"model_discovery": response.status_code == 200, "streaming": True, "tools": True},
                            status_code=response.status_code,
                            message="OpenAI-compatible models endpoint detected." if response.status_code == 200 else "Endpoint detected; credentials are required for model discovery.",
                            checked_urls=checked,
                        )
                except httpx.HTTPError:
                    continue

        return ProviderDetectionResult(
            detected=False,
            kind="unknown",
            normalized_base_url=normalized,
            name_suggestion=self._provider_name(normalized),
            capabilities={},
            message="No supported Ollama or OpenAI-compatible endpoint answered the probe.",
            checked_urls=checked,
        )

    async def probe_profile(self, profile: ProviderProfile) -> ProviderDetectionResult:
        if profile.kind == "custom_script":
            return ProviderDetectionResult(
                detected=True,
                kind="custom_script",
                normalized_base_url=profile.base_url,
                name_suggestion=profile.name,
                capabilities={"model_discovery": False, "streaming": False, "tools": True},
                message="Custom adapter profile is structurally valid; runtime availability is checked when invoked.",
            )
        return await self.detect(profile.normalized_base_url(), profile.auth_env_var)

    @staticmethod
    def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _looks_openai(payload: dict[str, Any], status_code: int) -> bool:
        if status_code in {401, 403}:
            return True
        return isinstance(payload.get("data"), list) or isinstance(payload.get("object"), str)

    @staticmethod
    def _model_names(items: Any) -> list[str]:
        if not isinstance(items, list):
            return []
        return [str(item.get("name") or item.get("id")) for item in items if isinstance(item, dict) and (item.get("name") or item.get("id"))]

    @staticmethod
    def _provider_name(base_url: str) -> str:
        host = host_from_url(base_url)
        return host.split(":", 1)[0] or "OpenAI-compatible provider"
