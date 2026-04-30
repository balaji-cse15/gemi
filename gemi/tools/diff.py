"""DiffTool — compare two files or show git diff."""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class DiffTool(Tool):
    name = "diff"
    description = (
        "Compare two files and show unified diff. "
        "Also supports comparing a string against a file."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "file_a": {
                "type": "string",
                "description": "First file path.",
            },
            "file_b": {
                "type": "string",
                "description": "Second file path.",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of context lines around changes (default 3).",
                "default": 3,
            },
        },
        "required": ["file_a", "file_b"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        path_a = kwargs.get("file_a", "")
        path_b = kwargs.get("file_b", "")
        context = int(kwargs.get("context_lines", 3))
        if not path_a or not path_b:
            return ToolResult.fail("Both file_a and file_b required.")

        fa = Path(path_a) if Path(path_a).is_absolute() else workspace / path_a
        fb = Path(path_b) if Path(path_b).is_absolute() else workspace / path_b
        fa, fb = fa.resolve(), fb.resolve()

        if not fa.is_file():
            return ToolResult.fail(f"File not found: {fa}")
        if not fb.is_file():
            return ToolResult.fail(f"File not found: {fb}")

        try:
            text_a = fa.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            text_b = fb.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        except Exception as e:
            return ToolResult.fail(f"Read error: {e}")

        diff = list(difflib.unified_diff(text_a, text_b, fromfile=str(fa), tofile=str(fb), n=context))
        if not diff:
            return ToolResult.ok("Files are identical.")
        result = "".join(diff)
        if len(result) > 50000:
            result = result[:50000] + "\n... (truncated)"
        return ToolResult.ok(result)
