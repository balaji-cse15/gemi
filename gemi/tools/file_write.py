"""FileWriteTool — create or overwrite files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class FileWriteTool(Tool):
    name = "write_file"
    description = (
        "Write content to a file. Creates parent directories if needed. "
        "Overwrites existing files."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or workspace-relative path to the file.",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file.",
            },
        },
        "required": ["file_path", "content"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("file_path", "")
        content = kwargs.get("content", "")
        if not raw_path:
            return ToolResult.fail("No file_path provided.")
        path = Path(raw_path)
        if not path.is_absolute():
            path = workspace / path
        path = path.resolve()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult.ok(f"Wrote {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult.fail(f"Cannot write file: {e}")
