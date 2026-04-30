"""JsonTool — parse, validate, format, and query JSON."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class JsonTool(Tool):
    name = "json"
    description = (
        "Parse, validate, format, or query JSON data. "
        "Actions: 'format' (pretty-print), 'validate', 'query' (dot-path extraction), 'minify'."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'format', 'validate', 'query', 'minify'.",
                "enum": ["format", "validate", "query", "minify"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to JSON file (alternative to 'input').",
            },
            "input": {
                "type": "string",
                "description": "Raw JSON string (alternative to 'file_path').",
            },
            "path": {
                "type": "string",
                "description": "Dot-notation path for query (e.g. 'data.items.0.name').",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        file_path = kwargs.get("file_path", "")
        raw_input = kwargs.get("input", "")
        query_path = kwargs.get("path", "")

        if file_path:
            fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
            fp = fp.resolve()
            if not fp.is_file():
                return ToolResult.fail(f"File not found: {fp}")
            try:
                raw_input = fp.read_text(encoding="utf-8")
            except Exception as e:
                return ToolResult.fail(f"Read error: {e}")

        if not raw_input:
            return ToolResult.fail("Provide file_path or input.")

        try:
            data = json.loads(raw_input)
        except json.JSONDecodeError as e:
            if action == "validate":
                return ToolResult.ok(f"INVALID: {e}")
            return ToolResult.fail(f"Invalid JSON: {e}")

        if action == "validate":
            return ToolResult.ok("VALID JSON")
        elif action == "format":
            return ToolResult.ok(json.dumps(data, indent=2, ensure_ascii=False))
        elif action == "minify":
            return ToolResult.ok(json.dumps(data, separators=(",", ":")))
        elif action == "query":
            if not query_path:
                return ToolResult.fail("path required for query action.")
            return self._query(data, query_path)
        return ToolResult.fail(f"Unknown action: {action}")

    def _query(self, data: Any, path: str) -> ToolResult:
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                if part not in current:
                    return ToolResult.fail(f"Key not found: {part}")
                current = current[part]
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return ToolResult.fail(f"Invalid index: {part}")
            else:
                return ToolResult.fail(f"Cannot traverse into {type(current).__name__} with key {part}")
        if isinstance(current, (dict, list)):
            return ToolResult.ok(json.dumps(current, indent=2, ensure_ascii=False))
        return ToolResult.ok(str(current))
