"""ProcessTool — list and kill system processes."""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ProcessTool(Tool):
    name = "process"
    dangerous = True
    description = (
        "List running processes or kill a process by PID. "
        "Actions: 'list' (filter by name), 'kill' (by PID)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'list' or 'kill'.",
                "enum": ["list", "kill"],
            },
            "filter": {
                "type": "string",
                "description": "Filter process list by name (for list action).",
            },
            "pid": {
                "type": "integer",
                "description": "Process ID to kill (for kill action).",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        if action == "list":
            return self._list(kwargs.get("filter", ""))
        elif action == "kill":
            pid = kwargs.get("pid")
            if not pid:
                return ToolResult.fail("pid required for kill action.")
            return self._kill(int(pid))
        return ToolResult.fail(f"Unknown action: {action}")

    def _list(self, name_filter: str) -> ToolResult:
        try:
            if os.name == "nt":
                cmd = "tasklist /FO CSV /NH"
            else:
                cmd = "ps aux"
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            lines = proc.stdout.strip().splitlines()
            if name_filter:
                nf = name_filter.lower()
                lines = [l for l in lines if nf in l.lower()]
            output = "\n".join(lines[:200])
            if len(lines) > 200:
                output += f"\n... ({len(lines)} total, showing 200)"
            return ToolResult.ok(output or "No processes found.")
        except Exception as e:
            return ToolResult.fail(f"Process list failed: {e}")

    def _kill(self, pid: int) -> ToolResult:
        try:
            os.kill(pid, signal.SIGTERM)
            return ToolResult.ok(f"Sent SIGTERM to PID {pid}")
        except ProcessLookupError:
            return ToolResult.fail(f"No process with PID {pid}")
        except PermissionError:
            return ToolResult.fail(f"Permission denied for PID {pid}")
        except Exception as e:
            return ToolResult.fail(f"Kill failed: {e}")
