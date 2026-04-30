"""DotenvTool — read and parse .env files safely."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class DotenvTool(Tool):
    name = "dotenv"
    description = (
        "Read and parse .env files. "
        "Actions: 'read' (show all vars with values masked), "
        "'get' (get specific key), 'keys' (list key names only), "
        "'validate' (check for common issues)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'read', 'get', 'keys', 'validate'.",
                "enum": ["read", "get", "keys", "validate"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to .env file (default: '.env' in workspace).",
                "default": ".env",
            },
            "key": {
                "type": "string",
                "description": "Key name for 'get' action.",
            },
            "show_values": {
                "type": "boolean",
                "description": "Show actual values instead of masked (default false).",
                "default": False,
            },
        },
        "required": ["action"],
    }

    def _parse_env(self, text: str) -> list[tuple[str, str]]:
        pairs = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
            if m:
                key = m.group(1)
                val = m.group(2).strip().strip("'\"")
                pairs.append((key, val))
        return pairs

    def _mask(self, val: str) -> str:
        if len(val) <= 4:
            return "****"
        return val[:2] + "*" * (len(val) - 4) + val[-2:]

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        file_path = kwargs.get("file_path", ".env")
        key = kwargs.get("key", "")
        show = bool(kwargs.get("show_values", False))

        fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
        fp = fp.resolve()

        if not fp.is_file():
            return ToolResult.fail(f"File not found: {fp}")

        try:
            text = fp.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult.fail(f"Read error: {e}")

        pairs = self._parse_env(text)

        if action == "keys":
            if not pairs:
                return ToolResult.ok("No variables found.")
            return ToolResult.ok("\n".join(k for k, _ in pairs))

        elif action == "read":
            if not pairs:
                return ToolResult.ok("No variables found.")
            lines = []
            for k, v in pairs:
                display = v if show else self._mask(v)
                lines.append(f"{k}={display}")
            return ToolResult.ok("\n".join(lines))

        elif action == "get":
            if not key:
                return ToolResult.fail("key required for get action.")
            for k, v in pairs:
                if k == key:
                    display = v if show else self._mask(v)
                    return ToolResult.ok(f"{k}={display}")
            return ToolResult.fail(f"Key not found: {key}")

        elif action == "validate":
            issues = []
            seen = set()
            for k, v in pairs:
                if k in seen:
                    issues.append(f"Duplicate key: {k}")
                seen.add(k)
                if not v:
                    issues.append(f"Empty value: {k}")
                if " " in k:
                    issues.append(f"Space in key: '{k}'")
            if not issues:
                return ToolResult.ok(f"Valid .env file: {len(pairs)} variables, no issues.")
            return ToolResult.ok(f"{len(issues)} issues:\n" + "\n".join(f"  - {i}" for i in issues))

        return ToolResult.fail(f"Unknown action: {action}")
