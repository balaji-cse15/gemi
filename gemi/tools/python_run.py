"""PythonTool — run Python code."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class PythonTool(Tool):
    name = "python"
    dangerous = True
    description ="Run Python code in the workspace using the current Python interpreter."
    input_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120).",
                "default": 120,
            },
        },
        "required": ["code"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        code = kwargs.get("code", "")
        timeout = int(kwargs.get("timeout", 120))
        if not code.strip():
            return ToolResult.fail("No code provided.")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            output = output.strip()
            if proc.returncode != 0:
                return ToolResult(output="", error=f"Exit code {proc.returncode}\n{output}", is_error=True)
            return ToolResult.ok(output or "(no output)")
        except subprocess.TimeoutExpired:
            return ToolResult.fail(f"Python timed out after {timeout}s")
        except Exception as e:
            return ToolResult.fail(str(e))
