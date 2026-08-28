from __future__ import annotations

import asyncio
from typing import Any

try:
    from ddgs import DDGS
except ImportError as exc:  # pragma: no cover - exercised only before Python dependencies are installed
    DDGS = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class WebSearchSkill:
    name = "web_search"
    description = "Search the public web for fresh information using the local keyless DDGS metasearch client."
    parameters = {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "A focused web search query, without private data.",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return, from 1 to 8.",
                "minimum": 1,
                "maximum": 8,
            },
        },
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return {"ok": False, "error": "web_search requires a non-empty query."}
        query = query.strip()[:400]

        max_results = arguments.get("max_results", 5)
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            return {"ok": False, "error": "max_results must be an integer."}
        max_results = max(1, min(max_results, 8))

        if DDGS is None:
            return {"ok": False, "error": f"The ddgs package is unavailable: {_IMPORT_ERROR}"}

        def search() -> list[dict[str, Any]]:
            return list(DDGS().text(query, region="us-en", safesearch="moderate", max_results=max_results, backend="auto"))

        try:
            raw_results = await asyncio.to_thread(search)
        except Exception as exc:  # search backends can fail independently of the app
            return {"ok": False, "error": f"Web search failed: {exc}"}

        results: list[dict[str, str]] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = item.get("href") or item.get("url")
            title = item.get("title")
            snippet = item.get("body") or item.get("snippet")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                results.append(
                    {
                        "title": str(title or url)[:240],
                        "url": url[:1000],
                        "snippet": str(snippet or "")[:1200],
                    }
                )

        return {"ok": True, "query": query, "results": results}
