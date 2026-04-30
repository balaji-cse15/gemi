"""BashTool — execute commands in a real bash interpreter.

On Windows, locates Git Bash (or WSL bash). Falls back to cmd.exe with a
warning if no bash is found. Supports cwd, env vars, stdin, and per-call
timeout up to 10 minutes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from ._shell_common import find_bash, run_shell, SHELL_SCHEMA_PROPS


class BashTool(Tool):
    name = "bash"
    dangerous = True
    description = (
        "Execute a bash/shell command. Returns combined stdout+stderr with "
        "exit code on error. On Windows, uses Git Bash or WSL when available "
        "(real bash semantics). Supports cwd, env vars, and stdin piping."
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

        bash = find_bash()
        if not bash:
            # Fall back to cmd.exe on Windows or sh on Unix
            if sys.platform == "win32":
                exit_code, output = run_shell(
                    command, cwd=cwd, env=env, stdin=stdin,
                    timeout=timeout, shell=True,
                )
                if exit_code != 0:
                    return ToolResult(
                        output="",
                        error=f"[no bash on PATH — used cmd.exe instead]\nExit {exit_code}\n{output}",
                        is_error=True,
                    )
                return ToolResult.ok(f"[no bash — used cmd.exe]\n{output}")
            return ToolResult.fail("bash not found on PATH")

        # Use bash.exe / wsl with -c "<command>"
        if bash.lower().endswith("wsl.exe") or bash.lower().endswith("wsl"):
            argv = [bash, "bash", "-c", command]
        else:
            argv = [bash, "-c", command]

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
