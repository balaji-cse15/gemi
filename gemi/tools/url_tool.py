"""UrlTool — parse, build, and encode URLs."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import (
    parse_qs,
    quote,
    unquote,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

from .base import Tool, ToolResult


class UrlTool(Tool):
    name = "url"
    description = (
        "Parse, build, encode, and manipulate URLs. "
        "Actions: 'parse' (break down URL), 'build' (construct URL), "
        "'encode' (percent-encode), 'decode' (percent-decode), "
        "'join' (resolve relative URL)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'parse', 'build', 'encode', 'decode', 'join'.",
                "enum": ["parse", "build", "encode", "decode", "join"],
            },
            "url": {
                "type": "string",
                "description": "URL to parse/decode, or base URL for join.",
            },
            "text": {
                "type": "string",
                "description": "Text to encode, or relative URL for join.",
            },
            "scheme": {"type": "string", "description": "URL scheme (for build)."},
            "host": {"type": "string", "description": "Hostname (for build)."},
            "port": {"type": "integer", "description": "Port (for build)."},
            "path": {"type": "string", "description": "URL path (for build)."},
            "params": {"type": "string", "description": "Query params as key=val&key2=val2 (for build)."},
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "parse":
            url = kwargs.get("url", "")
            if not url:
                return ToolResult.fail("url required.")
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            lines = [
                f"Scheme:   {parsed.scheme}",
                f"Host:     {parsed.hostname or ''}",
                f"Port:     {parsed.port or 'default'}",
                f"Path:     {parsed.path}",
                f"Query:    {parsed.query}",
                f"Fragment: {parsed.fragment}",
                f"Username: {parsed.username or ''}",
                f"Password: {'***' if parsed.password else ''}",
            ]
            if qs:
                lines.append("Params:")
                for k, v in qs.items():
                    lines.append(f"  {k} = {v}")
            return ToolResult.ok("\n".join(lines))

        elif action == "build":
            scheme = kwargs.get("scheme", "https")
            host = kwargs.get("host", "")
            port = kwargs.get("port", "")
            path = kwargs.get("path", "/")
            params = kwargs.get("params", "")
            if not host:
                return ToolResult.fail("host required for build.")
            netloc = host
            if port:
                netloc += f":{port}"
            url = urlunparse((scheme, netloc, path, "", params, ""))
            return ToolResult.ok(url)

        elif action == "encode":
            text = kwargs.get("text", kwargs.get("url", ""))
            if not text:
                return ToolResult.fail("text required.")
            return ToolResult.ok(quote(text, safe=""))

        elif action == "decode":
            text = kwargs.get("text", kwargs.get("url", ""))
            if not text:
                return ToolResult.fail("text required.")
            return ToolResult.ok(unquote(text))

        elif action == "join":
            base = kwargs.get("url", "")
            relative = kwargs.get("text", "")
            if not base or not relative:
                return ToolResult.fail("url (base) and text (relative) required.")
            return ToolResult.ok(urljoin(base, relative))

        return ToolResult.fail(f"Unknown action: {action}")
