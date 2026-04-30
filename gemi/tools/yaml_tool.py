"""YamlTool — parse, validate, format, and convert YAML."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

try:
    import yaml
    HAS_YAML = True
except ImportError:
    yaml = None
    HAS_YAML = False


class YamlTool(Tool):
    name = "yaml"
    description = (
        "Parse, validate, format, or convert YAML data. "
        "Actions: 'format' (pretty-print), 'validate', 'to_json' (YAML→JSON), 'from_json' (JSON→YAML)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'format', 'validate', 'to_json', 'from_json'.",
                "enum": ["format", "validate", "to_json", "from_json"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to YAML/JSON file.",
            },
            "input": {
                "type": "string",
                "description": "Raw YAML or JSON string.",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        if not HAS_YAML:
            return ToolResult.fail("PyYAML not installed. Run: pip install pyyaml")

        action = kwargs.get("action", "")
        file_path = kwargs.get("file_path", "")
        raw = kwargs.get("input", "")

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
                yaml.safe_load(raw)
                return ToolResult.ok("VALID YAML")
            except yaml.YAMLError as e:
                return ToolResult.ok(f"INVALID: {e}")

        elif action == "format":
            try:
                data = yaml.safe_load(raw)
                return ToolResult.ok(yaml.dump(data, default_flow_style=False, sort_keys=False))
            except yaml.YAMLError as e:
                return ToolResult.fail(f"YAML parse error: {e}")

        elif action == "to_json":
            try:
                data = yaml.safe_load(raw)
                return ToolResult.ok(json.dumps(data, indent=2, ensure_ascii=False, default=str))
            except yaml.YAMLError as e:
                return ToolResult.fail(f"YAML parse error: {e}")

        elif action == "from_json":
            try:
                data = json.loads(raw)
                return ToolResult.ok(yaml.dump(data, default_flow_style=False, sort_keys=False))
            except json.JSONDecodeError as e:
                return ToolResult.fail(f"JSON parse error: {e}")

        return ToolResult.fail(f"Unknown action: {action}")
