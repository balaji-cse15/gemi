"""ClipboardTool — copy/paste system clipboard."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ClipboardTool(Tool):
    name = "clipboard"
    description = (
        "Read from or write to the system clipboard. "
        "Actions: 'copy' (write text to clipboard), 'paste' (read text from clipboard)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'copy' or 'paste'.",
                "enum": ["copy", "paste"],
            },
            "text": {
                "type": "string",
                "description": "Text to copy to clipboard (required for 'copy').",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "paste":
            return self._paste()
        elif action == "copy":
            text = kwargs.get("text", "")
            if not text:
                return ToolResult.fail("No text provided to copy.")
            return self._copy(text)
        return ToolResult.fail(f"Unknown action: {action}")

    def _paste(self) -> ToolResult:
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5,
                )
                return ToolResult.ok(result.stdout.rstrip("\r\n"))
            elif sys.platform == "darwin":
                result = subprocess.run(
                    ["pbpaste"], capture_output=True, text=True, timeout=5,
                )
                return ToolResult.ok(result.stdout)
            else:
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, text=True, timeout=5,
                )
                return ToolResult.ok(result.stdout)
        except Exception as e:
            return ToolResult.fail(f"Clipboard read failed: {e}")

    def _copy(self, text: str) -> ToolResult:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["powershell", "-Command", "Set-Clipboard", "-Value", text],
                    capture_output=True, timeout=5,
                )
            elif sys.platform == "darwin":
                subprocess.run(
                    ["pbcopy"], input=text, text=True, timeout=5,
                )
            else:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text, text=True, timeout=5,
                )
            return ToolResult.ok(f"Copied {len(text)} chars to clipboard.")
        except Exception as e:
            return ToolResult.fail(f"Clipboard write failed: {e}")
