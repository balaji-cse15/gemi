"""EnvTool — get, set, list environment variables."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class EnvTool(Tool):
    name = "env"
    description = (
        "Get, set, or list environment variables. "
        "Actions: 'get', 'set', 'list', 'unset'."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'get', 'set', 'list', 'unset'.",
                "enum": ["get", "set", "list", "unset"],
            },
            "name": {
                "type": "string",
                "description": "Variable name (for get/set/unset).",
            },
            "value": {
                "type": "string",
                "description": "Value to set (for set action).",
            },
            "filter": {
                "type": "string",
                "description": "Filter variable names (for list action).",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")
        value = kwargs.get("value", "")
        filt = kwargs.get("filter", "")

        if action == "get":
            if not name:
                return ToolResult.fail("name required for get.")
            val = os.environ.get(name)
            if val is None:
                return ToolResult.ok(f"{name} is not set")
            return ToolResult.ok(f"{name}={val}")

        elif action == "set":
            if not name:
                return ToolResult.fail("name required for set.")
            os.environ[name] = value
            return ToolResult.ok(f"Set {name}={value}")

        elif action == "unset":
            if not name:
                return ToolResult.fail("name required for unset.")
            os.environ.pop(name, None)
            return ToolResult.ok(f"Unset {name}")

        elif action == "list":
            items = sorted(os.environ.items())
            if filt:
                fl = filt.lower()
                items = [(k, v) for k, v in items if fl in k.lower()]
            lines = [f"{k}={v[:100]}" for k, v in items]
            return ToolResult.ok("\n".join(lines[:200]) or "No matching variables.")

        return ToolResult.fail(f"Unknown action: {action}")
