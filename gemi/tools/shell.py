"""ShellTool — cross-platform smart shell wrapper.

Auto-picks the best shell for the host:
  - Linux/macOS: bash (or sh fallback)
  - Windows:     bash (Git Bash) → cmd.exe → powershell

Use this when you don't care which shell, just want it to work. Use the
specific bash/powershell/cmd tools when you need that exact dialect.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from ._shell_common import find_bash, find_cmd, find_powershell, run_shell, SHELL_SCHEMA_PROPS


class ShellTool(Tool):
    name = "shell"
    dangerous = True
    description = (
        "Smart cross-platform shell. On Linux/macOS uses bash; on Windows "
        "auto-picks bash (Git Bash) → cmd.exe → powershell. Use this when "
        "the command works in any standard shell. For platform-specific "
        "syntax, use the bash/cmd/powershell tools directly."
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
        if bash:
            if bash.lower().endswith("wsl.exe") or bash.lower().endswith("wsl"):
                argv = [bash, "bash", "-c", command]
            else:
                argv = [bash, "-c", command]
            shell = False
            label = "bash"
        elif sys.platform == "win32":
            cmd_path = find_cmd()
            if cmd_path:
                argv = [cmd_path, "/c", command]
                shell = False
                label = "cmd"
            else:
                ps = find_powershell()
                if not ps:
                    return ToolResult.fail("no shell found on PATH")
                argv = [ps, "-NoProfile", "-NonInteractive", "-Command", command]
                shell = False
                label = "powershell"
        else:
            argv = ["/bin/sh", "-c", command]
            shell = False
            label = "sh"

        exit_code, output = run_shell(
            argv, cwd=cwd, env=env, stdin=stdin, timeout=timeout, shell=shell,
        )
        prefix = f"[shell={label}]\n" if label != "bash" else ""
        if exit_code != 0:
            return ToolResult(
                output="",
                error=f"{prefix}Exit {exit_code}\n{output}",
                is_error=True,
            )
        return ToolResult.ok(prefix + (output or "(no output)"))
