"""Task tool — spawn a sub-agent with its own tool loop.

This is true recursive delegation: the spawned agent gets a fresh
QueryEngine with its own tool budget, isolated from the parent's
conversation. Mirrors Claude Code's Task tool.

Difference from agent_call:
  - agent_call: one-shot text in/out, no tools, no recursion
  - task:       full tool loop, isolated context, returns final text

Recursion is bounded by:
  - max_tool_rounds (per task)
  - max_depth (overall stack — defaults to 2)
  - The Task tool refuses to spawn nested tasks beyond max_depth
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from ..config import get_agent

# Module-level depth counter (per-process)
_DEPTH: list[int] = [0]
MAX_DEPTH = 2


class TaskTool(Tool):
    name = "task"
    read_only = False
    dangerous = False
    description = (
        "Spawn a sub-agent with its OWN tool loop to handle a focused sub-task. "
        "The sub-agent runs a full agent loop (read files, edit, run commands) "
        "but in an isolated conversation. Returns the final text output. "
        "Use for: (1) parallelizable subtasks, (2) keeping the main "
        "conversation focused, (3) using a different agent's specialty. "
        "Recursion limit: 2 levels."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "Sub-agent slug (e.g. 'local-agent-3'). Default: same as caller.",
            },
            "prompt": {
                "type": "string",
                "description": "The sub-task to execute. Must be self-contained — sub-agent has no parent context.",
            },
            "max_rounds": {
                "type": "integer",
                "description": "Maximum tool rounds for the sub-agent (default 10).",
                "default": 10,
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximum response tokens (default 4096).",
                "default": 4096,
            },
            "yolo": {
                "type": "boolean",
                "description": "Whether sub-agent runs in YOLO mode (default false).",
                "default": False,
            },
        },
        "required": ["prompt"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        from ..query_engine import QueryEngine
        from .. import logger as logger_mod

        prompt = kwargs.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail("No prompt provided.")

        # Depth check
        if _DEPTH[0] >= MAX_DEPTH:
            return ToolResult.fail(
                f"Task recursion limit reached ({MAX_DEPTH}). "
                f"Cannot spawn nested tasks deeper than this."
            )

        slug = kwargs.get("agent", "").strip()
        max_rounds = int(kwargs.get("max_rounds", 10))
        max_tokens = int(kwargs.get("max_tokens", 4096))
        yolo = bool(kwargs.get("yolo", False))

        # Pick agent
        agent = get_agent(slug) if slug else None
        if agent is None:
            # Default to the first running agent
            from ..config import get_running_agents
            running = get_running_agents()
            if not running:
                return ToolResult.fail(
                    "No agent specified and no running agents available."
                )
            agent = running[0]

        if not agent.is_proxy_running():
            return ToolResult.fail(
                f"Sub-agent {agent.slug} proxy is offline at {agent.proxy_url}"
            )

        # Build minimal system prompt for sub-task
        sub_system = (
            f"You are {agent.name}, a sub-agent spawned to handle a specific task. "
            f"You have your own tool access. Complete the task and respond with "
            f"a clear summary of what you did and the final result."
        )

        _DEPTH[0] += 1
        logger_mod.log("task.spawn", agent=agent.slug, depth=_DEPTH[0],
                       prompt_preview=prompt[:80])
        try:
            sub_engine = QueryEngine(
                agent=agent,
                workspace=workspace,
                system_prompt=sub_system,
                max_tokens=max_tokens,
                temperature=0.2,
                max_tool_rounds=max_rounds,
                bypass_permissions=yolo,
            )
            result = sub_engine.query(prompt)
            sub_engine._client.close()
        except Exception as e:
            return ToolResult.fail(f"Sub-task failed: {e}")
        finally:
            _DEPTH[0] -= 1

        if result.error:
            return ToolResult.fail(f"Sub-task error: {result.error}")

        meta = (
            f"[task→{agent.slug} {result.elapsed:.1f}s "
            f"{len(result.tool_calls)} tools "
            f"{result.usage.input_tokens}/{result.usage.output_tokens} tok]\n\n"
        )
        return ToolResult.ok(meta + (result.text or "(no output)"))
