"""SystemInfoTool — OS, CPU, RAM, disk, Python info."""
from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class SystemInfoTool(Tool):
    name = "system_info"
    description = (
        "Get system information: OS, CPU, RAM, disk space, Python version, "
        "environment details."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "description": "Specific section: 'os', 'python', 'disk', 'env', or 'all' (default).",
                "default": "all",
            },
        },
        "required": [],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        section = kwargs.get("section", "all")
        parts: list[str] = []

        if section in ("all", "os"):
            parts.append("=== OS ===")
            parts.append(f"System:    {platform.system()} {platform.release()}")
            parts.append(f"Version:   {platform.version()}")
            parts.append(f"Machine:   {platform.machine()}")
            parts.append(f"Processor: {platform.processor()}")
            parts.append(f"Hostname:  {platform.node()}")
            parts.append(f"CPU count: {os.cpu_count()}")

        if section in ("all", "python"):
            parts.append("\n=== Python ===")
            parts.append(f"Version:    {sys.version}")
            parts.append(f"Executable: {sys.executable}")
            parts.append(f"Prefix:     {sys.prefix}")
            parts.append(f"Path:       {sys.path[:5]}")

        if section in ("all", "disk"):
            parts.append("\n=== Disk ===")
            for drive in [workspace, Path.home()]:
                try:
                    usage = shutil.disk_usage(drive)
                    total_gb = usage.total / (1024**3)
                    free_gb = usage.free / (1024**3)
                    used_pct = (usage.used / usage.total) * 100
                    parts.append(f"{drive}: {free_gb:.1f}GB free / {total_gb:.1f}GB total ({used_pct:.0f}% used)")
                except Exception:
                    pass

        if section in ("all", "env"):
            parts.append("\n=== Key Env Vars ===")
            for var in ["PATH", "HOME", "USERPROFILE", "CUDA_VISIBLE_DEVICES", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV"]:
                val = os.environ.get(var, "")
                if val:
                    display = val[:150] + "..." if len(val) > 150 else val
                    parts.append(f"{var}: {display}")

        return ToolResult.ok("\n".join(parts))
