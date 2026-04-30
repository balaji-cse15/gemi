"""FileDeleteTool — delete files or empty directories."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class FileDeleteTool(Tool):
    name = "delete_file"
    dangerous = True
    description = (
        "Delete a file or directory. For directories, use recursive=true. "
        "Returns confirmation of what was deleted."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file or directory to delete.",
            },
            "recursive": {
                "type": "boolean",
                "description": "Delete directories recursively (default false).",
                "default": False,
            },
        },
        "required": ["path"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("path", "")
        recursive = bool(kwargs.get("recursive", False))
        if not raw_path:
            return ToolResult.fail("No path provided.")
        target = Path(raw_path)
        if not target.is_absolute():
            target = workspace / target
        target = target.resolve()
        if not target.exists():
            return ToolResult.fail(f"Path not found: {target}")
        try:
            if target.is_file() or target.is_symlink():
                target.unlink()
                return ToolResult.ok(f"Deleted file: {target}")
            elif target.is_dir():
                if recursive:
                    shutil.rmtree(target)
                    return ToolResult.ok(f"Deleted directory (recursive): {target}")
                else:
                    target.rmdir()
                    return ToolResult.ok(f"Deleted empty directory: {target}")
            else:
                return ToolResult.fail(f"Unknown path type: {target}")
        except OSError as e:
            return ToolResult.fail(f"Delete failed: {e}")
