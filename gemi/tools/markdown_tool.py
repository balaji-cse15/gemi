"""MarkdownTool — extract structure from markdown files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class MarkdownTool(Tool):
    name = "markdown"
    description = (
        "Extract structure from Markdown files. "
        "Actions: 'toc' (table of contents from headings), "
        "'links' (extract all links), 'codeblocks' (extract fenced code blocks), "
        "'sections' (split by headings)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'toc', 'links', 'codeblocks', 'sections'.",
                "enum": ["toc", "links", "codeblocks", "sections"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to markdown file.",
            },
            "text": {
                "type": "string",
                "description": "Raw markdown text (alternative to file_path).",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        file_path = kwargs.get("file_path", "")
        text = kwargs.get("text", "")

        if file_path:
            fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
            fp = fp.resolve()
            if not fp.is_file():
                return ToolResult.fail(f"File not found: {fp}")
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception as e:
                return ToolResult.fail(f"Read error: {e}")

        if not text:
            return ToolResult.fail("Provide file_path or text.")

        if action == "toc":
            return self._toc(text)
        elif action == "links":
            return self._links(text)
        elif action == "codeblocks":
            return self._codeblocks(text)
        elif action == "sections":
            return self._sections(text)
        return ToolResult.fail(f"Unknown action: {action}")

    def _toc(self, text: str) -> ToolResult:
        headings = []
        for line in text.splitlines():
            m = re.match(r"^(#{1,6})\s+(.+)", line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                indent = "  " * (level - 1)
                headings.append(f"{indent}- {title}")
        if not headings:
            return ToolResult.ok("No headings found.")
        return ToolResult.ok("\n".join(headings))

    def _links(self, text: str) -> ToolResult:
        links = re.findall(r"\[([^\]]*)\]\(([^)]+)\)", text)
        if not links:
            return ToolResult.ok("No links found.")
        lines = [f"  [{label}]({url})" for label, url in links]
        return ToolResult.ok(f"{len(links)} links:\n" + "\n".join(lines))

    def _codeblocks(self, text: str) -> ToolResult:
        blocks = re.findall(r"```(\w*)\n(.*?)```", text, re.DOTALL)
        if not blocks:
            return ToolResult.ok("No code blocks found.")
        lines = []
        for i, (lang, code) in enumerate(blocks, 1):
            lang_label = lang or "plain"
            preview = code.strip()[:200]
            if len(code.strip()) > 200:
                preview += "..."
            lines.append(f"\n--- Block {i} ({lang_label}) ---\n{preview}")
        return ToolResult.ok(f"{len(blocks)} code blocks:" + "\n".join(lines))

    def _sections(self, text: str) -> ToolResult:
        sections = []
        current_heading = "(top)"
        current_lines: list[str] = []

        for line in text.splitlines():
            m = re.match(r"^(#{1,6})\s+(.+)", line)
            if m:
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    sections.append((current_heading, len(content)))
                current_heading = m.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            content = "\n".join(current_lines).strip()
            sections.append((current_heading, len(content)))

        if not sections:
            return ToolResult.ok("No sections found.")
        lines = [f"  {name}: {chars} chars" for name, chars in sections]
        return ToolResult.ok(f"{len(sections)} sections:\n" + "\n".join(lines))
