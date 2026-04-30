"""XmlTool — parse, format, and query XML."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class XmlTool(Tool):
    name = "xml"
    description = (
        "Parse, format, validate, or query XML data. "
        "Actions: 'format' (pretty-print), 'validate', "
        "'xpath' (query with XPath), 'to_json' (convert to JSON)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'format', 'validate', 'xpath', 'to_json'.",
                "enum": ["format", "validate", "xpath", "to_json"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to XML file.",
            },
            "input": {
                "type": "string",
                "description": "Raw XML string.",
            },
            "query": {
                "type": "string",
                "description": "XPath expression (for xpath action).",
            },
        },
        "required": ["action"],
    }

    def _elem_to_dict(self, elem: ET.Element) -> dict:
        result: dict[str, Any] = {}
        if elem.attrib:
            result["@attributes"] = dict(elem.attrib)
        children = list(elem)
        if children:
            child_dict: dict[str, list] = {}
            for child in children:
                tag = child.tag
                if tag not in child_dict:
                    child_dict[tag] = []
                child_dict[tag].append(self._elem_to_dict(child))
            for tag, items in child_dict.items():
                result[tag] = items[0] if len(items) == 1 else items
        elif elem.text and elem.text.strip():
            result["#text"] = elem.text.strip()
        return result

    def _indent(self, elem: ET.Element, level: int = 0) -> None:
        indent = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                self._indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        file_path = kwargs.get("file_path", "")
        raw = kwargs.get("input", "")
        query = kwargs.get("query", "")

        if file_path:
            fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
            fp = fp.resolve()
            if not fp.is_file():
                return ToolResult.fail(f"File not found: {fp}")
            raw = fp.read_text(encoding="utf-8")

        if not raw:
            return ToolResult.fail("Provide file_path or input.")

        if action == "validate":
            try:
                ET.fromstring(raw)
                return ToolResult.ok("VALID XML")
            except ET.ParseError as e:
                return ToolResult.ok(f"INVALID: {e}")

        elif action == "format":
            try:
                root = ET.fromstring(raw)
                self._indent(root)
                return ToolResult.ok(ET.tostring(root, encoding="unicode"))
            except ET.ParseError as e:
                return ToolResult.fail(f"XML parse error: {e}")

        elif action == "xpath":
            if not query:
                return ToolResult.fail("query required for xpath action.")
            try:
                root = ET.fromstring(raw)
                results = root.findall(query)
                if not results:
                    return ToolResult.ok("No matches.")
                lines = []
                for r in results[:50]:
                    if r.text and r.text.strip():
                        lines.append(f"<{r.tag}> = {r.text.strip()}")
                    else:
                        lines.append(f"<{r.tag}> ({len(list(r))} children)")
                return ToolResult.ok(f"{len(results)} matches:\n" + "\n".join(lines))
            except ET.ParseError as e:
                return ToolResult.fail(f"XML parse error: {e}")

        elif action == "to_json":
            try:
                root = ET.fromstring(raw)
                data = {root.tag: self._elem_to_dict(root)}
                return ToolResult.ok(json.dumps(data, indent=2, ensure_ascii=False))
            except ET.ParseError as e:
                return ToolResult.fail(f"XML parse error: {e}")

        return ToolResult.fail(f"Unknown action: {action}")
