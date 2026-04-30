"""LLM provider — talks to local agent proxies via Anthropic Messages API.

The free-claude-code proxy ALWAYS returns Anthropic SSE streams, even for
non-streaming requests. This module handles both cases:
  - send_message(): collects the SSE stream into a complete response dict
  - stream_message(): yields SSE events for real-time rendering
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Generator

import httpx

from .config import AgentDef


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class StreamEvent:
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)


class ProviderError(RuntimeError):
    pass


def _build_headers() -> dict[str, str]:
    return {
        "x-api-key": "local",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def _build_payload(
    messages: list[dict[str, Any]],
    system: str = "",
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "claude-3-5-sonnet-latest",
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if system:
        payload["system"] = system
    if tools:
        payload["tools"] = tools
    return payload


def _parse_sse_lines(raw_lines: list[str]) -> Generator[tuple[str, dict[str, Any]], None, None]:
    """Parse Anthropic SSE format: event: <type>\\ndata: <json>"""
    current_event = ""
    for line in raw_lines:
        line = line.strip()
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            data_str = line[6:]
            if data_str == "[DONE]":
                return
            try:
                data = json.loads(data_str)
                yield current_event or data.get("type", "unknown"), data
            except json.JSONDecodeError:
                continue


def _collect_sse_to_response(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Assemble SSE events into a complete Anthropic Messages API response."""
    response: dict[str, Any] = {
        "id": "",
        "type": "message",
        "role": "assistant",
        "content": [],
        "model": "",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }

    content_blocks: dict[int, dict[str, Any]] = {}
    current_block_index = -1

    for event_type, data in events:
        if event_type == "message_start":
            msg = data.get("message", {})
            response["id"] = msg.get("id", response["id"])
            response["model"] = msg.get("model", response["model"])
            usage = msg.get("usage", {})
            response["usage"]["input_tokens"] = usage.get("input_tokens", 0)

        elif event_type == "content_block_start":
            idx = data.get("index", 0)
            block = data.get("content_block", {})
            content_blocks[idx] = block.copy()
            if block.get("type") == "tool_use":
                content_blocks[idx].setdefault("input", {})
                content_blocks[idx]["_input_json"] = ""
            current_block_index = idx

        elif event_type == "content_block_delta":
            idx = data.get("index", current_block_index)
            delta = data.get("delta", {})
            block = content_blocks.get(idx, {})

            if delta.get("type") == "text_delta":
                block["text"] = block.get("text", "") + delta.get("text", "")
            elif delta.get("type") == "input_json_delta":
                block["_input_json"] = block.get("_input_json", "") + delta.get("partial_json", "")
            elif delta.get("type") == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + delta.get("thinking", "")

        elif event_type == "content_block_stop":
            idx = data.get("index", current_block_index)
            block = content_blocks.get(idx, {})
            if "_input_json" in block:
                raw = block.pop("_input_json")
                if raw:
                    try:
                        block["input"] = json.loads(raw)
                    except json.JSONDecodeError:
                        block["input"] = {}

        elif event_type == "message_delta":
            delta = data.get("delta", {})
            response["stop_reason"] = delta.get("stop_reason", response["stop_reason"])
            usage = data.get("usage", {})
            if usage.get("output_tokens"):
                response["usage"]["output_tokens"] = usage["output_tokens"]

    response["content"] = [content_blocks[i] for i in sorted(content_blocks)]
    return response


def send_message(
    agent: AgentDef,
    messages: list[dict[str, Any]],
    system: str = "",
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    timeout: int = 300,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Send a message and collect the SSE stream into a complete response."""
    import time as _time

    url = f"{agent.proxy_url}/v1/messages"
    payload = _build_payload(messages, system, tools, max_tokens, temperature)
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            collected_events: list[tuple[str, dict[str, Any]]] = []
            with httpx.stream(
                "POST", url, json=payload, headers=_build_headers(), timeout=timeout
            ) as resp:
                if resp.status_code == 529 or resp.status_code == 503:
                    if attempt < max_retries:
                        _time.sleep(2 ** attempt)
                        continue
                if resp.status_code != 200:
                    body = resp.read().decode(errors="replace")
                    raise ProviderError(f"Agent returned {resp.status_code}: {body[:500]}")
                raw_lines: list[str] = []
                for line in resp.iter_lines():
                    raw_lines.append(line)
                collected_events = list(_parse_sse_lines(raw_lines))

            return _collect_sse_to_response(collected_events)

        except ProviderError:
            raise
        except httpx.TimeoutException:
            last_error = httpx.TimeoutException(f"Timed out after {timeout}s")
            if attempt < max_retries:
                _time.sleep(2 ** attempt)
                continue
        except httpx.ConnectError:
            raise ProviderError(
                f"Cannot connect to {agent.slug} at {agent.proxy_url}.\n"
                f"Start it with: agents.ps1 -Start {agent.slug} -Proxy"
            )
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                _time.sleep(2 ** attempt)
                continue

    raise ProviderError(f"Failed after {max_retries + 1} attempts: {last_error}")


def stream_message(
    agent: AgentDef,
    messages: list[dict[str, Any]],
    system: str = "",
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.2,
    timeout: int = 300,
) -> Generator[StreamEvent, None, None]:
    """Stream SSE events from the local agent proxy for real-time rendering."""
    url = f"{agent.proxy_url}/v1/messages"
    payload = _build_payload(messages, system, tools, max_tokens, temperature)

    try:
        with httpx.stream(
            "POST", url, json=payload, headers=_build_headers(), timeout=timeout
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
                        return
                    try:
                        data = json.loads(data_str)
                        yield StreamEvent(
                            event_type=current_event or data.get("type", "unknown"),
                            data=data,
                        )
                    except json.JSONDecodeError:
                        continue

    except ProviderError:
        raise
    except httpx.ConnectError:
        raise ProviderError(
            f"Cannot connect to agent at {agent.proxy_url}.\n"
            f"Start with: agents.ps1 -Start {agent.slug} -Proxy"
        )
    except httpx.TimeoutException:
        raise ProviderError(f"Stream timed out after {timeout}s")


def extract_text(response: dict[str, Any]) -> str:
    content = response.get("content", [])
    parts = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def extract_tool_uses(response: dict[str, Any]) -> list[dict[str, Any]]:
    content = response.get("content", [])
    tool_uses = [block for block in content if block.get("type") == "tool_use"]
    if tool_uses:
        return tool_uses
    # Fallback: parse broken Qwen 3.6 XML tool calls from text blocks
    for block in content:
        if block.get("type") == "text":
            text = block.get("text", "")
            parsed = _parse_qwen36_broken_tool_calls(text)
            if parsed:
                for tc in parsed:
                    content.append(tc)
                tool_uses.extend(parsed)
    return tool_uses


def _parse_qwen36_broken_tool_calls(text: str) -> list[dict[str, Any]]:
    """Parse broken Qwen 3.6 XML format: <tool_call><function=name><parameter=key>value</tool_call>"""
    import re
    import uuid

    results: list[dict[str, Any]] = []

    # Pattern 1: JSON inside <tool_call> tags (fixed template format)
    json_pattern = re.findall(
        r'<tool_call>\s*(\{.+?\})\s*</tool_call>', text, re.DOTALL
    )
    for match in json_pattern:
        try:
            data = json.loads(match)
            name = data.get("name", "")
            args = data.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            if name:
                results.append({
                    "type": "tool_use",
                    "id": f"toolu_{uuid.uuid4().hex[:24]}",
                    "name": name,
                    "input": args,
                })
        except json.JSONDecodeError:
            continue

    if results:
        return results

    # Pattern 2: Broken XML format <function=name><parameter=key>value
    xml_pattern = re.findall(
        r'<tool_call>\s*<function=(\w+)>(.*?)</tool_call>',
        text, re.DOTALL,
    )
    for func_name, param_block in xml_pattern:
        params: dict[str, Any] = {}
        for m in re.finditer(r'<parameter=(\w+)>\s*(.*?)(?=<parameter=|\Z)', param_block, re.DOTALL):
            key = m.group(1)
            val = m.group(2).strip()
            params[key] = val
        if func_name:
            results.append({
                "type": "tool_use",
                "id": f"toolu_{uuid.uuid4().hex[:24]}",
                "name": func_name,
                "input": params,
            })

    return results


def extract_usage(response: dict[str, Any]) -> TokenUsage:
    usage = response.get("usage", {})
    return TokenUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )


def ping_agent(agent: AgentDef, timeout: int = 5) -> bool:
    try:
        with httpx.stream(
            "POST",
            f"{agent.proxy_url}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-latest",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "ping"}],
                "stream": True,
            },
            headers=_build_headers(),
            timeout=timeout,
        ) as resp:
            return resp.status_code == 200
    except Exception:
        return False
