"""Tests for provider registry authentication and authorization."""

from __future__ import annotations

import asyncio
import tempfile

import httpx
import pytest

from python_backend import main
from python_backend.provider_models import ProviderProfile
from python_backend.provider_store import ProviderStore


def _test_profile() -> ProviderProfile:
    """Create a test provider profile."""
    return ProviderProfile(
        id="test-provider",
        name="Test Provider",
        description="Test provider for authentication tests",
        kind="openai_compatible",
        base_url="http://localhost:8080",
        auth_env_var="",
        models_path="/v1/models",
        chat_path="/v1/chat/completions",
        default_model="test-model",
        script="",
        allowed_hosts=[],
        capabilities={},
        builtin=False,
    )


@pytest.fixture
def isolated_app(monkeypatch):
    """Create an isolated FastAPI app with a temporary provider store."""
    temp_store = ProviderStore(path=f"{tempfile.mkdtemp()}/test_auth.db")
    monkeypatch.setattr(main, "provider_store", temp_store)
    return main.app


def test_upsert_provider_without_api_key_when_not_configured(
    isolated_app, monkeypatch
) -> None:
    """When API_KEY is not configured, POST /providers should succeed without authentication."""
    monkeypatch.setattr(main, "API_KEY", "")

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/providers",
                json={
                    "name": "Test Provider",
                    "description": "Test",
                    "kind": "openai_compatible",
                    "base_url": "http://localhost:8080",
                    "auth_env_var": "",
                    "models_path": "/v1/models",
                    "chat_path": "/v1/chat/completions",
                    "default_model": "test-model",
                    "script": "",
                    "allowed_hosts": [],
                },
            )
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 201
    assert payload["ok"] is True
    assert "provider" in payload


def test_upsert_provider_with_api_key_when_configured(
    isolated_app, monkeypatch
) -> None:
    """When API_KEY is configured, POST /providers should succeed with correct key."""
    monkeypatch.setattr(main, "API_KEY", "test-secret-key-12345")

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/providers",
                json={
                    "name": "Test Provider",
                    "description": "Test",
                    "kind": "openai_compatible",
                    "base_url": "http://localhost:8080",
                    "auth_env_var": "",
                    "models_path": "/v1/models",
                    "chat_path": "/v1/chat/completions",
                    "default_model": "test-model",
                    "script": "",
                    "allowed_hosts": [],
                },
                headers={"X-API-Key": "test-secret-key-12345"},
            )
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 201
    assert payload["ok"] is True


def test_upsert_provider_without_api_key_when_configured_fails(
    isolated_app, monkeypatch
) -> None:
    """When API_KEY is configured, POST /providers should fail without authentication."""
    monkeypatch.setattr(main, "API_KEY", "test-secret-key-12345")

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/providers",
                json={
                    "name": "Test Provider",
                    "description": "Test",
                    "kind": "openai_compatible",
                    "base_url": "http://localhost:8080",
                    "auth_env_var": "",
                    "models_path": "/v1/models",
                    "chat_path": "/v1/chat/completions",
                    "default_model": "test-model",
                    "script": "",
                    "allowed_hosts": [],
                },
            )
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 401
    assert "X-API-Key" in payload["detail"]


def test_upsert_provider_with_wrong_api_key_fails(isolated_app, monkeypatch) -> None:
    """When API_KEY is configured, POST /providers should fail with incorrect key."""
    monkeypatch.setattr(main, "API_KEY", "test-secret-key-12345")

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.post(
                "/providers",
                json={
                    "name": "Test Provider",
                    "description": "Test",
                    "kind": "openai_compatible",
                    "base_url": "http://localhost:8080",
                    "auth_env_var": "",
                    "models_path": "/v1/models",
                    "chat_path": "/v1/chat/completions",
                    "default_model": "test-model",
                    "script": "",
                    "allowed_hosts": [],
                },
                headers={"X-API-Key": "wrong-key"},
            )
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 401
    assert "Invalid API key" in payload["detail"]


def test_delete_provider_without_api_key_when_not_configured(
    isolated_app, monkeypatch
) -> None:
    """When API_KEY is not configured, DELETE /providers/{id} should succeed without authentication."""
    monkeypatch.setattr(main, "API_KEY", "")

    # First create a provider
    profile = _test_profile()
    main.provider_store.upsert(profile)

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.delete("/providers/test-provider")
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 200
    assert payload["ok"] is True


def test_delete_provider_with_api_key_when_configured(
    isolated_app, monkeypatch
) -> None:
    """When API_KEY is configured, DELETE /providers/{id} should succeed with correct key."""
    monkeypatch.setattr(main, "API_KEY", "test-secret-key-12345")

    # First create a provider
    profile = _test_profile()
    main.provider_store.upsert(profile)

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.delete(
                "/providers/test-provider",
                headers={"X-API-Key": "test-secret-key-12345"},
            )
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 200
    assert payload["ok"] is True


def test_delete_provider_without_api_key_when_configured_fails(
    isolated_app, monkeypatch
) -> None:
    """When API_KEY is configured, DELETE /providers/{id} should fail without authentication."""
    monkeypatch.setattr(main, "API_KEY", "test-secret-key-12345")

    # First create a provider
    profile = _test_profile()
    main.provider_store.upsert(profile)

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.delete("/providers/test-provider")
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 401
    assert "X-API-Key" in payload["detail"]


def test_delete_provider_with_wrong_api_key_fails(isolated_app, monkeypatch) -> None:
    """When API_KEY is configured, DELETE /providers/{id} should fail with incorrect key."""
    monkeypatch.setattr(main, "API_KEY", "test-secret-key-12345")

    # First create a provider
    profile = _test_profile()
    main.provider_store.upsert(profile)

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.delete(
                "/providers/test-provider",
                headers={"X-API-Key": "wrong-key"},
            )
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 401
    assert "Invalid API key" in payload["detail"]


def test_get_providers_always_works_without_authentication(
    isolated_app, monkeypatch
) -> None:
    """GET /providers should always work without authentication, even when API_KEY is configured."""
    monkeypatch.setattr(main, "API_KEY", "test-secret-key-12345")

    async def run() -> tuple[int, dict]:
        transport = httpx.ASGITransport(app=isolated_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            response = await client.get("/providers")
            return response.status_code, response.json()

    status, payload = asyncio.run(run())
    assert status == 200
    assert payload["ok"] is True
    assert "providers" in payload
