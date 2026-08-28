"""Regression tests: provider model discovery must never surface as a plain-text 500.

The reported bug surfaced as:

    Cannot discover provider models: Unexpected token 'I', "Internal S"... is not valid JSON

Chain of failures that produced it:
1. ``ProviderRuntime.list_models`` built the URL *outside* its try/except, so an
   empty or malformed provider ``base_url`` raised a bare ``ValueError``.
2. The FastAPI endpoint only caught ``ProviderRuntimeError``, so the ``ValueError``
   escaped and Starlette answered with a plain-text ``Internal Server Error``.
3. The Next.js proxy called ``response.json()`` on that body and crashed with the
   cryptic JSON error above.

These tests pin the fix at every layer: the runtime wraps URL errors, and the
endpoint returns a structured JSON 502 for every failure mode.
"""

from __future__ import annotations

import asyncio
import json
import tempfile

import httpx
import pytest

from python_backend import main
from python_backend.provider_models import ProviderProfile
from python_backend.provider_runtime import ProviderRuntime, ProviderRuntimeError
from python_backend.provider_store import ProviderStore


def _runtime_with(profile: ProviderProfile | None = None) -> ProviderRuntime:
    store = ProviderStore(path=f"{tempfile.mkdtemp()}/state.db")
    if profile is not None:
        store.upsert(profile)
    return ProviderRuntime(store, timeout_seconds=3.0)


def _custom_profile(provider_id: str = "my-provider", base_url: str = "") -> ProviderProfile:
    return ProviderProfile(
        id=provider_id,
        name="My Provider",
        kind="openai_compatible",
        base_url=base_url,
    )


async def _get_models(provider_id: str) -> tuple[int, dict[str, object]]:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/providers/{provider_id}/models")
        return response.status_code, json.loads(response.text)


# --- runtime layer ----------------------------------------------------------


def test_list_models_empty_base_url_raises_runtime_error() -> None:
    runtime = _runtime_with(_custom_profile(base_url=""))
    with pytest.raises(ProviderRuntimeError) as excinfo:
        asyncio.run(runtime.list_models("my-provider"))
    assert "Provider URL is required" in str(excinfo.value)


def test_list_models_invalid_base_url_raises_runtime_error() -> None:
    runtime = _runtime_with(_custom_profile(base_url="not a url with spaces"))
    with pytest.raises(ProviderRuntimeError) as excinfo:
        asyncio.run(runtime.list_models("my-provider"))
    # The key guarantee: a user-safe ProviderRuntimeError, never a bare ValueError
    # that would escape the endpoint as a plain-text 500.
    assert "Model discovery failed" in str(excinfo.value)


def test_list_models_missing_profile_raises_runtime_error() -> None:
    runtime = _runtime_with()
    with pytest.raises(ProviderRuntimeError) as excinfo:
        asyncio.run(runtime.list_models("missing"))
    assert "not configured" in str(excinfo.value)


def test_list_models_plain_text_500_includes_detail(monkeypatch) -> None:
    """A provider that answers with plain-text 'Internal Server Error' must become a
    ProviderRuntimeError carrying that detail — exactly the body that used to crash
    the frontend proxy."""

    class FakeResponse:
        status_code = 500

        async def aread(self) -> bytes:
            return b"Internal Server Error"

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def get(self, url: str, headers: dict[str, str] | None = None) -> FakeResponse:
            return FakeResponse()

    runtime = _runtime_with(_custom_profile(base_url="http://127.0.0.1:9"))
    monkeypatch.setattr("python_backend.provider_runtime.httpx.AsyncClient", FakeClient)
    with pytest.raises(ProviderRuntimeError) as excinfo:
        asyncio.run(runtime.list_models("my-provider"))
    assert "500" in str(excinfo.value)
    assert "Internal Server Error" in str(excinfo.value)


# --- endpoint layer ---------------------------------------------------------


def test_models_endpoint_returns_json_502_for_empty_base_url(monkeypatch) -> None:
    monkeypatch.setattr(main, "provider_runtime", _runtime_with(_custom_profile(base_url="")))
    status, payload = asyncio.run(_get_models("my-provider"))
    assert status == 502
    assert payload["ok"] is False
    assert payload["models"] == []
    assert "Provider URL is required" in str(payload["error"])


def test_models_endpoint_unknown_provider_returns_json_502(monkeypatch) -> None:
    monkeypatch.setattr(main, "provider_runtime", _runtime_with())
    status, payload = asyncio.run(_get_models("no-such-provider"))
    assert status == 502
    assert payload["ok"] is False
    assert "not configured" in str(payload["error"])


def test_models_endpoint_never_returns_plain_text_500(monkeypatch) -> None:
    """Last-resort guard: ANY unexpected error must come back as JSON, so the
    frontend proxy never has to parse 'Internal Server Error'."""

    class Boom:
        async def list_models(self, provider_id: str) -> list[dict[str, object]]:
            raise RuntimeError("boom inside list_models")

    monkeypatch.setattr(main, "provider_runtime", Boom())
    status, payload = asyncio.run(_get_models("whatever"))
    assert status == 502
    assert payload["ok"] is False
    assert payload["models"] == []
    assert "boom inside list_models" in str(payload["error"])
