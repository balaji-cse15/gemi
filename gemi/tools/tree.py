"""TreeTool — directory tree viewer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class TreeTool(Tool):
    name = "tree"
    description = (
        "Show directory tree structure. Lists files and subdirectories "
        "with indentation. Use to understand project layout."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to show tree for. Defaults to workspace root.",
                "default": ".",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth to recurse (default 3).",
                "default": 3,
            },
            "show_hidden": {
                "type": "boolean",
                "description": "Include hidden files/dirs (default false).",
                "default": False,
            },
        },
        "required": [],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        target = kwargs.get("path", ".")
        max_depth = int(kwargs.get("max_depth", 3))
        show_hidden = bool(kwargs.get("show_hidden", False))

        base = Path(target)
        if not base.is_absolute():
            base = workspace / base
        base = base.resolve()
        if not base.is_dir():
            return ToolResult.fail(f"Not a directory: {base}")

        lines: list[str] = [str(base)]
        file_count = 0
        dir_count = 0
        max_entries = 500

        def _walk(directory: Path, prefix: str, depth: int) -> None:
            nonlocal file_count, dir_count
            if depth > max_depth or len(lines) >= max_entries:
                return
            try:
                entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                lines.append(f"{prefix}[permission denied]")
                return

            filtered = []
            for e in entries:
                if not show_hidden and e.name.startswith("."):
                    continue
                if e.name in ("__pycache__", "node_modules", ".git", ".venv", "venv"):
                    continue
                filtered.append(e)

            for i, entry in enumerate(filtered):
                if len(lines) >= max_entries:
                    lines.append(f"{prefix}... (truncated)")
                    return
                is_last = i == len(filtered) - 1
                connector = "└── " if is_last else "├── "
                if entry.is_dir():
                    dir_count += 1
                    lines.append(f"{prefix}{connector}{entry.name}/")
                    extension = "    " if is_last else "│   "
                    _walk(entry, prefix + extension, depth + 1)
                else:
                    file_count += 1
                    size = ""
                    try:
                        s = entry.stat().st_size
                        if s > 1_048_576:
                            size = f" ({s / 1_048_576:.1f}MB)"
                        elif s > 1024:
                            size = f" ({s / 1024:.0f}KB)"
                    except OSError:
                        pass
                    lines.append(f"{prefix}{connector}{entry.name}{size}")

        _walk(base, "", 0)
        lines.append(f"\n{dir_count} directories, {file_count} files")
        return ToolResult.ok("\n".join(lines))
