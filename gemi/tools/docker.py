"""DockerTool — docker and docker-compose commands."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class DockerTool(Tool):
    name = "docker"
    dangerous = True
    description = (
        "Run docker or docker-compose commands. Supports ps, images, build, run, "
        "exec, logs, stop, rm, pull, push, compose up/down, and more."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "args": {
                "type": "string",
                "description": "Docker arguments (e.g. 'ps', 'build .', 'compose up -d').",
            },
            "compose": {
                "type": "boolean",
                "description": "Use docker compose instead of docker (default false).",
                "default": False,
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 120).",
                "default": 120,
            },
        },
        "required": ["args"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        args_str = kwargs.get("args", "")
        compose = bool(kwargs.get("compose", False))
        timeout = int(kwargs.get("timeout", 120))
        if not args_str:
            return ToolResult.fail("No arguments provided.")
        cmd = f"docker {'compose ' if compose else ''}{args_str}"
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
            return ToolResult.fail(f"docker timed out after {timeout}s")
        except Exception as e:
            return ToolResult.fail(str(e))
