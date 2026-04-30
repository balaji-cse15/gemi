"""SnippetTool — save, list, and retrieve reusable code snippets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

SNIPPETS_FILE = ".gemi_snippets.json"


class SnippetTool(Tool):
    name = "snippet"
    description = (
        "Save, list, search, and retrieve reusable code snippets. "
        "Actions: 'save', 'get', 'list', 'search', 'delete'."
    )
    read_only = False
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'save', 'get', 'list', 'search', 'delete'.",
                "enum": ["save", "get", "list", "search", "delete"],
            },
            "name": {
                "type": "string",
                "description": "Snippet name (for save/get/delete).",
            },
            "code": {
                "type": "string",
                "description": "Code content (for save).",
            },
            "language": {
                "type": "string",
                "description": "Language tag (for save).",
            },
            "tags": {
                "type": "string",
                "description": "Comma-separated tags (for save/search).",
            },
            "query": {
                "type": "string",
                "description": "Search query (for search).",
            },
        },
        "required": ["action"],
    }

    def _load(self, workspace: Path) -> dict:
        fp = workspace / SNIPPETS_FILE
        if fp.is_file():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self, workspace: Path, data: dict) -> None:
        fp = workspace / SNIPPETS_FILE
        fp.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        name = kwargs.get("name", "")
        snippets = self._load(workspace)

        if action == "save":
            code = kwargs.get("code", "")
            if not name or not code:
                return ToolResult.fail("name and code required.")
            lang = kwargs.get("language", "")
            tags = [t.strip() for t in kwargs.get("tags", "").split(",") if t.strip()]
            snippets[name] = {"code": code, "language": lang, "tags": tags}
            self._save(workspace, snippets)
            return ToolResult.ok(f"Snippet '{name}' saved ({len(code)} chars).")

        elif action == "get":
            if not name:
                return ToolResult.fail("name required.")
            s = snippets.get(name)
            if not s:
                return ToolResult.fail(f"Snippet '{name}' not found.")
            lang = s.get("language", "")
            tags = ", ".join(s.get("tags", []))
            header = f"[{name}]"
            if lang:
                header += f" ({lang})"
            if tags:
                header += f" tags: {tags}"
            return ToolResult.ok(f"{header}\n{s['code']}")

        elif action == "list":
            if not snippets:
                return ToolResult.ok("No snippets saved.")
            lines = []
            for n, s in sorted(snippets.items()):
                lang = s.get("language", "")
                tags = ", ".join(s.get("tags", []))
                size = len(s.get("code", ""))
                lines.append(f"  {n:30s} {lang:10s} {size:>6d}b  {tags}")
            return ToolResult.ok(f"Snippets ({len(snippets)}):\n" + "\n".join(lines))

        elif action == "search":
            query = kwargs.get("query", "").lower()
            tags_filter = [t.strip().lower() for t in kwargs.get("tags", "").split(",") if t.strip()]
            if not query and not tags_filter:
                return ToolResult.fail("query or tags required.")
            matches = []
            for n, s in snippets.items():
                stags = [t.lower() for t in s.get("tags", [])]
                if query and query in n.lower():
                    matches.append(n)
                elif query and query in s.get("code", "").lower():
                    matches.append(n)
                elif tags_filter and any(t in stags for t in tags_filter):
                    matches.append(n)
            if not matches:
                return ToolResult.ok("No matching snippets.")
            return ToolResult.ok(f"Found {len(matches)}: " + ", ".join(matches))

        elif action == "delete":
            if not name:
                return ToolResult.fail("name required.")
            if name not in snippets:
                return ToolResult.fail(f"Snippet '{name}' not found.")
            del snippets[name]
            self._save(workspace, snippets)
            return ToolResult.ok(f"Snippet '{name}' deleted.")

        return ToolResult.fail(f"Unknown action: {action}")
