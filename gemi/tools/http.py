"""HttpTool — full HTTP client (GET, POST, PUT, PATCH, DELETE)."""
from __future__ import annotations

import json as json_mod
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class HttpTool(Tool):
    name = "http_request"
    description = (
        "Make HTTP requests (GET, POST, PUT, PATCH, DELETE). "
        "Supports JSON body, custom headers, and form data."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to request.",
            },
            "method": {
                "type": "string",
                "description": "HTTP method (GET, POST, PUT, PATCH, DELETE). Default GET.",
                "default": "GET",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
            },
            "headers": {
                "type": "object",
                "description": "Request headers as key-value pairs.",
            },
            "json": {
                "type": "object",
                "description": "JSON body (automatically sets Content-Type).",
            },
            "body": {
                "type": "string",
                "description": "Raw request body string.",
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
        method = kwargs.get("method", "GET").upper()
        headers = kwargs.get("headers") or {}
        json_body = kwargs.get("json")
        body = kwargs.get("body")
        timeout = int(kwargs.get("timeout", 30))

        if not url:
            return ToolResult.fail("No URL provided.")

        try:
            import httpx
            req_kwargs: dict[str, Any] = {
                "method": method,
                "url": url,
                "headers": headers,
                "timeout": timeout,
                "follow_redirects": True,
            }
            if json_body is not None:
                req_kwargs["json"] = json_body
            elif body is not None:
                req_kwargs["content"] = body

            resp = httpx.request(**req_kwargs)
            parts = [
                f"Status: {resp.status_code} {resp.reason_phrase}",
                f"Headers: {dict(resp.headers)}",
                "",
            ]
            text = resp.text
            if len(text) > 50000:
                text = text[:50000] + "\n... (truncated)"
            parts.append(text)
            return ToolResult.ok("\n".join(parts))
        except Exception as e:
            return ToolResult.fail(f"HTTP request failed: {e}")
