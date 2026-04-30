"""FileEditTool — partial file modification via string replacement."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class FileEditTool(Tool):
    name = "edit_file"
    description = (
        "Edit a file by replacing an exact string with new content. "
        "The old_string must be unique in the file (or use replace_all). "
        "Preserves indentation exactly."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or workspace-relative path to the file.",
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to find and replace.",
            },
            "new_string": {
                "type": "string",
                "description": "The text to replace it with.",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default false).",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("file_path", "")
        old_string = kwargs.get("old_string", "")
        new_string = kwargs.get("new_string", "")
        replace_all = bool(kwargs.get("replace_all", False))
        if not raw_path:
            return ToolResult.fail("No file_path provided.")
        if not old_string:
            return ToolResult.fail("No old_string provided.")
        if old_string == new_string:
            return ToolResult.fail("old_string and new_string are identical.")
        path = Path(raw_path)
        if not path.is_absolute():
            path = workspace / path
        path = path.resolve()
        if not path.is_file():
            return ToolResult.fail(f"File not found: {path}")
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult.fail(f"Cannot read file: {e}")
        count = content.count(old_string)
        if count == 0:
            return ToolResult.fail("old_string not found in file.")
        if count > 1 and not replace_all:
            return ToolResult.fail(
                f"old_string found {count} times. Use replace_all=true or provide more context."
            )
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
        path.write_text(new_content, encoding="utf-8")
        replacements = count if replace_all else 1
        return ToolResult.ok(f"Replaced {replacements} occurrence(s) in {path}")
