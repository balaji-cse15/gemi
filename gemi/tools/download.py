"""DownloadTool — download files from URLs to disk."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .base import Tool, ToolResult


class DownloadTool(Tool):
    name = "download"
    description = (
        "Download a file from a URL and save it to disk. "
        "Supports HTTP/HTTPS. Shows progress for large files."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to download from.",
            },
            "output_path": {
                "type": "string",
                "description": "Local path to save the file. Defaults to filename from URL.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 300).",
                "default": 300,
            },
        },
        "required": ["url"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        output = kwargs.get("output_path", "")
        timeout = int(kwargs.get("timeout", 300))

        if not url:
            return ToolResult.fail("No URL provided.")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult.fail("Only http/https URLs supported.")

        if not output:
            filename = Path(parsed.path).name or "download"
            out_path = workspace / filename
        else:
            out_path = Path(output) if Path(output).is_absolute() else workspace / output
        out_path = out_path.resolve()

        try:
            import httpx
            out_path.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
                if resp.status_code >= 400:
                    return ToolResult.fail(f"HTTP {resp.status_code}: {resp.reason_phrase}")
                with open(out_path, "wb") as f:
                    for chunk in resp.iter_bytes(65536):
                        f.write(chunk)
                        total += len(chunk)

            size_str = f"{total / 1_048_576:.1f}MB" if total > 1_048_576 else f"{total / 1024:.0f}KB"
            return ToolResult.ok(f"Downloaded {size_str} to {out_path}")
        except Exception as e:
            return ToolResult.fail(f"Download failed: {e}")
