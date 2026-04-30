"""Task-runner detection + dispatch.

Auto-detects task runners in the workspace:
  - Makefile         → make
  - justfile         → just
  - package.json     → npm/yarn/pnpm scripts
  - pyproject.toml   → uv/poetry/hatch run, plus python -m
  - Taskfile.yml     → task
  - Cargo.toml       → cargo
  - go.mod           → go
  - composer.json    → composer
  - dockerfile       → docker

Two modes:
  - list          enumerate available tasks
  - run <task>    execute a task with optional args
"""
from __future__ import annotations

import json
import re
import subprocess
import shutil
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from ._shell_common import run_shell


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _detect_runners(workspace: Path) -> list[dict]:
    """Find every task runner with config files in the workspace root."""
    runners: list[dict] = []

    if (workspace / "Makefile").is_file() and shutil.which("make"):
        # Parse target names
        try:
            text = (workspace / "Makefile").read_text(encoding="utf-8", errors="replace")
            targets = re.findall(r"^([A-Za-z0-9_.-]+)\s*:", text, re.MULTILINE)
            targets = [t for t in targets if not t.startswith(".")]
        except Exception:
            targets = []
        runners.append({"runner": "make", "config": "Makefile", "tasks": targets[:30]})

    if (workspace / "justfile").is_file() and shutil.which("just"):
        try:
            text = (workspace / "justfile").read_text(encoding="utf-8", errors="replace")
            tasks = re.findall(r"^([A-Za-z0-9_-]+)(?:\s+\w+)?\s*:", text, re.MULTILINE)
        except Exception:
            tasks = []
        runners.append({"runner": "just", "config": "justfile", "tasks": tasks[:30]})

    pkg = workspace / "package.json"
    if pkg.is_file():
        data = _read_json(pkg) or {}
        scripts = list((data.get("scripts") or {}).keys())
        manager = "npm"
        if (workspace / "pnpm-lock.yaml").exists():
            manager = "pnpm"
        elif (workspace / "yarn.lock").exists():
            manager = "yarn"
        elif (workspace / "bun.lockb").exists() or (workspace / "bun.lock").exists():
            manager = "bun"
        runners.append({
            "runner": manager, "config": "package.json", "tasks": scripts[:30],
            "command_template": f"{manager} run {{task}}",
        })

    pp = workspace / "pyproject.toml"
    if pp.is_file():
        text = pp.read_text(encoding="utf-8", errors="replace")
        scripts = re.findall(r"\[(?:tool\.)?(?:poe|hatch\.envs\.[^.]+|poetry\.scripts|project\.scripts)\.tasks?\]", text)
        # Try to extract simple key=value scripts under common sections
        tasks = []
        m = re.search(r"\[tool\.poe\.tasks\]\s*\n((?:[^[]+\n)*)", text)
        if m:
            tasks = re.findall(r"^([a-zA-Z0-9_-]+)\s*=", m.group(1), re.MULTILINE)
        runners.append({
            "runner": "python",
            "config": "pyproject.toml",
            "tasks": tasks[:20],
            "_note": "use `python -m <module>` for general dispatch",
        })

    if (workspace / "Taskfile.yml").is_file() and shutil.which("task"):
        runners.append({"runner": "task", "config": "Taskfile.yml", "tasks": []})

    if (workspace / "Cargo.toml").is_file() and shutil.which("cargo"):
        runners.append({"runner": "cargo", "config": "Cargo.toml",
                        "tasks": ["build", "test", "run", "check", "clippy", "fmt"]})

    if (workspace / "go.mod").is_file() and shutil.which("go"):
        runners.append({"runner": "go", "config": "go.mod",
                        "tasks": ["build", "test", "run", "vet", "mod tidy"]})

    if (workspace / "Dockerfile").is_file() and shutil.which("docker"):
        runners.append({"runner": "docker", "config": "Dockerfile",
                        "tasks": ["build", "run"]})

    return runners


class TaskRunnerTool(Tool):
    name = "task_runner"
    dangerous = True
    description = (
        "Detect and run project task runners (make/just/npm/pnpm/yarn/bun/"
        "cargo/go/python/docker). action='list' enumerates configs and "
        "available tasks. action='run' executes a task."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "list | run",
                "default": "list",
            },
            "runner": {
                "type": "string",
                "description": "Specific runner (npm, make, etc.). Auto-detected if omitted.",
            },
            "task": {
                "type": "string",
                "description": "Task name (for action=run).",
            },
            "extra_args": {
                "type": "string",
                "description": "Additional arguments to append to the command.",
            },
            "cwd": {"type": "string"},
            "timeout": {"type": "integer", "default": 600},
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = (kwargs.get("action") or "list").lower()
        cwd = Path(kwargs.get("cwd") or workspace).resolve()
        timeout = max(1, min(int(kwargs.get("timeout", 600)), 1800))

        runners = _detect_runners(cwd)
        if action == "list":
            if not runners:
                return ToolResult.ok(f"# No task runners found in {cwd}")
            out = [f"# Task runners — {cwd}\n"]
            for r in runners:
                out.append(f"## {r['runner']}  ({r['config']})")
                if r.get("tasks"):
                    for t in r["tasks"]:
                        out.append(f"  • {t}")
                else:
                    out.append("  (no tasks parsed; run anything via the runner)")
                if r.get("_note"):
                    out.append(f"  note: {r['_note']}")
                out.append("")
            return ToolResult.ok("\n".join(out))

        if action == "run":
            task = kwargs.get("task", "").strip()
            if not task:
                return ToolResult.fail("missing task")
            requested_runner = kwargs.get("runner", "").strip().lower()
            extra = kwargs.get("extra_args", "").strip()

            chosen = None
            if requested_runner:
                chosen = next((r for r in runners if r["runner"] == requested_runner), None)
                if not chosen:
                    return ToolResult.fail(
                        f"runner '{requested_runner}' not detected here; "
                        f"available: {', '.join(r['runner'] for r in runners) or 'none'}"
                    )
            else:
                # Heuristic: pick the runner whose task list contains this name
                for r in runners:
                    if task in (r.get("tasks") or []):
                        chosen = r
                        break
                if not chosen and runners:
                    chosen = runners[0]
            if not chosen:
                return ToolResult.fail("no runners detected")

            runner = chosen["runner"]
            if runner in ("npm", "pnpm", "yarn", "bun"):
                cmd = f"{runner} run {task}"
            elif runner == "make":
                cmd = f"make {task}"
            elif runner == "just":
                cmd = f"just {task}"
            elif runner == "cargo":
                cmd = f"cargo {task}"
            elif runner == "go":
                cmd = f"go {task}"
            elif runner == "task":
                cmd = f"task {task}"
            elif runner == "python":
                cmd = f"python -m {task}"
            elif runner == "docker":
                cmd = f"docker {task}"
            else:
                return ToolResult.fail(f"don't know how to dispatch {runner}")

            if extra:
                cmd += f" {extra}"

            ec, out = run_shell(cmd, cwd=cwd, timeout=timeout, shell=True)
            if ec != 0:
                return ToolResult(output="", error=f"$ {cmd}\n[exit {ec}]\n{out}", is_error=True)
            return ToolResult.ok(f"$ {cmd}\n{out}")

        return ToolResult.fail(f"unknown action: {action}")
