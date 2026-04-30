"""Query engine — the core loop: send message -> handle tool calls -> repeat.

Permission model (three tiers, plus rule overrides):
  1. SAFE tools (read_only=True)  → always allowed
  2. WRITE tools (dangerous=False, read_only=False) → allowed, pattern-checked
  3. DANGEROUS tools (dangerous=True) → BLOCKED unless bypass_permissions (YOLO)

Per-call overrides (via buddy.permissions):
  - DENY rules:  block even in YOLO mode
  - ALLOW rules: skip pattern check in non-YOLO mode

Lifecycle integrations:
  - hooks.fire_pre_tool   before each tool call (can BLOCK)
  - hooks.fire_post_tool  after each tool call (can mutate output)
  - cache.get_cache()     LRU cache for SAFE-tier reads
  - cost.get_tracker()    per-turn kWh/USD estimate
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

from .config import AgentDef
from .provider import (
    ProviderError,
    TokenUsage,
    _build_headers,
    _build_payload,
    _collect_sse_to_response,
    extract_text,
    extract_tool_uses,
    extract_usage,
    send_message,
)
from .tools.registry import execute_tool, get_tool, tool_schemas
from . import hooks as hooks_module
from .cache import get_cache
from .cost import get_tracker
from .permissions import Decision, get_permissions
from . import approval as approval_mod
from . import retry as retry_mod
from . import logger as _logger_mod

DANGEROUS_PATTERNS = {
    "write_file": ["__init__", ".env", "credentials", "secret"],
    "edit_file": [".env", "credentials", "secret"],
    "multi_edit": [".env", "credentials"],
    "move_file": [".git", "__pycache__"],
    "copy_file": [".git"],
    "archive": [".."],
    "env": ["SECRET", "TOKEN", "PASSWORD", "KEY"],
    "sqlite": ["DROP", "DELETE FROM", "TRUNCATE"],
    "http_request": ["DELETE"],
    "download": [".."],
}

ROUGH_CHARS_PER_TOKEN = 4


@dataclass
class TurnResult:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    elapsed: float = 0.0
    error: str = ""
    streamed: bool = False
    cost_kwh: float = 0.0
    cost_usd: float = 0.0
    cache_hits: int = 0


@dataclass
class Snapshot:
    """Lightweight conversation checkpoint for rewind."""
    turn: int
    timestamp: float
    msg_count: int
    user_preview: str = ""


ToolCallback = Callable[[str, dict[str, Any], str], None]
TextChunkCallback = Callable[[str], None]
PermissionCallback = Callable[[str, dict[str, Any]], bool]


def _matches_pattern(name: str, args: dict[str, Any]) -> bool:
    patterns = DANGEROUS_PATTERNS.get(name, [])
    if not patterns:
        return False
    haystack = " ".join(str(v) for v in args.values()).lower()
    return any(p.lower() in haystack for p in patterns)


def _estimate_tokens(messages: list[dict[str, Any]], system: str) -> int:
    total_chars = len(system)
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(str(block.get("text", "")))
                    total_chars += len(str(block.get("content", "")))
                    total_chars += len(str(block.get("input", "")))
    return total_chars // ROUGH_CHARS_PER_TOKEN


def _summarize_messages(messages: list[dict[str, Any]]) -> str:
    """Build a compact text summary of a span of messages for compaction."""
    bits = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        if role == "user" and isinstance(content, str):
            bits.append(f"U: {content[:120].replace(chr(10), ' ')}")
        elif role == "assistant" and isinstance(content, list):
            tool_names = [b.get("name", "?") for b in content
                          if isinstance(b, dict) and b.get("type") == "tool_use"]
            text_chunks = [b.get("text", "") for b in content
                           if isinstance(b, dict) and b.get("type") == "text"]
            text = " ".join(t.strip() for t in text_chunks if t).strip()
            if text:
                bits.append(f"A: {text[:120].replace(chr(10), ' ')}")
            if tool_names:
                bits.append(f"   tools: {', '.join(tool_names)}")
        elif role == "user" and isinstance(content, list):
            n_results = sum(1 for b in content
                            if isinstance(b, dict) and b.get("type") == "tool_result")
            if n_results:
                bits.append(f"   {n_results} tool result(s)")
    return "\n".join(bits[:80])


class QueryEngine:
    def __init__(
        self,
        agent: AgentDef,
        workspace: Path,
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.2,
        max_tool_rounds: int = 25,
        on_tool_start: ToolCallback | None = None,
        on_tool_end: ToolCallback | None = None,
        on_text: Callable[[str], None] | None = None,
        on_text_chunk: TextChunkCallback | None = None,
        on_permission: PermissionCallback | None = None,
        bypass_permissions: bool = False,
    ):
        self.agent = agent
        self.workspace = workspace
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_tool_rounds = max_tool_rounds
        self.on_tool_start = on_tool_start
        self.on_tool_end = on_tool_end
        self.on_text = on_text
        self.on_text_chunk = on_text_chunk
        self.on_permission = on_permission
        self.bypass_permissions = bypass_permissions
        self.messages: list[dict[str, Any]] = []
        self.total_usage = TokenUsage()
        self.tools_enabled = True
        self.turn_count = 0
        self.tool_stats: dict[str, dict[str, Any]] = {}
        self.total_elapsed = 0.0
        self.snapshots: list[Snapshot] = []
        self._cache = get_cache()
        self._cost = get_tracker()
        self._client = httpx.Client(
            base_url=agent.proxy_url,
            headers=_build_headers(),
            timeout=300,
        )

    # ------------------------------------------------------------ permissions

    def _check_permission(self, name: str, args: dict[str, Any]) -> tuple[bool, str]:
        # Per-call deny rules trump everything (even YOLO)
        perms = get_permissions()
        decision, reason = perms.evaluate(name, args)
        if decision == Decision.DENY:
            return False, f"DENIED by rule: {reason}"

        if self.bypass_permissions:
            return True, ""

        tool = get_tool(name)
        if not tool:
            return True, ""
        if tool.read_only:
            return True, ""
        if tool.dangerous:
            return False, (
                f"BLOCKED: '{name}' is a dangerous tool. "
                f"Enable YOLO mode (/yolo or --yolo) to use it."
            )

        # Allow rules let this tool through without pattern checking
        if decision == Decision.ALLOW:
            return True, ""

        if _matches_pattern(name, args):
            return False, (
                f"BLOCKED: '{name}' matched a safety pattern. "
                f"Enable YOLO mode (/yolo or --yolo) to bypass."
            )
        return True, ""

    # ------------------------------------------------------------ compaction

    def _compact_messages(self) -> None:
        """Smart compaction: keep head + tail + summary of dropped middle.

        Strategy:
          - Always keep the first 2 messages (initial context)
          - Always keep the last 4 messages (recent context for current task)
          - If still over budget, summarize the dropped middle into a single
            assistant note that's much cheaper to send
        """
        est = _estimate_tokens(self.messages, self.system_prompt)
        context_budget = int(self.agent.context * 0.75)
        if est <= context_budget or len(self.messages) < 8:
            return

        head = self.messages[:2]
        tail = self.messages[-4:]
        middle = self.messages[2:-4]
        if not middle:
            return

        summary = _summarize_messages(middle)
        marker = (
            f"[Buddy auto-compacted {len(middle)} earlier messages "
            f"({_estimate_tokens(middle, '')} tokens). Compressed summary follows.]\n"
            f"{summary}"
        )
        compact_block = [
            {"role": "user", "content": marker},
            {"role": "assistant", "content": [{"type": "text", "text": "Acknowledged — using compressed history."}]},
        ]
        self.messages = head + compact_block + tail

        # If still over budget after one compaction pass, truncate more aggressively
        est = _estimate_tokens(self.messages, self.system_prompt)
        while est > context_budget and len(self.messages) > 6:
            self.messages.pop(2)  # drop from inside (preserve head + tail)
            est = _estimate_tokens(self.messages, self.system_prompt)

    # ------------------------------------------------------------ streaming

    def _stream_round(
        self, tools: list[dict[str, Any]] | None
    ) -> dict[str, Any]:
        payload = _build_payload(
            self.messages, self.system_prompt, tools,
            self.max_tokens, self.temperature,
        )
        try:
            collected_events: list[tuple[str, dict[str, Any]]] = []
            with self._client.stream(
                "POST", "/v1/messages", json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode(errors="replace")
                    raise ProviderError(f"Agent returned {resp.status_code}: {body[:500]}")

                current_event = ""
                for line in resp.iter_lines():
                    line = line.strip()
                    if line.startswith("event: "):
                        current_event = line[7:]
                    elif line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        evt_type = current_event or data.get("type", "unknown")
                        collected_events.append((evt_type, data))

                        if self.on_text_chunk and evt_type == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                chunk = delta.get("text", "")
                                if chunk:
                                    self.on_text_chunk(chunk)

            return _collect_sse_to_response(collected_events)

        except ProviderError as e:
            msg = str(e)
            if "413" in msg or "too large" in msg.lower() or "context" in msg.lower():
                est = _estimate_tokens(self.messages, self.system_prompt)
                raise ProviderError(
                    f"Context overflow (~{est:,} tokens vs {self.agent.context:,} limit). "
                    f"Use /compact to free space or /clear to reset."
                )
            raise
        except httpx.TimeoutException:
            raise ProviderError(
                f"Agent {self.agent.slug} timed out after 300s. "
                f"The model may be overloaded — try again or /agent to switch."
            )
        except httpx.ConnectError:
            raise ProviderError(
                f"Cannot connect to {self.agent.slug} at {self.agent.proxy_url}.\n"
                f"Start it with: agents.ps1 -Start {self.agent.slug} -Proxy"
            )
        except Exception as e:
            raise ProviderError(f"Provider error: {e}")

    # ------------------------------------------------------------ main loop

    def query(self, user_input: str) -> TurnResult:
        # Fire UserPromptSubmit hook (can mutate prompt via hook output but we
        # currently just allow/log — extension point for future)
        hooks_module.fire_prompt(user_input)

        self.messages.append({"role": "user", "content": user_input})
        self.turn_count += 1
        self._snapshot_pre_turn(user_input)
        self._compact_messages()
        t0 = time.time()
        total_tool_calls: list[dict[str, Any]] = []
        total_tool_results: list[dict[str, Any]] = []
        final_text = ""
        total_usage = TokenUsage()
        did_stream = bool(self.on_text_chunk)
        cache_hits = 0

        for _round_idx in range(self.max_tool_rounds + 1):
            try:
                tools = tool_schemas(
                    exclude_dangerous=not self.bypass_permissions,
                    context_budget=self.agent.context,
                ) if self.tools_enabled else None
                if self.on_text_chunk:
                    response = self._stream_round(tools)
                else:
                    response = send_message(
                        agent=self.agent,
                        messages=self.messages,
                        system=self.system_prompt,
                        tools=tools,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )
            except ProviderError as e:
                elapsed = time.time() - t0
                hooks_module.fire_stop(self.turn_count, elapsed)
                return TurnResult(text="", error=str(e), elapsed=elapsed)

            usage = extract_usage(response)
            total_usage.input_tokens += usage.input_tokens
            total_usage.output_tokens += usage.output_tokens

            text = extract_text(response)
            tool_uses = extract_tool_uses(response)

            if text and self.on_text and not self.on_text_chunk:
                self.on_text(text)

            if not tool_uses:
                final_text = text
                self.messages.append({"role": "assistant", "content": response.get("content", [])})
                break

            self.messages.append({"role": "assistant", "content": response.get("content", [])})

            tool_result_blocks = []
            for tu in tool_uses:
                tool_name = tu.get("name", "")
                tool_input = tu.get("input", {})
                tool_id = tu.get("id", "")

                if self.on_tool_start:
                    self.on_tool_start(tool_name, tool_input, tool_id)

                # 1. Check the base permission tier system + custom rules
                allowed, reason = self._check_permission(tool_name, tool_input)

                # 2. Fire PreToolUse hook (can also block)
                if allowed:
                    pre = hooks_module.fire_pre_tool(tool_name, tool_input)
                    if not pre.allow:
                        allowed = False
                        reason = f"BLOCKED by hook: {pre.message}"

                if not allowed:
                    result_content = reason
                    is_error = True
                    tool_elapsed = 0.0
                else:
                    # 3. Interactive approval gate (if configured)
                    if approval_mod.needs_approval(tool_name, self.bypass_permissions):
                        try:
                            ok, deny_reason = approval_mod.prompt_user(tool_name, tool_input)
                        except Exception:
                            ok, deny_reason = True, ""
                        if not ok:
                            result_content = (
                                f"DENIED by user: {deny_reason or 'approval declined'}"
                            )
                            is_error = True
                            tool_elapsed = 0.0
                            allowed = False
                            _logger_mod.log("approval.denied", tool=tool_name,
                                            reason=deny_reason)

                if not allowed:
                    pass  # already set result_content above
                else:
                    # 4. Try cache (SAFE reads only)
                    cached = self._cache.get(tool_name, tool_input)
                    if cached:
                        result_content = cached.output
                        is_error = cached.is_error
                        tool_elapsed = 0.0
                        cache_hits += 1
                    else:
                        # 5. Execute with retry (transient errors only)
                        def _runner():
                            return execute_tool(tool_name, self.workspace, tool_input)

                        def _on_retry(attempt, err, delay):
                            _logger_mod.log_warn(
                                "tool.retry", tool=tool_name,
                                attempt=attempt, delay=delay, err=err,
                            )

                        t_start = time.time()
                        result, n_attempts = retry_mod.execute_with_retry(
                            tool_name, _runner, on_retry=_on_retry,
                        )
                        tool_elapsed = time.time() - t_start
                        result_content = result.content
                        is_error = result.is_error
                        if n_attempts > 1 and not is_error:
                            result_content = (
                                f"[recovered after {n_attempts} attempt(s)]\n" + result_content
                            )

                        # Cache result if applicable
                        self._cache.put(
                            tool_name, tool_input,
                            result_content, is_error, tool_elapsed,
                        )
                        if not is_error:
                            self._cache.invalidate_for_write(tool_name, tool_input)

                    # 6. Fire PostToolUse hook (can mutate output)
                    post = hooks_module.fire_post_tool(
                        tool_name, tool_input, result_content, is_error,
                    )
                    if post.mutated_output is not None:
                        result_content = post.mutated_output

                total_tool_calls.append(tu)
                total_tool_results.append({
                    "tool_use_id": tool_id,
                    "name": tool_name,
                    "args": tool_input,
                    "output": result_content,
                    "is_error": is_error,
                    "elapsed": tool_elapsed,
                    "cached": tool_elapsed == 0.0 and not is_error and cache_hits > 0,
                })

                if tool_name not in self.tool_stats:
                    self.tool_stats[tool_name] = {"calls": 0, "errors": 0, "time": 0.0, "cached": 0}
                self.tool_stats[tool_name]["calls"] += 1
                self.tool_stats[tool_name]["time"] += tool_elapsed
                if is_error:
                    self.tool_stats[tool_name]["errors"] += 1

                if self.on_tool_end:
                    self.on_tool_end(tool_name, tool_input, result_content)

                tool_result_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_content,
                    "is_error": is_error,
                })

            self.messages.append({"role": "user", "content": tool_result_blocks})
        else:
            final_text = text or "(max tool rounds reached)"

        self.total_usage.input_tokens += total_usage.input_tokens
        self.total_usage.output_tokens += total_usage.output_tokens
        turn_elapsed = time.time() - t0
        self.total_elapsed += turn_elapsed

        # Cost tracking
        cost_record = self._cost.record(
            agent_slug=self.agent.slug,
            quant=self.agent.quant,
            elapsed=turn_elapsed,
            input_tokens=total_usage.input_tokens,
            output_tokens=total_usage.output_tokens,
        )

        hooks_module.fire_stop(self.turn_count, turn_elapsed)

        return TurnResult(
            text=final_text,
            tool_calls=total_tool_calls,
            tool_results=total_tool_results,
            usage=total_usage,
            elapsed=turn_elapsed,
            streamed=did_stream,
            cost_kwh=cost_record.kwh,
            cost_usd=cost_record.usd,
            cache_hits=cache_hits,
        )

    # ------------------------------------------------------------ snapshots

    def _snapshot_pre_turn(self, user_input: str) -> None:
        self.snapshots.append(Snapshot(
            turn=self.turn_count,
            timestamp=time.time(),
            msg_count=len(self.messages),
            user_preview=user_input[:120].replace("\n", " "),
        ))

    def rewind_to(self, turn: int) -> bool:
        """Rewind conversation to start of turn N. Drops everything from that turn onward."""
        if turn < 1:
            return False
        target = next((s for s in self.snapshots if s.turn == turn), None)
        if not target:
            return False
        # Snapshot was taken AFTER the user message was added but before assistant response.
        # We want the state BEFORE the snapshot's user message, so trim to (msg_count - 1).
        keep = max(0, target.msg_count - 1)
        self.messages = self.messages[:keep]
        self.turn_count = turn - 1
        self.snapshots = [s for s in self.snapshots if s.turn < turn]
        return True

    # ------------------------------------------------------------ stats / utility

    def get_stats(self) -> dict[str, Any]:
        cache_stats = self._cache.stats
        return {
            "turns": self.turn_count,
            "total_elapsed": self.total_elapsed,
            "input_tokens": self.total_usage.input_tokens,
            "output_tokens": self.total_usage.output_tokens,
            "total_tokens": self.total_usage.total,
            "tool_stats": dict(self.tool_stats),
            "total_tool_calls": sum(s["calls"] for s in self.tool_stats.values()),
            "total_tool_errors": sum(s["errors"] for s in self.tool_stats.values()),
            "total_tool_time": sum(s["time"] for s in self.tool_stats.values()),
            "cache_hits": cache_stats.hits,
            "cache_misses": cache_stats.misses,
            "cache_hit_rate": cache_stats.hit_rate,
            "session_cost_kwh": self._cost.session.total_kwh,
            "session_cost_usd": self._cost.session.total_usd,
        }

    def clear(self) -> None:
        self.messages.clear()
        self.total_usage = TokenUsage()
        self.turn_count = 0
        self.tool_stats.clear()
        self.total_elapsed = 0.0
        self.snapshots.clear()
        self._cache.clear()

    def set_agent(self, agent: AgentDef) -> None:
        old_slug = self.agent.slug
        self.agent = agent
        self._client.close()
        self._client = httpx.Client(
            base_url=agent.proxy_url,
            headers=_build_headers(),
            timeout=300,
        )
        hooks_module.fire_agent_switch(old_slug, agent.slug)

    def undo(self) -> bool:
        if len(self.messages) < 2:
            return False
        while self.messages and self.messages[-1].get("role") != "user":
            self.messages.pop()
        if self.messages:
            self.messages.pop()
        self.turn_count = max(0, self.turn_count - 1)
        if self.snapshots:
            self.snapshots.pop()
        return True

    def export_markdown(self) -> str:
        lines = [f"# Buddy Session\n"]
        for msg in self.messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if role == "user":
                if isinstance(content, str):
                    lines.append(f"## User\n\n{content}\n")
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            lines.append(f"*Tool result ({block.get('tool_use_id', '')[:8]})*\n")
            elif role == "assistant":
                lines.append(f"## Assistant\n")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                lines.append(f"\n{block.get('text', '')}\n")
                            elif block.get("type") == "tool_use":
                                lines.append(f"\n**Tool: {block.get('name', '')}**\n")
                elif isinstance(content, str):
                    lines.append(f"\n{content}\n")
        lines.append(f"\n---\n*Tokens: {self.total_usage.total:,} | Turns: {self.turn_count}*\n")
        return "\n".join(lines)
