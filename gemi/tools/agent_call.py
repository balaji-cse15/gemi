"""AgentCallTool — delegate a sub-task to another agent in the fleet.

Lets the active agent (typically the lead orchestrator) hand off work to a
specialist agent. The delegated agent runs as a one-shot text-only call —
no nested tool loop, no recursion. The result is returned as text the
delegating agent can use in its own reasoning.

Usage by the model:
    {"name": "agent_call", "input": {
        "agent": "local-agent-9",
        "prompt": "Review this design for race conditions: ...",
        "max_tokens": 2048
    }}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult
from ..orchestration import delegate, vote, find_specialist
from ..config import FLEET, get_agent


class AgentCallTool(Tool):
    name = "agent_call"
    read_only = False
    dangerous = False
    description = (
        "Delegate a sub-task to another agent in the local fleet. Returns the "
        "other agent's text response. Use to leverage specialists: a precision "
        "coder for hard logic, a fast agent for triage, a parallel agent for "
        "wide search. Pass either 'agent' (slug) or 'role_keyword' (e.g. "
        "'precision', 'fast', 'reviewer'). Do NOT recurse — the delegated "
        "agent has no tools."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "Agent slug (e.g. 'local-agent-5'). Mutually exclusive with role_keyword.",
            },
            "role_keyword": {
                "type": "string",
                "description": "Heuristic role match: 'precision', 'fast', 'reviewer', 'classifier', 'orchestrator'.",
            },
            "prompt": {
                "type": "string",
                "description": "The task to delegate. Be specific — the other agent has no context.",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximum response tokens (default 2048).",
                "default": 2048,
            },
            "temperature": {
                "type": "number",
                "description": "Sampling temperature (default 0.2).",
                "default": 0.2,
            },
        },
        "required": ["prompt"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        prompt = kwargs.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail("No prompt provided.")

        slug = kwargs.get("agent", "").strip()
        role_keyword = kwargs.get("role_keyword", "").strip()
        max_tokens = int(kwargs.get("max_tokens", 2048))
        temperature = float(kwargs.get("temperature", 0.2))

        if not slug and role_keyword:
            specialist = find_specialist(role_keyword)
            if not specialist:
                running = ", ".join(a.slug for a in FLEET if a.is_proxy_running()) or "(none)"
                return ToolResult.fail(
                    f"No agent matches role_keyword='{role_keyword}'. "
                    f"Running agents: {running}"
                )
            slug = specialist.slug

        if not slug:
            return ToolResult.fail("Provide either 'agent' or 'role_keyword'.")

        agent = get_agent(slug)
        if not agent:
            return ToolResult.fail(f"Unknown agent: {slug}")

        result = delegate(
            target_slug=slug,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=180,
        )

        if not result.succeeded:
            return ToolResult.fail(
                f"Delegation to {result.agent} failed: {result.error}"
            )

        meta = (
            f"[delegated to {agent.name} ({agent.slug}, {agent.quant}) "
            f"in {result.elapsed:.1f}s, "
            f"{result.usage.input_tokens}/{result.usage.output_tokens} tokens]\n\n"
        )
        return ToolResult.ok(meta + result.text)


class AgentVoteTool(Tool):
    name = "agent_vote"
    read_only = False
    dangerous = False
    description = (
        "Run the SAME prompt against multiple running agents in parallel and "
        "return all responses for comparison. Use when you want a second "
        "opinion or ensemble check on a hard question. Only running agents "
        "respond. Each agent is independent — no shared context."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Prompt to send to each agent.",
            },
            "agents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of agent slugs. Default: all running agents.",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Per-agent max response tokens (default 1024).",
                "default": 1024,
            },
        },
        "required": ["prompt"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        prompt = kwargs.get("prompt", "").strip()
        if not prompt:
            return ToolResult.fail("No prompt provided.")
        agents = kwargs.get("agents", [])
        if not isinstance(agents, list):
            agents = []
        max_tokens = int(kwargs.get("max_tokens", 1024))

        results = vote(
            prompt=prompt,
            targets=agents or None,
            max_tokens=max_tokens,
            temperature=0.3,
            timeout=120,
        )
        if not results:
            return ToolResult.fail("No running agents available for voting.")

        lines = [f"# Vote: {len(results)} agents responded\n"]
        for r in results:
            lines.append(f"## {r.agent} ({r.quant})  {r.elapsed:.1f}s")
            if r.error:
                lines.append(f"ERROR: {r.error}")
            else:
                lines.append(r.text.strip())
            lines.append("")
        return ToolResult.ok("\n".join(lines))
