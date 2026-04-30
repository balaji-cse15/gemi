"""Hooks system — pre/post tool-call interception for security, logging, validation.

Hooks are user-defined callbacks (Python functions OR shell commands) that fire on:
  - PreToolUse:        before any tool executes; can BLOCK the call
  - PostToolUse:       after a tool executes; can mutate the output
  - UserPromptSubmit:  when the user submits a prompt
  - Stop:              when a turn ends
  - SessionStart:      when a session begins
  - AgentSwitch:       when /agent switches the active agent

Configuration lives at ~/.gemi/hooks.json:

  [
    {
      "event": "PreToolUse",
      "matcher": "bash|powershell",     # regex on tool name
      "command": "python C:/scripts/audit.py",   # optional: shell command
      "timeout": 5,
      "block_on_failure": true,
      "description": "Audit dangerous shell commands"
    },
    {
      "event": "PostToolUse",
      "matcher": "write_file",
      "command": "git add -A",
      "timeout": 10
    }
  ]

Hooks are also registrable programmatically via register_hook().
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

HOOKS_FILE = Path.home() / ".gemi" / "hooks.json"

HookCallback = Callable[[dict[str, Any]], "HookResult"]


@dataclass
class HookResult:
    allow: bool = True              # PreToolUse: false blocks the call
    message: str = ""               # Reason / log line
    mutated_output: str | None = None  # PostToolUse: replaces tool output
    elapsed: float = 0.0


@dataclass
class Hook:
    event: str                      # PreToolUse | PostToolUse | UserPromptSubmit | Stop | SessionStart | AgentSwitch
    matcher: str = "*"              # regex on tool name (or "*" for any)
    command: str = ""               # shell command (mutually exclusive with callback)
    callback: HookCallback | None = None
    timeout: int = 10
    block_on_failure: bool = False  # if true and the hook errors, BLOCK the call
    description: str = ""

    def matches(self, name: str) -> bool:
        if self.matcher == "*" or not self.matcher:
            return True
        try:
            return bool(re.search(self.matcher, name))
        except re.error:
            return self.matcher == name


_REGISTERED: list[Hook] = []
_LOG: list[dict[str, Any]] = []
_LOG_MAX = 500


def register_hook(hook: Hook) -> None:
    _REGISTERED.append(hook)


def clear_hooks() -> None:
    _REGISTERED.clear()


def load_hooks_from_file() -> int:
    """Load hooks from ~/.gemi/hooks.json. Returns number loaded."""
    if not HOOKS_FILE.exists():
        return 0
    try:
        data = json.loads(HOOKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return 0
    loaded = 0
    for entry in data if isinstance(data, list) else []:
        try:
            register_hook(Hook(
                event=entry.get("event", ""),
                matcher=entry.get("matcher", "*"),
                command=entry.get("command", ""),
                timeout=int(entry.get("timeout", 10)),
                block_on_failure=bool(entry.get("block_on_failure", False)),
                description=entry.get("description", ""),
            ))
            loaded += 1
        except Exception:
            continue
    return loaded


def list_hooks() -> list[Hook]:
    return list(_REGISTERED)


def list_log(limit: int = 50) -> list[dict[str, Any]]:
    return _LOG[-limit:]


def _record(event: str, name: str, hook: Hook, result: HookResult) -> None:
    _LOG.append({
        "ts": time.time(),
        "event": event,
        "tool": name,
        "matcher": hook.matcher,
        "allow": result.allow,
        "message": result.message[:200],
        "elapsed": result.elapsed,
    })
    if len(_LOG) > _LOG_MAX:
        del _LOG[: len(_LOG) - _LOG_MAX]


def _fire_one(hook: Hook, payload: dict[str, Any]) -> HookResult:
    t0 = time.time()
    try:
        if hook.callback:
            result = hook.callback(payload)
            if not isinstance(result, HookResult):
                result = HookResult(allow=True, message=str(result or ""))
        elif hook.command:
            env_payload = json.dumps(payload, default=str)
            proc = subprocess.run(
                hook.command,
                shell=True,
                input=env_payload,
                capture_output=True,
                text=True,
                timeout=hook.timeout,
            )
            allow = proc.returncode == 0
            msg = (proc.stdout or proc.stderr or "").strip()[:500]
            result = HookResult(allow=allow, message=msg)
        else:
            result = HookResult(allow=True, message="(no command/callback)")
    except subprocess.TimeoutExpired:
        result = HookResult(
            allow=not hook.block_on_failure,
            message=f"Hook timed out after {hook.timeout}s",
        )
    except Exception as e:
        result = HookResult(
            allow=not hook.block_on_failure,
            message=f"Hook error: {e}",
        )
    result.elapsed = time.time() - t0
    return result


def fire(event: str, name: str = "", payload: dict[str, Any] | None = None) -> HookResult:
    """Fire all hooks matching event+name. Returns aggregated result.

    For PreToolUse: any hook returning allow=False blocks.
    For PostToolUse: last mutated_output (if any) wins.
    """
    payload = payload or {}
    payload = {"event": event, "tool": name, **payload}
    final = HookResult(allow=True)

    for hook in _REGISTERED:
        if hook.event != event:
            continue
        if not hook.matches(name):
            continue
        result = _fire_one(hook, payload)
        _record(event, name, hook, result)

        if not result.allow:
            final.allow = False
            final.message = result.message or final.message
            # PreToolUse: short-circuit on first block
            if event == "PreToolUse":
                return final
        if result.mutated_output is not None:
            final.mutated_output = result.mutated_output

    return final


def fire_pre_tool(name: str, args: dict[str, Any]) -> HookResult:
    return fire("PreToolUse", name, {"args": args})


def fire_post_tool(name: str, args: dict[str, Any], output: str, is_error: bool) -> HookResult:
    return fire("PostToolUse", name, {"args": args, "output": output, "is_error": is_error})


def fire_prompt(prompt: str) -> HookResult:
    return fire("UserPromptSubmit", "", {"prompt": prompt})


def fire_stop(turn_count: int, elapsed: float) -> HookResult:
    return fire("Stop", "", {"turn": turn_count, "elapsed": elapsed})


def fire_session_start(agent_slug: str, workspace: str) -> HookResult:
    return fire("SessionStart", "", {"agent": agent_slug, "workspace": workspace})


def fire_agent_switch(from_slug: str, to_slug: str) -> HookResult:
    return fire("AgentSwitch", "", {"from": from_slug, "to": to_slug})


def initialize() -> int:
    """Load hooks from disk on startup. Idempotent."""
    clear_hooks()
    return load_hooks_from_file()
