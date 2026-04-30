"""WatchTool — snapshot directory state for change detection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".tox", ".mypy_cache"}


class WatchTool(Tool):
    name = "watch"
    description = (
        "Snapshot directory state for change detection. "
        "Actions: 'snapshot' (capture current state), 'diff' (compare against last snapshot). "
        "Useful for detecting what changed after running a command."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'snapshot' or 'diff'.",
                "enum": ["snapshot", "diff"],
            },
            "path": {
                "type": "string",
                "description": "Directory to watch (default: workspace root).",
                "default": ".",
            },
            "glob": {
                "type": "string",
                "description": "Glob filter for files (e.g. '*.py').",
                "default": "*",
            },
        },
        "required": ["action"],
    }

    _snapshots: dict[str, dict[str, tuple[float, int]]] = {}

    def _scan(self, base: Path, file_glob: str) -> dict[str, tuple[float, int]]:
        state: dict[str, tuple[float, int]] = {}
        import fnmatch
        for fpath in sorted(base.rglob("*")):
            if any(skip in fpath.parts for skip in SKIP_DIRS):
                continue
            if not fpath.is_file():
                continue
            if file_glob != "*" and not fnmatch.fnmatch(fpath.name, file_glob):
                continue
            try:
                stat = fpath.stat()
                state[str(fpath)] = (stat.st_mtime, stat.st_size)
            except OSError:
                continue
        return state

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        watch_path = kwargs.get("path", ".")
        file_glob = kwargs.get("glob", "*")

        base = Path(watch_path)
        if not base.is_absolute():
            base = workspace / base
        base = base.resolve()

        if not base.is_dir():
            return ToolResult.fail(f"Directory not found: {base}")

        key = f"{base}|{file_glob}"

        if action == "snapshot":
            state = self._scan(base, file_glob)
            WatchTool._snapshots[key] = state
            return ToolResult.ok(f"Snapshot captured: {len(state)} files")

        elif action == "diff":
            old_state = WatchTool._snapshots.get(key)
            if old_state is None:
                return ToolResult.fail("No previous snapshot. Run 'snapshot' first.")

            new_state = self._scan(base, file_glob)
            old_keys = set(old_state.keys())
            new_keys = set(new_state.keys())

            added = sorted(new_keys - old_keys)
            removed = sorted(old_keys - new_keys)
            modified = []
            for k in sorted(old_keys & new_keys):
                if old_state[k] != new_state[k]:
                    modified.append(k)

            if not added and not removed and not modified:
                return ToolResult.ok("No changes detected.")

            lines = []
            if added:
                lines.append(f"Added ({len(added)}):")
                for f in added[:50]:
                    try:
                        lines.append(f"  + {Path(f).relative_to(workspace)}")
                    except ValueError:
                        lines.append(f"  + {f}")
            if removed:
                lines.append(f"Removed ({len(removed)}):")
                for f in removed[:50]:
                    try:
                        lines.append(f"  - {Path(f).relative_to(workspace)}")
                    except ValueError:
                        lines.append(f"  - {f}")
            if modified:
                lines.append(f"Modified ({len(modified)}):")
                for f in modified[:50]:
                    try:
                        lines.append(f"  ~ {Path(f).relative_to(workspace)}")
                    except ValueError:
                        lines.append(f"  ~ {f}")

            WatchTool._snapshots[key] = new_state
            return ToolResult.ok("\n".join(lines))

        return ToolResult.fail(f"Unknown action: {action}")
