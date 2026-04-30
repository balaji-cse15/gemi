"""RegexTool — test, match, extract, replace with regular expressions."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class RegexTool(Tool):
    name = "regex"
    description = (
        "Test, match, extract, or replace using regular expressions. "
        "Actions: 'test' (bool match), 'match' (first match + groups), "
        "'findall' (all matches), 'replace' (substitution)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'test', 'match', 'findall', 'replace'.",
                "enum": ["test", "match", "findall", "replace"],
            },
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern.",
            },
            "text": {
                "type": "string",
                "description": "Input text to match against.",
            },
            "replacement": {
                "type": "string",
                "description": "Replacement string (for 'replace' action).",
            },
            "flags": {
                "type": "string",
                "description": "Regex flags: 'i' (ignorecase), 'm' (multiline), 's' (dotall). Combine: 'ims'.",
                "default": "",
            },
        },
        "required": ["action", "pattern", "text"],
    }

    def _parse_flags(self, flags_str: str) -> int:
        flags = 0
        for c in flags_str.lower():
            if c == "i":
                flags |= re.IGNORECASE
            elif c == "m":
                flags |= re.MULTILINE
            elif c == "s":
                flags |= re.DOTALL
        return flags

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        pattern = kwargs.get("pattern", "")
        text = kwargs.get("text", "")
        replacement = kwargs.get("replacement", "")
        flags_str = kwargs.get("flags", "")

        if not pattern:
            return ToolResult.fail("No pattern provided.")

        try:
            regex = re.compile(pattern, self._parse_flags(flags_str))
        except re.error as e:
            return ToolResult.fail(f"Invalid regex: {e}")

        if action == "test":
            found = bool(regex.search(text))
            return ToolResult.ok(f"Match: {found}")

        elif action == "match":
            m = regex.search(text)
            if not m:
                return ToolResult.ok("No match found.")
            groups = m.groups()
            result = f"Match: {m.group()!r}\nSpan: {m.span()}"
            if groups:
                for i, g in enumerate(groups, 1):
                    result += f"\nGroup {i}: {g!r}"
            named = m.groupdict()
            if named:
                for name, val in named.items():
                    result += f"\nGroup '{name}': {val!r}"
            return ToolResult.ok(result)

        elif action == "findall":
            matches = regex.findall(text)
            if not matches:
                return ToolResult.ok("No matches found.")
            lines = [f"{i+1}: {m!r}" for i, m in enumerate(matches[:200])]
            header = f"{len(matches)} matches"
            if len(matches) > 200:
                header += " (showing first 200)"
            return ToolResult.ok(f"{header}\n" + "\n".join(lines))

        elif action == "replace":
            if replacement is None:
                return ToolResult.fail("replacement required for replace action.")
            result, count = regex.subn(replacement, text)
            return ToolResult.ok(f"{count} replacements\n{result}")

        return ToolResult.fail(f"Unknown action: {action}")
