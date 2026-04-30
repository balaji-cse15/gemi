"""TomlTool — parse, validate, and format TOML."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


class TomlTool(Tool):
    name = "toml"
    description = (
        "Parse, validate, or convert TOML data. "
        "Actions: 'parse' (to JSON), 'validate', 'get' (extract key by dot-path)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'parse', 'validate', 'get'.",
                "enum": ["parse", "validate", "get"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to TOML file.",
            },
            "input": {
                "type": "string",
                "description": "Raw TOML string.",
            },
            "key": {
                "type": "string",
                "description": "Dot-notation key path for 'get' action (e.g. 'project.name').",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        if tomllib is None:
            return ToolResult.fail("tomllib not available. Requires Python 3.11+ or pip install tomli")

        action = kwargs.get("action", "")
        file_path = kwargs.get("file_path", "")
        raw = kwargs.get("input", "")
        key = kwargs.get("key", "")

        if file_path:
            fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
            fp = fp.resolve()
            if not fp.is_file():
                return ToolResult.fail(f"File not found: {fp}")
            raw = fp.read_text(encoding="utf-8")

        if not raw:
            return ToolResult.fail("Provide file_path or input.")

        if action == "validate":
            try:
                tomllib.loads(raw)
                return ToolResult.ok("VALID TOML")
            except Exception as e:
                return ToolResult.ok(f"INVALID: {e}")

        elif action == "parse":
            try:
                data = tomllib.loads(raw)
                return ToolResult.ok(json.dumps(data, indent=2, default=str))
            except Exception as e:
                return ToolResult.fail(f"TOML parse error: {e}")

        elif action == "get":
            if not key:
                return ToolResult.fail("key parameter required for get action.")
            try:
                data = tomllib.loads(raw)
                current = data
                for part in key.split("."):
                    if isinstance(current, dict):
                        current = current[part]
                    else:
                        return ToolResult.fail(f"Cannot traverse into {type(current).__name__}")
                if isinstance(current, (dict, list)):
                    return ToolResult.ok(json.dumps(current, indent=2, default=str))
                return ToolResult.ok(str(current))
            except KeyError as e:
                return ToolResult.fail(f"Key not found: {e}")
            except Exception as e:
                return ToolResult.fail(f"Error: {e}")

        return ToolResult.fail(f"Unknown action: {action}")
