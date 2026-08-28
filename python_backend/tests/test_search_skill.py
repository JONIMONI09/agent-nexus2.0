from __future__ import annotations

import asyncio

from python_backend.skills import web_search


def test_search_skill_rejects_invalid_arguments() -> None:
    async def run() -> tuple[dict[str, object], dict[str, object]]:
        skill = web_search.WebSearchSkill()
        return await skill.execute({}), await skill.execute({"query": "ok", "max_results": "5"})

    empty, wrong_limit = asyncio.run(run())
    assert empty["ok"] is False
    assert wrong_limit["ok"] is False


def test_search_skill_normalizes_valid_results(monkeypatch) -> None:
    class FakeDDGS:
        def text(self, query, **kwargs):
            assert query == "local agents"
            assert kwargs["max_results"] == 2
            return [
                {"title": "One", "href": "https://example.com/one", "body": "First"},
                {"title": "Ignored", "href": "not-a-url", "body": "No"},
                {"title": "Two", "url": "https://example.com/two", "snippet": "Second"},
            ]

    monkeypatch.setattr(web_search, "DDGS", FakeDDGS)
    result = asyncio.run(web_search.WebSearchSkill().execute({"query": " local agents ", "max_results": 2}))

    assert result["ok"] is True
    assert result["query"] == "local agents"
    assert result["results"] == [
        {"title": "One", "url": "https://example.com/one", "snippet": "First"},
        {"title": "Two", "url": "https://example.com/two", "snippet": "Second"},
    ]
