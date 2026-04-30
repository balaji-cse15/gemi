"""NpmTool — npm and npx commands."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class NpmTool(Tool):
    name = "npm"
    dangerous = True
    description = (
        "Run npm or npx commands. Supports install, run, test, build, init, "
        "list, outdated, audit, and npx for one-off package execution."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "args": {
                "type": "string",
                "description": "npm arguments as string (e.g. 'install', 'run build', 'test').",
            },
            "use_npx": {
                "type": "boolean",
                "description": "Use npx instead of npm (default false).",
                "default": False,
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
        use_npx = bool(kwargs.get("use_npx", False))
        timeout = int(kwargs.get("timeout", 300))
        if not args_str:
            return ToolResult.fail("No arguments provided.")
        cmd = f"{'npx' if use_npx else 'npm'} {args_str}"
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=str(workspace),
                capture_output=True, text=True, timeout=timeout,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            output = output.strip()
            if len(output) > 30000:
                output = output[:30000] + "\n... (truncated)"
            if proc.returncode != 0:
                return ToolResult(output="", error=f"Exit code {proc.returncode}\n{output}", is_error=True)
            return ToolResult.ok(output or "(no output)")
        except subprocess.TimeoutExpired:
            return ToolResult.fail(f"npm timed out after {timeout}s")
        except Exception as e:
            return ToolResult.fail(str(e))
