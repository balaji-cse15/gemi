"""EncodeTool — encode/decode: URL, HTML entities, hex, binary."""
from __future__ import annotations

import html
import binascii
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from .base import Tool, ToolResult


class EncodeTool(Tool):
    name = "encode"
    description = (
        "Encode or decode text in various formats. "
        "Formats: 'url' (percent-encoding), 'html' (HTML entities), "
        "'hex' (hexadecimal), 'binary' (0s and 1s), 'rot13'."
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
            "format": {
                "type": "string",
                "description": "Format: 'url', 'html', 'hex', 'binary', 'rot13'.",
                "enum": ["url", "html", "hex", "binary", "rot13"],
            },
            "text": {
                "type": "string",
                "description": "Text to encode or decode.",
            },
        },
        "required": ["action", "format", "text"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        fmt = kwargs.get("format", "")
        text = kwargs.get("text", "")

        if not text:
            return ToolResult.fail("No text provided.")

        try:
            if fmt == "url":
                if action == "encode":
                    return ToolResult.ok(quote(text, safe=""))
                else:
                    return ToolResult.ok(unquote(text))

            elif fmt == "html":
                if action == "encode":
                    return ToolResult.ok(html.escape(text))
                else:
                    return ToolResult.ok(html.unescape(text))

            elif fmt == "hex":
                if action == "encode":
                    return ToolResult.ok(binascii.hexlify(text.encode()).decode())
                else:
                    return ToolResult.ok(binascii.unhexlify(text).decode())

            elif fmt == "binary":
                if action == "encode":
                    bits = " ".join(format(b, "08b") for b in text.encode())
                    return ToolResult.ok(bits)
                else:
                    clean = text.replace(" ", "")
                    chars = [chr(int(clean[i:i+8], 2)) for i in range(0, len(clean), 8)]
                    return ToolResult.ok("".join(chars))

            elif fmt == "rot13":
                import codecs
                return ToolResult.ok(codecs.encode(text, "rot_13"))

        except Exception as e:
            return ToolResult.fail(f"{action} error ({fmt}): {e}")

        return ToolResult.fail(f"Unknown format: {fmt}")
