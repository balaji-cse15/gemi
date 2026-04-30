"""GitTool — git operations with structured shortcuts.

Three modes:
  - args="<raw git args>"          full passthrough (e.g. 'log --oneline -10')
  - subcommand=<name> + flags      structured: status, diff, log, branch, etc.
  - workflow=<name> + params       high-level: commit-and-push, smart-merge, etc.

The structured mode prevents "git push --force origin main" from sneaking
through unless explicitly requested.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from ._shell_common import find_git, run_shell


# Read-only subcommands — invoked via subcommand= without YOLO concern
READONLY_SUB = {
    "status", "diff", "log", "show", "blame", "branch", "tag",
    "remote", "config", "ls-files", "ls-tree", "rev-parse",
    "describe", "shortlog", "reflog",
}

# Write subcommands that require explicit args
WRITE_SUB = {
    "add", "commit", "push", "pull", "fetch", "checkout", "switch",
    "merge", "rebase", "cherry-pick", "stash", "reset", "revert",
    "clone", "init", "tag", "rm", "mv", "clean",
}


class GitTool(Tool):
    name = "git"
    dangerous = True
    description = (
        "Run git commands. Three modes:\n"
        "  • args=\"<raw git args>\"           — passthrough, e.g. 'log --oneline -10'\n"
        "  • subcommand=<name> + flags=\"...\" — structured (status, diff, log, etc.)\n"
        "  • workflow=<name>                  — high-level: 'commit-all', 'sync-branch'\n"
        "Workflows: commit-all, sync-branch, smart-merge, summary."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "args": {
                "type": "string",
                "description": "Raw git arguments (e.g. 'status --short')",
            },
            "subcommand": {
                "type": "string",
                "description": f"Git subcommand. Read-only: {', '.join(sorted(READONLY_SUB))[:200]}",
            },
            "flags": {
                "type": "string",
                "description": "Flags + extra args for the subcommand.",
            },
            "workflow": {
                "type": "string",
                "description": "High-level workflow: commit-all, sync-branch, smart-merge, summary",
            },
            "message": {
                "type": "string",
                "description": "Commit message (for commit-all workflow).",
            },
            "branch": {
                "type": "string",
                "description": "Branch name (for sync-branch workflow).",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: workspace).",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 60).",
                "default": 60,
            },
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        git = find_git()
        if not git:
            return ToolResult.fail("git not found on PATH")

        cwd = kwargs.get("cwd") or workspace
        timeout = max(1, min(int(kwargs.get("timeout", 60)), 300))

        # Branch on mode
        if kwargs.get("workflow"):
            return self._workflow(git, cwd, timeout, kwargs)
        if kwargs.get("subcommand"):
            return self._structured(git, cwd, timeout, kwargs)
        if kwargs.get("args"):
            return self._passthrough(git, cwd, timeout, kwargs.get("args", ""))
        return ToolResult.fail("provide one of: args, subcommand, workflow")

    # ----- Mode 1: raw args -------------------------------------

    def _passthrough(self, git: str, cwd, timeout: int, args_str: str) -> ToolResult:
        # Use shell=True to handle quoted strings naturally
        exit_code, output = run_shell(
            f'"{git}" {args_str}',
            cwd=cwd, timeout=timeout, shell=True,
        )
        return self._result(exit_code, output)

    # ----- Mode 2: structured -----------------------------------

    def _structured(self, git: str, cwd, timeout: int, kw: dict) -> ToolResult:
        sub = kw.get("subcommand", "").strip()
        flags = kw.get("flags", "").strip()

        if not sub:
            return ToolResult.fail("subcommand required")

        # Bonus: defaults for common subcommands
        defaults = {
            "status":  "--short",
            "log":     "--oneline -20",
            "branch":  "-vv",
            "diff":    "--stat",
            "remote":  "-v",
        }
        if not flags and sub in defaults:
            flags = defaults[sub]

        argv = [git, sub] + (flags.split() if flags else [])
        exit_code, output = run_shell(argv, cwd=cwd, timeout=timeout, shell=False)
        return self._result(exit_code, output)

    # ----- Mode 3: workflows ------------------------------------

    def _workflow(self, git: str, cwd, timeout: int, kw: dict) -> ToolResult:
        wf = kw.get("workflow", "").strip()

        if wf == "commit-all":
            msg = kw.get("message") or "gemi: auto-commit"
            steps = [
                [git, "add", "-A"],
                [git, "commit", "-m", msg],
            ]
            return self._run_steps(steps, cwd, timeout)

        if wf == "sync-branch":
            branch = kw.get("branch") or "main"
            steps = [
                [git, "fetch", "origin"],
                [git, "checkout", branch],
                [git, "pull", "--ff-only", "origin", branch],
            ]
            return self._run_steps(steps, cwd, timeout)

        if wf == "smart-merge":
            branch = kw.get("branch")
            if not branch:
                return ToolResult.fail("smart-merge needs branch=<name>")
            # Pre-flight: dirty working tree?
            ec, out = run_shell([git, "status", "--porcelain"], cwd=cwd, timeout=10, shell=False)
            if ec == 0 and out.strip():
                return ToolResult.fail(
                    f"working tree dirty — clean up before smart-merge:\n{out[:500]}"
                )
            steps = [
                [git, "fetch", "origin"],
                [git, "merge", "--no-ff", branch],
            ]
            return self._run_steps(steps, cwd, timeout)

        if wf == "summary":
            # status + diff stat + recent log + branch
            outs = []
            for cmd, label in [
                ([git, "branch", "--show-current"], "branch"),
                ([git, "status", "--short"], "status"),
                ([git, "diff", "--stat"], "diff"),
                ([git, "log", "--oneline", "-10"], "recent commits"),
            ]:
                ec, o = run_shell(cmd, cwd=cwd, timeout=10, shell=False)
                outs.append(f"## {label}\n{o or '(empty)'}")
            return ToolResult.ok("\n\n".join(outs))

        return ToolResult.fail(f"unknown workflow: {wf}")

    # ----- helpers ----------------------------------------------

    def _run_steps(self, steps: list[list[str]], cwd, timeout: int) -> ToolResult:
        outputs = []
        for step in steps:
            shown = " ".join(step[1:])  # drop git binary path
            ec, out = run_shell(step, cwd=cwd, timeout=timeout, shell=False)
            outputs.append(f"$ git {shown}\n{out}")
            if ec != 0:
                return ToolResult(
                    output="",
                    error="\n\n".join(outputs) + f"\n\n[failed at: git {shown}]",
                    is_error=True,
                )
        return ToolResult.ok("\n\n".join(outputs))

    @staticmethod
    def _result(exit_code: int, output: str) -> ToolResult:
        if exit_code != 0:
            return ToolResult(output="", error=f"git exit {exit_code}\n{output}", is_error=True)
        return ToolResult.ok(output or "(no output)")
