"""WebSearchTool — DuckDuckGo HTML search (no API key required).

Uses the lite HTML endpoint and parses results with regex. No external
dependencies beyond httpx (already a buddy dep). Returns top N results
as title, URL, and snippet.

NOT a YOLO tool — read-only web access, same tier as web_fetch.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from .base import Tool, ToolResult


class WebSearchTool(Tool):
    name = "web_search"
    read_only = True
    description = (
        "Search the web via DuckDuckGo's HTML endpoint (no API key needed). "
        "Returns top results as title, URL, snippet. Use to find documentation, "
        "Stack Overflow answers, GitHub repos, etc."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 10, max 25).",
                "default": 10,
            },
            "region": {
                "type": "string",
                "description": "DuckDuckGo region code (default us-en).",
                "default": "us-en",
            },
        },
        "required": ["query"],
    }

    _RESULT_PATTERN = re.compile(
        r'<a\s+rel="nofollow"\s+class="result__a"\s+href="([^"]+)"[^>]*>(.+?)</a>'
        r'.*?<a\s+class="result__snippet"[^>]*>(.+?)</a>',
        re.DOTALL,
    )

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "").strip()
        if not query:
            return ToolResult.fail("No query provided.")
        max_results = min(int(kwargs.get("max_results", 10)), 25)
        region = kwargs.get("region", "us-en")

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl={region}"
        try:
            resp = httpx.get(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html",
                },
                timeout=15,
                follow_redirects=True,
            )
        except httpx.TimeoutException:
            return ToolResult.fail("DuckDuckGo request timed out.")
        except Exception as e:
            return ToolResult.fail(f"Request failed: {e}")

        if resp.status_code != 200:
            return ToolResult.fail(f"DuckDuckGo returned HTTP {resp.status_code}")

        results = []
        for match in self._RESULT_PATTERN.finditer(resp.text):
            href, title_html, snippet_html = match.groups()
            title = _strip_tags(html.unescape(title_html)).strip()
            snippet = _strip_tags(html.unescape(snippet_html)).strip()
            href = _normalize_url(href)
            if title and href:
                results.append({"title": title, "url": href, "snippet": snippet})
            if len(results) >= max_results:
                break

        if not results:
            return ToolResult.fail(f"No results for: {query}")

        lines = [f"Search: {query}  ({len(results)} results)\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['url']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet'][:300]}")
            lines.append("")
        return ToolResult.ok("\n".join(lines))


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def _normalize_url(href: str) -> str:
    """DuckDuckGo wraps result URLs as /l/?uddg=<encoded>. Unwrap them."""
    m = re.search(r"uddg=([^&]+)", href)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    if href.startswith("//"):
        return "https:" + href
    return href
