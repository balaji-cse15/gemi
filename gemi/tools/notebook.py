"""NotebookTool — read and inspect Jupyter notebooks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class NotebookTool(Tool):
    name = "notebook"
    description = (
        "Read and inspect Jupyter notebook (.ipynb) files. "
        "Shows cells with their type, source, and outputs."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to .ipynb file.",
            },
            "cell_range": {
                "type": "string",
                "description": "Cell range to show (e.g. '0-5', '3', '10-20'). Default: all.",
            },
            "show_outputs": {
                "type": "boolean",
                "description": "Include cell outputs (default true).",
                "default": True,
            },
        },
        "required": ["file_path"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("file_path", "")
        cell_range = kwargs.get("cell_range", "")
        show_outputs = bool(kwargs.get("show_outputs", True))

        if not raw_path:
            return ToolResult.fail("No file_path provided.")

        fp = Path(raw_path) if Path(raw_path).is_absolute() else workspace / raw_path
        fp = fp.resolve()
        if not fp.is_file():
            return ToolResult.fail(f"File not found: {fp}")

        try:
            nb = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult.fail(f"Cannot parse notebook: {e}")

        cells = nb.get("cells", [])
        kernel = nb.get("metadata", {}).get("kernelspec", {}).get("display_name", "?")

        start, end = 0, len(cells)
        if cell_range:
            if "-" in cell_range:
                parts = cell_range.split("-", 1)
                start = int(parts[0])
                end = int(parts[1]) + 1
            else:
                start = int(cell_range)
                end = start + 1

        lines: list[str] = [f"Notebook: {fp.name} | Kernel: {kernel} | Cells: {len(cells)}"]
        lines.append("")

        for i in range(max(0, start), min(end, len(cells))):
            cell = cells[i]
            ctype = cell.get("cell_type", "?")
            source = "".join(cell.get("source", []))
            lines.append(f"--- Cell {i} [{ctype}] ---")
            lines.append(source)

            if show_outputs and ctype == "code":
                outputs = cell.get("outputs", [])
                for out in outputs:
                    otype = out.get("output_type", "")
                    if otype == "stream":
                        text = "".join(out.get("text", []))
                        lines.append(f"[stdout] {text}")
                    elif otype in ("execute_result", "display_data"):
                        data = out.get("data", {})
                        if "text/plain" in data:
                            text = "".join(data["text/plain"])
                            lines.append(f"[result] {text}")
                    elif otype == "error":
                        lines.append(f"[error] {out.get('ename', '')}: {out.get('evalue', '')}")
            lines.append("")

        result = "\n".join(lines)
        if len(result) > 50000:
            result = result[:50000] + "\n... (truncated)"
        return ToolResult.ok(result)
