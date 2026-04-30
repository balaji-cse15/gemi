"""HashTool — compute file and string hashes."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class HashTool(Tool):
    name = "hash"
    description = (
        "Compute hash of a file or string. "
        "Algorithms: md5, sha1, sha256, sha512."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to file to hash (mutually exclusive with 'text').",
            },
            "text": {
                "type": "string",
                "description": "String to hash (mutually exclusive with 'file_path').",
            },
            "algorithm": {
                "type": "string",
                "description": "Hash algorithm (default sha256).",
                "default": "sha256",
                "enum": ["md5", "sha1", "sha256", "sha512"],
            },
        },
        "required": [],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        text = kwargs.get("text", "")
        algo = kwargs.get("algorithm", "sha256")

        if not file_path and text is None:
            return ToolResult.fail("Provide file_path or text.")

        try:
            h = hashlib.new(algo)
        except ValueError:
            return ToolResult.fail(f"Unknown algorithm: {algo}")

        if file_path:
            fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
            fp = fp.resolve()
            if not fp.is_file():
                return ToolResult.fail(f"File not found: {fp}")
            try:
                with open(fp, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                return ToolResult.ok(f"{algo}:{h.hexdigest()}  {fp}")
            except Exception as e:
                return ToolResult.fail(f"Hash error: {e}")
        else:
            h.update(text.encode("utf-8"))
            return ToolResult.ok(f"{algo}:{h.hexdigest()}")
