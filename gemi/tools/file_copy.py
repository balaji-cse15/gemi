"""FileCopyTool — copy files and directories."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class FileCopyTool(Tool):
    name = "copy_file"
    description = "Copy a file or directory to a new location."
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
            if src_path.is_dir():
                shutil.copytree(str(src_path), str(dst_path))
            else:
                shutil.copy2(str(src_path), str(dst_path))
            return ToolResult.ok(f"Copied {src_path} -> {dst_path}")
        except Exception as e:
            return ToolResult.fail(f"Copy failed: {e}")
