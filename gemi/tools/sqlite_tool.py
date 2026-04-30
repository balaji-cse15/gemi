"""SqliteTool — query local SQLite databases."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class SqliteTool(Tool):
    name = "sqlite"
    description = (
        "Query a local SQLite database file. "
        "Actions: 'query' (SELECT), 'execute' (INSERT/UPDATE/DELETE/DDL), "
        "'tables' (list tables), 'schema' (show table schema)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'query', 'execute', 'tables', 'schema'.",
                "enum": ["query", "execute", "tables", "schema"],
            },
            "database": {
                "type": "string",
                "description": "Path to SQLite database file.",
            },
            "sql": {
                "type": "string",
                "description": "SQL statement to run (for 'query' and 'execute').",
            },
            "table": {
                "type": "string",
                "description": "Table name (for 'schema' action).",
            },
            "params": {
                "type": "string",
                "description": "JSON array of query parameters for parameterized queries.",
            },
        },
        "required": ["action", "database"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        db_path = kwargs.get("database", "")
        sql = kwargs.get("sql", "")
        table = kwargs.get("table", "")
        params_raw = kwargs.get("params", "[]")

        if not db_path:
            return ToolResult.fail("No database path provided.")

        fp = Path(db_path) if Path(db_path).is_absolute() else workspace / db_path
        fp = fp.resolve()

        if action in ("query", "tables", "schema") and not fp.is_file():
            return ToolResult.fail(f"Database not found: {fp}")

        try:
            params = json.loads(params_raw) if isinstance(params_raw, str) and params_raw else []
        except json.JSONDecodeError:
            params = []

        try:
            conn = sqlite3.connect(str(fp))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if action == "tables":
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()
                if not tables:
                    return ToolResult.ok("No tables found.")
                return ToolResult.ok("Tables:\n" + "\n".join(f"  {t}" for t in tables))

            elif action == "schema":
                if not table:
                    return ToolResult.fail("table parameter required for schema action.")
                cursor.execute(f"SELECT sql FROM sqlite_master WHERE name=?", (table,))
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return ToolResult.fail(f"Table not found: {table}")
                return ToolResult.ok(row[0])

            elif action == "query":
                if not sql:
                    return ToolResult.fail("sql parameter required for query action.")
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                if not rows:
                    conn.close()
                    return ToolResult.ok("No results.")
                columns = [desc[0] for desc in cursor.description]
                results = [dict(zip(columns, row)) for row in rows]
                conn.close()
                output = json.dumps(results[:500], indent=2, default=str)
                header = f"{len(rows)} rows"
                if len(rows) > 500:
                    header += " (showing first 500)"
                return ToolResult.ok(f"{header}\n{output}")

            elif action == "execute":
                if not sql:
                    return ToolResult.fail("sql parameter required for execute action.")
                cursor.execute(sql, params)
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return ToolResult.ok(f"OK. Rows affected: {affected}")

            conn.close()
            return ToolResult.fail(f"Unknown action: {action}")

        except sqlite3.Error as e:
            return ToolResult.fail(f"SQLite error: {e}")
        except Exception as e:
            return ToolResult.fail(f"Error: {e}")
