"""FileMoveTool — move or rename files and directories."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class FileMoveTool(Tool):
    name = "move_file"
    description = "Move or rename a file or directory."
    input_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Source path.",
            },
            "destination": {
                "type": "string",
                "description": "Destination path.",
            },
        },
        "required": ["source", "destination"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        src = kwargs.get("source", "")
        dst = kwargs.get("destination", "")
        if not src or not dst:
            return ToolResult.fail("Both source and destination required.")
        src_path = Path(src) if Path(src).is_absolute() else workspace / src
        dst_path = Path(dst) if Path(dst).is_absolute() else workspace / dst
        src_path = src_path.resolve()
        dst_path = dst_path.resolve()
        if not src_path.exists():
            return ToolResult.fail(f"Source not found: {src_path}")
        try:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dst_path))
            return ToolResult.ok(f"Moved {src_path} -> {dst_path}")
        except Exception as e:
            return ToolResult.fail(f"Move failed: {e}")
