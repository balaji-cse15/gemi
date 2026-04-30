"""PipTool — pip package management."""
from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class PipTool(Tool):
    name = "pip"
    dangerous = True
    description ="Run pip commands (install, list, show, freeze, uninstall, etc.)."
    input_schema = {
        "type": "object",
        "properties": {
            "args": {
                "type": "string",
                "description": "Pip arguments as a string (e.g. 'install requests', 'list', 'show numpy').",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 300).",
                "default": 300,
            },
        },
        "required": ["args"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        args_str = kwargs.get("args", "")
        timeout = int(kwargs.get("timeout", 300))
        if not args_str:
            return ToolResult.fail("No pip arguments provided.")
        try:
            parts = shlex.split(args_str)
        except ValueError:
            parts = args_str.split()
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", *parts],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            output = output.strip()
            if proc.returncode != 0:
                return ToolResult(output="", error=f"pip exit code {proc.returncode}\n{output}", is_error=True)
            return ToolResult.ok(output or "(no output)")
        except subprocess.TimeoutExpired:
            return ToolResult.fail(f"pip timed out after {timeout}s")
        except Exception as e:
            return ToolResult.fail(str(e))
