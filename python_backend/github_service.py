from __future__ import annotations

import os
import re
from typing import Any

import httpx


_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")


class GitHubServiceError(RuntimeError):
    """A safe, user-facing GitHub integration error."""


class GitHubService:
    def __init__(self, token: str | None = None, *, timeout: float = 15.0, allowed_repositories: list[str] | None = None) -> None:
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN", "").strip()
        self.timeout = timeout
        # Parse allowed repositories from environment or parameter
        if allowed_repositories is not None:
            self.allowed_repositories = allowed_repositories
        else:
            env_repos = os.getenv("GITHUB_ALLOWED_REPOSITORIES", "").strip()
            if env_repos:
                # Parse comma-separated list, normalize whitespace
                self.allowed_repositories = [repo.strip() for repo in env_repos.split(",") if repo.strip()]
            else:
                self.allowed_repositories = []

    def _require_token(self) -> None:
        if not self.token:
            raise GitHubServiceError("GitHub is not configured. Add GITHUB_TOKEN in the Keys tab.")

    def _validate_repository(self, repository: str) -> str:
        value = repository.strip()
        if not _REPOSITORY.fullmatch(value):
            raise GitHubServiceError("repository must use the owner/repository format.")
        
        # Enforce repository allowlist authorization
        if not self.allowed_repositories:
            raise GitHubServiceError("GitHub integration is disabled. Configure GITHUB_ALLOWED_REPOSITORIES to authorize specific repositories.")
        
        # Case-insensitive comparison for repository names (GitHub treats them as case-insensitive)
        normalized_value = value.lower()
        normalized_allowed = [repo.lower() for repo in self.allowed_repositories]
        
        if normalized_value not in normalized_allowed:
            raise GitHubServiceError(f"Repository '{value}' is not authorized. Contact the administrator to add it to the allowlist.")
        
        return value

    @staticmethod
    def _validate_ref(ref: str, name: str = "ref") -> str:
        value = ref.strip()
        if not value or len(value) > 255 or value.startswith("-") or ".." in value:
            raise GitHubServiceError(f"{name} is invalid.")
        return value

    @staticmethod
    def _validate_sha(sha: str) -> str:
        value = sha.strip()
        if not _SHA.fullmatch(value):
            raise GitHubServiceError("sha must be a valid commit SHA.")
        return value

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self._require_token()
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(base_url="https://api.github.com", timeout=self.timeout) as client:
                response = await client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise GitHubServiceError(f"GitHub request failed: {exc.__class__.__name__}.") from exc
        if response.status_code >= 400:
            detail = response.json().get("message", "request rejected") if response.content else "request rejected"
            raise GitHubServiceError(f"GitHub rejected the request ({response.status_code}): {detail}")
        if not response.content:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {"items": payload}

    async def repository(self, repository: str) -> dict[str, Any]:
        owner_repo = self._validate_repository(repository)
        payload = await self._request("GET", f"/repos/{owner_repo}")
        return {"full_name": payload.get("full_name"), "default_branch": payload.get("default_branch"), "private": payload.get("private")}

    async def create_branch(self, repository: str, branch: str, from_sha: str) -> dict[str, Any]:
        owner_repo = self._validate_repository(repository)
        branch_name = self._validate_ref(branch, "branch")
        sha = self._validate_sha(from_sha)
        payload = await self._request("POST", f"/repos/{owner_repo}/git/refs", json={"ref": f"refs/heads/{branch_name}", "sha": sha})
        return {"ref": payload.get("ref"), "sha": (payload.get("object") or {}).get("sha")}

    async def create_pull_request(self, repository: str, title: str, body: str, head: str, base: str) -> dict[str, Any]:
        owner_repo = self._validate_repository(repository)
        if not title.strip() or len(title.strip()) > 256:
            raise GitHubServiceError("title must be between 1 and 256 characters.")
        head_ref = self._validate_ref(head, "head")
        base_ref = self._validate_ref(base, "base")
        payload = await self._request("POST", f"/repos/{owner_repo}/pulls", json={"title": title.strip(), "body": body[:10000], "head": head_ref, "base": base_ref})
        return {"number": payload.get("number"), "url": payload.get("html_url"), "state": payload.get("state"), "title": payload.get("title")}
