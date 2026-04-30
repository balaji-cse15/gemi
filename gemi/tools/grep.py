"""GrepTool — content search with regex support."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

BINARY_EXTENSIONS = {".exe", ".dll", ".so", ".bin", ".zip", ".gz", ".tar", ".png", ".jpg", ".gif", ".pdf", ".whl", ".gguf"}


class GrepTool(Tool):
    name = "grep"
    description = (
        "Search file contents using regex patterns. "
        "Returns matching lines with file paths and line numbers. "
        "Supports file type filtering via glob parameter."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search in. Defaults to workspace root.",
                "default": ".",
            },
            "glob": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g. '*.py', '*.ts').",
                "default": "*",
            },
            "max_matches": {
                "type": "integer",
                "description": "Maximum number of matching lines to return.",
                "default": 100,
            },
            "case_insensitive": {
                "type": "boolean",
                "description": "Case insensitive search.",
                "default": False,
            },
        },
        "required": ["pattern"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        pattern = kwargs.get("pattern", "")
        search_path = kwargs.get("path", ".")
        file_glob = kwargs.get("glob", "*")
        max_matches = int(kwargs.get("max_matches", 100))
        case_insensitive = bool(kwargs.get("case_insensitive", False))
        if not pattern:
            return ToolResult.fail("No pattern provided.")
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult.fail(f"Invalid regex: {e}")
        base = Path(search_path)
        if not base.is_absolute():
            base = workspace / base
        base = base.resolve()
        matches: list[str] = []
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = sorted(base.rglob("*"))
        else:
            return ToolResult.fail(f"Path not found: {base}")
        for fpath in files:
            if len(matches) >= max_matches:
                break
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() in BINARY_EXTENSIONS:
                continue
            if not fnmatch.fnmatch(fpath.name, file_glob):
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    try:
                        rel = fpath.relative_to(workspace)
                    except ValueError:
                        rel = fpath
                    matches.append(f"{rel}:{lineno}: {line[:300]}")
                    if len(matches) >= max_matches:
                        break
        if not matches:
            return ToolResult.ok("No matches found.")
        return ToolResult.ok("\n".join(matches))
