"""GlobTool — find files by pattern."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class GlobTool(Tool):
    name = "glob"
    description = (
        "Find files matching a glob pattern (e.g. '**/*.py', 'src/**/*.ts'). "
        "Returns matching file paths sorted by modification time."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match files against.",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in. Defaults to workspace root.",
                "default": ".",
            },
        },
        "required": ["pattern"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        pattern = kwargs.get("pattern", "")
        search_path = kwargs.get("path", ".")
        if not pattern:
            return ToolResult.fail("No pattern provided.")
        base = Path(search_path)
        if not base.is_absolute():
            base = workspace / base
        base = base.resolve()
        if not base.is_dir():
            return ToolResult.fail(f"Directory not found: {base}")
        try:
            matches = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception as e:
            return ToolResult.fail(f"Glob error: {e}")
        if not matches:
            return ToolResult.ok("No files matched.")
        lines = [str(m) for m in matches[:250]]
        return ToolResult.ok("\n".join(lines))
