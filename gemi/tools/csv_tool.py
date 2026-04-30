"""CsvTool — read, query, and transform CSV files."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class CsvTool(Tool):
    name = "csv"
    description = (
        "Read, query, and transform CSV files. "
        "Actions: 'read' (show rows), 'headers' (column names), "
        "'stats' (row/column counts), 'query' (filter rows), "
        "'to_json' (convert to JSON)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'read', 'headers', 'stats', 'query', 'to_json'.",
                "enum": ["read", "headers", "stats", "query", "to_json"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to CSV file.",
            },
            "limit": {
                "type": "integer",
                "description": "Max rows to return (default 50).",
                "default": 50,
            },
            "column": {
                "type": "string",
                "description": "Column name for query filter.",
            },
            "value": {
                "type": "string",
                "description": "Value to match in query filter (substring match).",
            },
            "delimiter": {
                "type": "string",
                "description": "Column delimiter (default ',').",
                "default": ",",
            },
        },
        "required": ["action", "file_path"],
    }

    def _read_csv(self, fp: Path, delimiter: str) -> tuple[list[str], list[dict[str, str]]]:
        with open(fp, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            headers = reader.fieldnames or []
            rows = list(reader)
        return headers, rows

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        file_path = kwargs.get("file_path", "")
        limit = int(kwargs.get("limit", 50))
        column = kwargs.get("column", "")
        value = kwargs.get("value", "")
        delimiter = kwargs.get("delimiter", ",")

        if not file_path:
            return ToolResult.fail("No file_path provided.")

        fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
        fp = fp.resolve()

        if not fp.is_file():
            return ToolResult.fail(f"File not found: {fp}")

        try:
            headers, rows = self._read_csv(fp, delimiter)
        except Exception as e:
            return ToolResult.fail(f"CSV parse error: {e}")

        if action == "headers":
            if not headers:
                return ToolResult.ok("No headers found.")
            return ToolResult.ok(f"{len(headers)} columns:\n" + "\n".join(f"  {h}" for h in headers))

        elif action == "stats":
            return ToolResult.ok(f"Rows: {len(rows)}\nColumns: {len(headers)}\nHeaders: {', '.join(headers)}")

        elif action == "read":
            if not rows:
                return ToolResult.ok("No data rows.")
            display = rows[:limit]
            lines = []
            for i, row in enumerate(display):
                lines.append(f"Row {i+1}: {dict(row)}")
            result = "\n".join(lines)
            if len(rows) > limit:
                result += f"\n... ({len(rows) - limit} more rows)"
            return ToolResult.ok(result)

        elif action == "query":
            if not column:
                return ToolResult.fail("column required for query action.")
            if column not in headers:
                return ToolResult.fail(f"Column not found: {column}. Available: {', '.join(headers)}")
            filtered = [r for r in rows if value.lower() in r.get(column, "").lower()]
            if not filtered:
                return ToolResult.ok("No matching rows.")
            display = filtered[:limit]
            lines = [f"Row: {dict(r)}" for r in display]
            result = f"{len(filtered)} matches:\n" + "\n".join(lines)
            if len(filtered) > limit:
                result += f"\n... ({len(filtered) - limit} more)"
            return ToolResult.ok(result)

        elif action == "to_json":
            display = rows[:limit]
            output = json.dumps(display, indent=2)
            if len(rows) > limit:
                output += f"\n// ... {len(rows) - limit} more rows"
            return ToolResult.ok(output)

        return ToolResult.fail(f"Unknown action: {action}")
