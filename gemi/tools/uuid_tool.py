"""UuidTool — generate and validate UUIDs."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class UuidTool(Tool):
    name = "uuid"
    description = (
        "Generate or validate UUIDs. "
        "Actions: 'v4' (random), 'v1' (time-based), 'v5' (namespace+name), "
        "'validate' (check if valid UUID), 'batch' (generate multiple)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'v4', 'v1', 'v5', 'validate', 'batch'.",
                "enum": ["v4", "v1", "v5", "validate", "batch"],
            },
            "input": {
                "type": "string",
                "description": "UUID to validate, or name for v5 generation.",
            },
            "namespace": {
                "type": "string",
                "description": "Namespace for v5: 'dns', 'url', 'oid', 'x500'.",
                "default": "dns",
            },
            "count": {
                "type": "integer",
                "description": "Number of UUIDs for batch (default 5, max 50).",
                "default": 5,
            },
        },
        "required": ["action"],
    }

    NAMESPACES = {
        "dns": uuid.NAMESPACE_DNS,
        "url": uuid.NAMESPACE_URL,
        "oid": uuid.NAMESPACE_OID,
        "x500": uuid.NAMESPACE_X500,
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "v4":
            return ToolResult.ok(str(uuid.uuid4()))

        elif action == "v1":
            return ToolResult.ok(str(uuid.uuid1()))

        elif action == "v5":
            name = kwargs.get("input", "")
            if not name:
                return ToolResult.fail("input (name) required for v5.")
            ns_key = kwargs.get("namespace", "dns")
            ns = self.NAMESPACES.get(ns_key, uuid.NAMESPACE_DNS)
            return ToolResult.ok(str(uuid.uuid5(ns, name)))

        elif action == "validate":
            value = kwargs.get("input", "")
            if not value:
                return ToolResult.fail("input required for validate.")
            try:
                parsed = uuid.UUID(value)
                return ToolResult.ok(f"Valid UUID v{parsed.version}: {parsed}")
            except ValueError:
                return ToolResult.ok(f"Invalid UUID: {value}")

        elif action == "batch":
            count = min(int(kwargs.get("count", 5)), 50)
            uuids = [str(uuid.uuid4()) for _ in range(count)]
            return ToolResult.ok("\n".join(uuids))

        return ToolResult.fail(f"Unknown action: {action}")
