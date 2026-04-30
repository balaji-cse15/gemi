"""FileReadTool — read file contents with optional line ranges."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class FileReadTool(Tool):
    name = "read_file"
    description = (
        "Read a file from the filesystem. Returns contents with line numbers. "
        "Supports offset and limit for reading specific sections of large files."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or workspace-relative path to the file.",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (0-based). Default 0.",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Number of lines to read. Default 2000.",
                "default": 2000,
            },
        },
        "required": ["file_path"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("file_path", "")
        offset = int(kwargs.get("offset", 0))
        limit = int(kwargs.get("limit", 2000))
        if not raw_path:
            return ToolResult.fail("No file_path provided.")
        path = Path(raw_path)
        if not path.is_absolute():
            path = workspace / path
        path = path.resolve()
        if not path.is_file():
            return ToolResult.fail(f"File not found: {path}")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult.fail(f"Cannot read file: {e}")
        lines = text.splitlines()
        selected = lines[offset : offset + limit]
        numbered = []
        for i, line in enumerate(selected, start=offset + 1):
            numbered.append(f"{i}\t{line}")
        return ToolResult.ok("\n".join(numbered))
