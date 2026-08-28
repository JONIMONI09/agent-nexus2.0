from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator


ProviderKind = Literal["ollama", "openai_compatible", "custom_script"]

_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class ProviderProfile(BaseModel):
    id: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    kind: ProviderKind
    base_url: str = Field(default="", max_length=2000)
    auth_env_var: str = Field(default="", max_length=128)
    models_path: str = Field(default="", max_length=300)
    chat_path: str = Field(default="", max_length=300)
    default_model: str = Field(default="", max_length=160)
    script: str = Field(default="", max_length=60000)
    allowed_hosts: list[str] = Field(default_factory=list, max_length=30)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    builtin: bool = False

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip().lower()
        if not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError("Provider id must contain lowercase letters, numbers, underscores, or hyphens.")
        return value

    @field_validator("auth_env_var")
    @classmethod
    def validate_auth_env_var(cls, value: str) -> str:
        value = value.strip().upper()
        if value and not _ENV_RE.fullmatch(value):
            raise ValueError("Credential reference must be a valid environment variable name.")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for host in value:
            normalized = host.strip().lower()
            if not normalized or normalized in cleaned:
                continue
            if any(character in normalized for character in ("/", "\\", " ", "@")):
                raise ValueError("Allowed network entries must be hostnames, not URLs or credentials.")
            cleaned.append(normalized)
        return cleaned

    def normalized_base_url(self) -> str:
        return normalize_base_url(self.base_url, allow_empty=self.kind == "custom_script")

    def public_dict(self) -> dict[str, Any]:
        payload = self.model_dump(exclude={"script"})
        payload["has_script"] = bool(self.script.strip())
        return payload


class ProviderUpsertRequest(BaseModel):
    id: str | None = Field(default=None, min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    kind: ProviderKind
    base_url: str = Field(default="", max_length=2000)
    auth_env_var: str = Field(default="", max_length=128)
    models_path: str = Field(default="", max_length=300)
    chat_path: str = Field(default="", max_length=300)
    default_model: str = Field(default="", max_length=160)
    script: str = Field(default="", max_length=60000)
    allowed_hosts: list[str] = Field(default_factory=list, max_length=30)

    def to_profile(self, provider_id: str) -> ProviderProfile:
        return ProviderProfile(
            id=provider_id,
            name=self.name.strip(),
            description=self.description.strip(),
            kind=self.kind,
            base_url=self.base_url.strip(),
            auth_env_var=self.auth_env_var,
            models_path=self.models_path.strip(),
            chat_path=self.chat_path.strip(),
            default_model=self.default_model.strip(),
            script=self.script,
            allowed_hosts=self.allowed_hosts,
            capabilities={},
            builtin=False,
        )


class ProviderDetectionResult(BaseModel):
    detected: bool
    kind: ProviderKind | Literal["unknown"]
    normalized_base_url: str
    name_suggestion: str
    models: list[str] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    status_code: int | None = None
    message: str
    checked_urls: list[str] = Field(default_factory=list)


def normalize_base_url(value: str, allow_empty: bool = False) -> str:
    raw = value.strip()
    if not raw:
        if allow_empty:
            return ""
        raise ValueError("Provider URL is required.")
    candidate = raw if "://" in raw else f"http://{raw}"
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Provider URL must use http or https and include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("Provider URLs must not contain embedded credentials.")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def join_endpoint(base_url: str, path: str) -> str:
    base = normalize_base_url(base_url)
    clean_path = "/" + path.strip().lstrip("/")
    return f"{base}{clean_path}"


def host_from_url(value: str) -> str:
    parsed = urlsplit(normalize_base_url(value))
    if parsed.port:
        return f"{parsed.hostname}:{parsed.port}"
    return parsed.hostname or ""


def generated_provider_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "provider"
    if len(slug) < 2:
        slug = f"{slug}-provider"
    return slug[:52]
