"""ThinkTool — structured reasoning scratchpad for the agent."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ThinkTool(Tool):
    name = "think"
    description = (
        "Use this tool to think through a problem step-by-step before acting. "
        "Write your reasoning, analysis, or plan. No side effects — pure thought."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": "Your reasoning, analysis, or plan.",
            },
        },
        "required": ["thought"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        thought = kwargs.get("thought", "")
        if not thought:
            return ToolResult.fail("No thought provided.")
        return ToolResult.ok(f"Thought recorded ({len(thought)} chars). Continue with your plan.")
