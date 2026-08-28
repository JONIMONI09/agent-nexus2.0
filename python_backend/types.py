from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class OrchestrateRequest(BaseModel):
    translate_input: bool = Field(default=False, description="Auto-translate non-English input to English for the local models before the run.")
    message: str = Field(min_length=1, max_length=8000)
    scout_model: str = Field(default="qwen3", min_length=1, max_length=160)
    synthesizer_model: str = Field(default="qwen3", min_length=1, max_length=160)
    fallback_model: str = Field(default="qwen2.5:3b", min_length=1, max_length=160)
    scout_provider_id: str = Field(default="ollama", min_length=2, max_length=64)
    synthesizer_provider_id: str = Field(default="ollama", min_length=2, max_length=64)
    fallback_provider_id: str = Field(default="ollama", min_length=2, max_length=64)
    system_prompt: str = Field(default="", max_length=6000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=40)
    single_agent: bool = Field(default=False, description="Run one AI that may delegate to subagents instead of the two-agent scout/synthesizer loop.")
    agent_count: int = Field(default=1, ge=1, le=3, description="How many agents are active in the pipeline: 1 = one AI, 2 = Scout+Synthesizer, 3 = Scout+Analyst+Synthesizer.")
    learning_enabled: bool = Field(default=False, description="Inject learn.md / Rules.md / Agent.md memory into this run.")
    thinking_style: str = Field(default="balanced", pattern="^(concise|balanced|deep|creative)$", description="How the AI should think.")


class GitHubRepositoryRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)


class GitHubBranchRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    branch: str = Field(min_length=1, max_length=255)
    from_sha: str = Field(min_length=7, max_length=64)


class GitHubPullRequestRequest(BaseModel):
    repository: str = Field(min_length=3, max_length=200)
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(default="", max_length=10000)
    head: str = Field(min_length=1, max_length=255)
    base: str = Field(min_length=1, max_length=255)


class ProviderDetectionRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2000)
    auth_env_var: str = Field(default="", max_length=128)


class ProviderUpsertRequest(BaseModel):
    id: str | None = Field(default=None, min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    kind: Literal["ollama", "openai_compatible", "custom_script"]
    base_url: str = Field(default="", max_length=2000)
    auth_env_var: str = Field(default="", max_length=128)
    models_path: str = Field(default="", max_length=300)
    chat_path: str = Field(default="", max_length=300)
    default_model: str = Field(default="", max_length=160)
    script: str = Field(default="", max_length=60000)
    allowed_hosts: list[str] = Field(default_factory=list, max_length=30)


class ProviderModelsRequest(BaseModel):
    provider_id: str = Field(min_length=2, max_length=64)


class ApprovalRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=100)
    approved: bool


class LearningSettingsRequest(BaseModel):
    enabled: bool


class LearningUpdateRequest(BaseModel):
    file: Literal["learn", "rules", "agent"]
    content: str = Field(max_length=60000)


class FsSettingsRequest(BaseModel):
    sandbox: Literal["jailed", "docker"] = "jailed"
    auto_create_projects: bool = True


class FsRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    system_prompt: str = Field(default="", max_length=6000)
