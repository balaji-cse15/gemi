"""WebFetchTool — fetch content from URLs."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .base import Tool, ToolResult


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch content from an HTTP/HTTPS URL. Returns the response body."
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30).",
                "default": 30,
            },
        },
        "required": ["url"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        timeout = int(kwargs.get("timeout", 30))
        if not url:
            return ToolResult.fail("No URL provided.")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult.fail("Only http/https URLs are supported.")
        try:
            import httpx
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            text = resp.text
            if len(text) > 50000:
                text = text[:50000] + "\n... (truncated)"
            return ToolResult.ok(f"Status: {resp.status_code}\n\n{text}")
        except Exception as e:
            return ToolResult.fail(f"Fetch failed: {e}")
