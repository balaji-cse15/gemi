"""CmdTool — execute a Windows cmd.exe command.

Distinct from bash and powershell — uses cmd.exe directly so bat scripts,
%ENV% variables, and `start` work as expected. Returns gracefully on
non-Windows systems.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from ._shell_common import find_cmd, run_shell, SHELL_SCHEMA_PROPS


class CmdTool(Tool):
    name = "cmd"
    dangerous = True
    description = (
        "Run a Windows cmd.exe command. Use for .bat scripts, %ENV% expansion, "
        "DIR/COPY/MOVE/DEL, registry edits via REG, and other cmd-specific "
        "operations. Returns an error on non-Windows systems."
    )
    input_schema = {
        "type": "object",
        "properties": SHELL_SCHEMA_PROPS,
        "required": ["command"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult.fail("cmd.exe is Windows-only — use bash or powershell on this platform")

        command = kwargs.get("command", "")
        if not command:
            return ToolResult.fail("No command provided.")

        cwd = kwargs.get("cwd") or workspace
        env = kwargs.get("env") or {}
        stdin = kwargs.get("stdin")
        timeout = max(1, min(int(kwargs.get("timeout", 120)), 600))

        cmd_path = find_cmd()
        if not cmd_path:
            return ToolResult.fail("cmd.exe not found")

        argv = [cmd_path, "/c", command]
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
