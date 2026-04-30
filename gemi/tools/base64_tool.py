"""Base64Tool — encode and decode base64."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class Base64Tool(Tool):
    name = "base64"
    description = (
        "Encode or decode base64 data. "
        "Can encode/decode strings or files."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'encode' or 'decode'.",
                "enum": ["encode", "decode"],
            },
            "text": {
                "type": "string",
                "description": "String to encode/decode.",
            },
            "file_path": {
                "type": "string",
                "description": "File to encode (reads binary). For decode, writes output to this path.",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        text = kwargs.get("text", "")
        file_path = kwargs.get("file_path", "")

        if action == "encode":
            if file_path:
                fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
                fp = fp.resolve()
                if not fp.is_file():
                    return ToolResult.fail(f"File not found: {fp}")
                try:
                    data = fp.read_bytes()
                    encoded = base64.b64encode(data).decode("ascii")
                    if len(encoded) > 100000:
                        encoded = encoded[:100000] + "\n... (truncated)"
                    return ToolResult.ok(encoded)
                except Exception as e:
                    return ToolResult.fail(f"Encode error: {e}")
            elif text:
                encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
                return ToolResult.ok(encoded)
            else:
                return ToolResult.fail("Provide text or file_path to encode.")

        elif action == "decode":
            if not text:
                return ToolResult.fail("Provide base64 text to decode.")
            try:
                decoded = base64.b64decode(text)
            except Exception as e:
                return ToolResult.fail(f"Invalid base64: {e}")
            if file_path:
                fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
                fp = fp.resolve()
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(decoded)
                return ToolResult.ok(f"Decoded {len(decoded)} bytes to {fp}")
            else:
                try:
                    return ToolResult.ok(decoded.decode("utf-8"))
                except UnicodeDecodeError:
                    return ToolResult.ok(f"(binary data, {len(decoded)} bytes)")

        return ToolResult.fail(f"Unknown action: {action}")
