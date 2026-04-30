"""Tool base class — mirrors Claude Code's buildTool pattern."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolResult:
    output: str
    error: str = ""
    is_error: bool = False

    @classmethod
    def ok(cls, output: str) -> ToolResult:
        return cls(output=output)

    @classmethod
    def fail(cls, error: str) -> ToolResult:
        return cls(output="", error=error, is_error=True)

    @property
    def content(self) -> str:
        return self.error if self.is_error else self.output


class Tool:
    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    read_only: bool = False
    dangerous: bool = False

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
