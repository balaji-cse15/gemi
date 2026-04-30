"""TemplateTool — render string templates with variable substitution."""
from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class TemplateTool(Tool):
    name = "template"
    description = (
        "Render a string template with variable substitution. "
        "Uses Python format syntax: {variable_name}. "
        "Can read template from file."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "template": {
                "type": "string",
                "description": "Template string with {placeholders}.",
            },
            "template_file": {
                "type": "string",
                "description": "Path to template file (alternative to 'template').",
            },
            "variables": {
                "type": "string",
                "description": "JSON object of variable values, e.g. '{\"name\": \"World\"}'.",
            },
        },
        "required": ["variables"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        template_str = kwargs.get("template", "")
        template_file = kwargs.get("template_file", "")
        variables_raw = kwargs.get("variables", "{}")

        if template_file:
            fp = Path(template_file) if Path(template_file).is_absolute() else workspace / template_file
            fp = fp.resolve()
            if not fp.is_file():
                return ToolResult.fail(f"Template file not found: {fp}")
            try:
                template_str = fp.read_text(encoding="utf-8")
            except Exception as e:
                return ToolResult.fail(f"Read error: {e}")

        if not template_str:
            return ToolResult.fail("Provide template or template_file.")

        try:
            if isinstance(variables_raw, str):
                variables = json.loads(variables_raw)
            else:
                variables = variables_raw
        except json.JSONDecodeError as e:
            return ToolResult.fail(f"Invalid JSON in variables: {e}")

        if not isinstance(variables, dict):
            return ToolResult.fail("variables must be a JSON object.")

        try:
            formatter = string.Formatter()
            result = formatter.format(template_str, **{k: str(v) for k, v in variables.items()})
            return ToolResult.ok(result)
        except KeyError as e:
            return ToolResult.fail(f"Missing variable: {e}")
        except Exception as e:
            return ToolResult.fail(f"Template error: {e}")
