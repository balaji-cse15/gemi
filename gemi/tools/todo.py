"""TodoWrite tool — structured task list for the current session.

Direct port of Claude Code's TodoWriteTool. The agent calls this tool to
create / update / complete a checklist; the renderer prints the list inline
so the user sees progress without scrolling. State persists for the lifetime
of a session (held by the QueryEngine, not on disk).

Schema (matches Claude Code exactly):

    {
      "todos": [
        {"content": "Run tests",
         "status": "pending|in_progress|completed",
         "activeForm": "Running tests"}
      ]
    }

Rules enforced in the prompt:
  - Exactly ONE in_progress at any time
  - Mark completed IMMEDIATELY after finishing (don't batch)
  - Don't mark completed if tests fail / impl partial / errors
  - Each item has both `content` (imperative) and `activeForm` (continuous)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from .base import Tool, ToolResult


_DESCRIPTION = """Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user. It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool

Use this tool proactively in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps
2. Non-trivial tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list
4. User provides multiple tasks (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos
6. When you start working on a task - Mark it as in_progress BEFORE beginning. Only ONE task in_progress at a time
7. After completing a task - Mark it as completed and add follow-up tasks discovered during implementation

## When NOT to Use

Skip when:
1. There is only a single, straightforward task
2. The task is trivial and tracking provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

## Task States and Management

1. **States**: pending / in_progress / completed
2. **Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Exactly ONE task must be in_progress at any time (not less, not more)
   - Complete current tasks before starting new ones
   - Remove tasks that are no longer relevant from the list entirely
3. **Completion Requirements**:
   - ONLY mark completed when FULLY accomplished
   - If errors/blockers/can't finish: keep as in_progress
   - When blocked: create a new task describing what needs to be resolved
   - Never mark completed if: tests failing, implementation partial, unresolved errors, missing files/deps
4. **Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Always provide both forms:
     - content (imperative): "Fix authentication bug"
     - activeForm (present continuous): "Fixing authentication bug"

When in doubt, use this tool.
"""


class TodoWriteTool(Tool):
    """In-session task tracker. Stateful — call updates an in-memory list."""

    name: ClassVar[str] = "todo_write"
    description: ClassVar[str] = (
        "Update the todo list for the current session. Use proactively to "
        "track multi-step work. Each item: content (imperative), activeForm "
        "(present continuous), status (pending/in_progress/completed). "
        "Exactly ONE task should be in_progress at a time."
    )
    read_only: ClassVar[bool] = False
    dangerous: ClassVar[bool] = False
    detailed_description: ClassVar[str] = _DESCRIPTION

    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "The full updated todo list (replaces any prior list).",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Imperative form: 'Fix bug', 'Run tests'.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                        "activeForm": {
                            "type": "string",
                            "minLength": 1,
                            "description": "Present continuous: 'Fixing bug', 'Running tests'.",
                        },
                    },
                    "required": ["content", "status", "activeForm"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["todos"],
        "additionalProperties": False,
    }

    # Per-session list, set by the engine when the tool is registered.
    # Key = session_id (or "default" if no session). Stored on the tool
    # instance so the registry can share state without passing it through args.
    _state: ClassVar[dict[str, list[dict[str, Any]]]] = {}

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        todos = kwargs.get("todos", [])
        if not isinstance(todos, list):
            return ToolResult.fail("todos must be a list")

        # Validate each item
        valid: list[dict[str, Any]] = []
        for i, item in enumerate(todos):
            if not isinstance(item, dict):
                return ToolResult.fail(f"todo[{i}] must be an object")
            content = item.get("content", "").strip()
            status = item.get("status", "pending")
            active = item.get("activeForm", item.get("active_form", content)).strip()
            if not content:
                return ToolResult.fail(f"todo[{i}].content is required")
            if status not in ("pending", "in_progress", "completed"):
                return ToolResult.fail(
                    f"todo[{i}].status must be one of: pending, in_progress, completed"
                )
            if not active:
                active = content
            valid.append({"content": content, "status": status, "activeForm": active})

        # Enforce: at most one in_progress
        in_prog = [i for i, t in enumerate(valid) if t["status"] == "in_progress"]
        warning = ""
        if len(in_prog) > 1:
            warning = (
                f"\nNOTE: {len(in_prog)} tasks marked in_progress; only ONE should be at a time. "
                "Reduce to a single in_progress before starting new work."
            )

        # If everything's done, clear the list (matches Claude Code behavior)
        all_done = valid and all(t["status"] == "completed" for t in valid)
        next_state = [] if all_done else valid
        TodoWriteTool._state["default"] = next_state

        # The renderer reads from _state['default']; the textual output is
        # short and stable so it caches cleanly.
        body = (
            "Todos have been modified successfully. Ensure that you continue "
            "to use the todo list to track your progress. Please proceed with "
            "the current tasks if applicable."
        )
        return ToolResult.ok(body + warning)

    @classmethod
    def current_todos(cls) -> list[dict[str, Any]]:
        return list(cls._state.get("default", []))

    @classmethod
    def clear(cls) -> None:
        cls._state["default"] = []
