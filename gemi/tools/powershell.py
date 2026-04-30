"""PowerShellTool — execute PowerShell commands.

Prefers pwsh (PowerShell 7+) over Windows-only powershell.exe. Supports
cwd, env vars, stdin, and per-call timeout.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from ._shell_common import find_powershell, run_shell, SHELL_SCHEMA_PROPS


class PowerShellTool(Tool):
    name = "powershell"
    dangerous = True
    description = (
        "Execute a PowerShell command. Uses pwsh (cross-platform PowerShell 7+) "
        "if installed, else Windows powershell.exe. Use for Windows-specific "
        "operations, registry, .NET, COM, WMI/CIM, and PS-specific cmdlets."
    )
    input_schema = {
        "type": "object",
        "properties": SHELL_SCHEMA_PROPS,
        "required": ["command"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        if not command:
            return ToolResult.fail("No command provided.")

        cwd = kwargs.get("cwd") or workspace
        env = kwargs.get("env") or {}
        stdin = kwargs.get("stdin")
        timeout = max(1, min(int(kwargs.get("timeout", 120)), 600))

        ps = find_powershell()
        if not ps:
            return ToolResult.fail("PowerShell not found (need pwsh or powershell.exe)")

        argv = [ps, "-NoProfile", "-NonInteractive", "-Command", command]
        exit_code, output = run_shell(
            argv, cwd=cwd, env=env, stdin=stdin, timeout=timeout, shell=False,
        )
        if exit_code != 0:
            return ToolResult(
                output="",
                error=f"Exit {exit_code}\n{output}",
                is_error=True,
            )
        return ToolResult.ok(output or "(no output)")
