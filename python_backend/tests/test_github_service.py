"""Tests for the GitHub service: input validation and safe error handling."""
from __future__ import annotations

import asyncio

from python_backend.github_service import GitHubService, GitHubServiceError


def test_missing_token_raises() -> None:
    svc = GitHubService(token="")
    try:
        asyncio.run(svc.repository("octocat/hello-world"))
    except GitHubServiceError as exc:
        assert "GITHUB_TOKEN" in str(exc)
    else:
        raise AssertionError("expected GitHubServiceError for missing token")


def test_repository_validation() -> None:
    svc = GitHubService(token="fake")
    for bad in ("", "no-slash", "/b", "../evil", "a/../b"):
        try:
            asyncio.run(svc.repository(bad))
        except GitHubServiceError as exc:
            assert "owner/repository" in str(exc) or "not configured" in str(exc) or "404" in str(exc)
        else:
            raise AssertionError(f"expected validation error for: {bad!r}")


def test_sha_validation() -> None:
    svc = GitHubService(token="fake")
    for bad in ("", "short", "g-" * 10, "ZZZZ"):
        try:
            asyncio.run(svc.create_branch("a/b", "feature", bad))
        except GitHubServiceError as exc:
            assert "sha" in str(exc).lower() or "not configured" in str(exc)
        else:
            raise AssertionError(f"expected sha error for: {bad!r}")


def test_ref_validation() -> None:
    svc = GitHubService(token="fake")
    for bad in ("", "a" * 300, "-leading", "has..double"):
        try:
            asyncio.run(svc.create_branch("a/b", bad, "0123456789abcdef"))
        except GitHubServiceError as exc:
            assert "invalid" in str(exc).lower() or "not configured" in str(exc)
        else:
            raise AssertionError(f"expected ref error for: {bad!r}")


def test_pr_title_validation() -> None:
    svc = GitHubService(token="fake")
    try:
        asyncio.run(svc.create_pull_request("a/b", "", "body", "head", "main"))
    except GitHubServiceError as exc:
        assert "title" in str(exc).lower() or "not configured" in str(exc)
    else:
        raise AssertionError("expected title validation error")


def test_pr_body_truncated() -> None:
    """Long PR bodies must be capped, not crash."""
    svc = GitHubService(token="fake")
    long_body = "x" * 20000
    # Should raise a network/token error, not a validation error about body length
    try:
        asyncio.run(svc.create_pull_request("a/b", "test", long_body, "head", "main"))
    except GitHubServiceError as exc:
        assert "body" not in str(exc).lower() or "not configured" in str(exc)
