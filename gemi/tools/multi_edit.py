"""MultiEditTool — find and replace across multiple files."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

BINARY_EXTENSIONS = {".exe", ".dll", ".so", ".bin", ".zip", ".gz", ".tar", ".png", ".jpg", ".gif", ".pdf", ".whl", ".gguf"}


class MultiEditTool(Tool):
    name = "multi_edit"
    description = (
        "Find and replace a string or regex pattern across multiple files. "
        "Supports glob filtering. Dry-run mode available."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "String or regex to find.",
            },
            "replacement": {
                "type": "string",
                "description": "Replacement string.",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in. Defaults to workspace root.",
                "default": ".",
            },
            "glob": {
                "type": "string",
                "description": "Glob filter for files (e.g. '*.py', '*.ts').",
                "default": "*",
            },
            "is_regex": {
                "type": "boolean",
                "description": "Treat pattern as regex (default false, uses literal string match).",
                "default": False,
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without writing (default false).",
                "default": False,
            },
        },
        "required": ["pattern", "replacement"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        pattern = kwargs.get("pattern", "")
        replacement = kwargs.get("replacement", "")
        search_path = kwargs.get("path", ".")
        file_glob = kwargs.get("glob", "*")
        is_regex = bool(kwargs.get("is_regex", False))
        dry_run = bool(kwargs.get("dry_run", False))

        if not pattern:
            return ToolResult.fail("No pattern provided.")

        base = Path(search_path)
        if not base.is_absolute():
            base = workspace / base
        base = base.resolve()

        if is_regex:
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return ToolResult.fail(f"Invalid regex: {e}")

        changed_files: list[str] = []
        total_replacements = 0

        for fpath in sorted(base.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() in BINARY_EXTENSIONS:
                continue
            if not fnmatch.fnmatch(fpath.name, file_glob):
                continue
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue

            if is_regex:
                new_text, count = regex.subn(replacement, text)
            else:
                count = text.count(pattern)
                new_text = text.replace(pattern, replacement) if count > 0 else text

            if count > 0:
                total_replacements += count
                try:
                    rel = fpath.relative_to(workspace)
                except ValueError:
                    rel = fpath
                changed_files.append(f"  {rel}: {count} replacements")
                if not dry_run:
                    fpath.write_text(new_text, encoding="utf-8")

        if not changed_files:
            return ToolResult.ok("No matches found.")

        prefix = "[DRY RUN] " if dry_run else ""
        header = f"{prefix}{total_replacements} replacements in {len(changed_files)} files:"
        return ToolResult.ok(header + "\n" + "\n".join(changed_files))
