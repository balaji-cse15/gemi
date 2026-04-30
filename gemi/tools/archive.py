"""ArchiveTool — create and extract zip/tar archives."""
from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ArchiveTool(Tool):
    name = "archive"
    description = (
        "Create or extract archive files (zip, tar, tar.gz, tar.bz2). "
        "Actions: 'create', 'extract', 'list'."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'create', 'extract', or 'list'.",
                "enum": ["create", "extract", "list"],
            },
            "archive_path": {
                "type": "string",
                "description": "Path to the archive file.",
            },
            "source": {
                "type": "string",
                "description": "Source file/directory (for create) or extract destination (for extract).",
            },
            "format": {
                "type": "string",
                "description": "Archive format: zip, tar, tar.gz, tar.bz2. Auto-detected from extension if omitted.",
            },
        },
        "required": ["action", "archive_path"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        archive = kwargs.get("archive_path", "")
        source = kwargs.get("source", "")
        fmt = kwargs.get("format", "")

        if not archive:
            return ToolResult.fail("No archive_path provided.")

        arc_path = Path(archive) if Path(archive).is_absolute() else workspace / archive
        arc_path = arc_path.resolve()

        if not fmt:
            name = arc_path.name.lower()
            if name.endswith(".tar.gz") or name.endswith(".tgz"):
                fmt = "tar.gz"
            elif name.endswith(".tar.bz2"):
                fmt = "tar.bz2"
            elif name.endswith(".tar"):
                fmt = "tar"
            else:
                fmt = "zip"

        try:
            if action == "list":
                return self._list(arc_path, fmt)
            elif action == "extract":
                dst = Path(source) if source else arc_path.parent
                if not dst.is_absolute():
                    dst = workspace / dst
                return self._extract(arc_path, dst.resolve(), fmt)
            elif action == "create":
                if not source:
                    return ToolResult.fail("source required for create.")
                src = Path(source) if Path(source).is_absolute() else workspace / source
                return self._create(arc_path, src.resolve(), fmt)
            else:
                return ToolResult.fail(f"Unknown action: {action}")
        except Exception as e:
            return ToolResult.fail(f"Archive error: {e}")

    def _list(self, arc_path: Path, fmt: str) -> ToolResult:
        if not arc_path.exists():
            return ToolResult.fail(f"Archive not found: {arc_path}")
        entries: list[str] = []
        if fmt == "zip":
            with zipfile.ZipFile(arc_path) as zf:
                entries = zf.namelist()
        else:
            with tarfile.open(arc_path) as tf:
                entries = tf.getnames()
        if not entries:
            return ToolResult.ok("(empty archive)")
        return ToolResult.ok(f"{len(entries)} entries:\n" + "\n".join(entries[:500]))

    def _extract(self, arc_path: Path, dst: Path, fmt: str) -> ToolResult:
        if not arc_path.exists():
            return ToolResult.fail(f"Archive not found: {arc_path}")
        dst.mkdir(parents=True, exist_ok=True)
        if fmt == "zip":
            with zipfile.ZipFile(arc_path) as zf:
                zf.extractall(dst)
                count = len(zf.namelist())
        else:
            with tarfile.open(arc_path) as tf:
                tf.extractall(dst, filter="data")
                count = len(tf.getnames())
        return ToolResult.ok(f"Extracted {count} entries to {dst}")

    def _create(self, arc_path: Path, src: Path, fmt: str) -> ToolResult:
        if not src.exists():
            return ToolResult.fail(f"Source not found: {src}")
        arc_path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "zip":
            with zipfile.ZipFile(arc_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if src.is_file():
                    zf.write(src, src.name)
                else:
                    for f in src.rglob("*"):
                        if f.is_file():
                            zf.write(f, f.relative_to(src.parent))
            return ToolResult.ok(f"Created {arc_path}")
        else:
            mode = "w:gz" if "gz" in fmt else "w:bz2" if "bz2" in fmt else "w"
            with tarfile.open(arc_path, mode) as tf:
                tf.add(src, arcname=src.name)
            return ToolResult.ok(f"Created {arc_path}")
