"""Tool retry policy — automatic retry with exponential backoff for transient errors.

Wraps tool execution to retry on:
  - Network/timeout errors
  - "rate limit" / "429" responses
  - "connection refused" / "temporarily unavailable"

Permanent errors are NOT retried (file not found, syntax error, denied, etc.).

Configuration via ~/.gemi/config.json:

  {
    "retry": {
      "enabled": true,
      "max_attempts": 3,
      "base_delay_ms": 500,
      "max_delay_ms": 8000,
      "tools": ["bash", "web_fetch", "http_request", "web_search", "agent_call"]
    }
  }
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

CONFIG_FILE = Path.home() / ".gemi" / "config.json"


# Patterns that indicate transient failure (worth retrying)
TRANSIENT_PATTERNS = [
    r"timed out",
    r"timeout",
    r"connection (refused|reset|aborted|closed)",
    r"temporarily unavailable",
    r"rate limit",
    r"\b429\b",
    r"\b503\b",
    r"\b504\b",
    r"\b502\b",
    r"\b529\b",
    r"unable to connect",
    r"network is unreachable",
    r"could not resolve host",
    r"name or service not known",
    r"name resolution failed",
]
TRANSIENT_RE = re.compile("|".join(TRANSIENT_PATTERNS), re.IGNORECASE)


@dataclass
class RetryPolicy:
    enabled: bool = True
    max_attempts: int = 3
    base_delay_ms: int = 500
    max_delay_ms: int = 8000
    # Default tool allowlist for retry — only network-y / I/O-y tools
    tools: list[str] = field(default_factory=lambda: [
        "bash", "powershell", "git", "pip", "npm", "docker",
        "web_fetch", "web_search", "http_request", "download",
        "port_scan", "dns_lookup", "whois", "subdomain",
        "agent_call", "agent_vote", "task",
    ])

    def should_retry(self, tool_name: str, error_text: str) -> bool:
        if not self.enabled:
            return False
        if tool_name not in self.tools:
            return False
        return bool(TRANSIENT_RE.search(error_text or ""))


def _load_policy() -> RetryPolicy:
    if not CONFIG_FILE.exists():
        return RetryPolicy()
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return RetryPolicy()
    body = cfg.get("retry") or {}
    p = RetryPolicy()
    if "enabled" in body:
        p.enabled = bool(body["enabled"])
    if "max_attempts" in body:
        p.max_attempts = max(1, int(body["max_attempts"]))
    if "base_delay_ms" in body:
        p.base_delay_ms = max(50, int(body["base_delay_ms"]))
    if "max_delay_ms" in body:
        p.max_delay_ms = max(p.base_delay_ms, int(body["max_delay_ms"]))
    if isinstance(body.get("tools"), list):
        p.tools = body["tools"]
    return p


_POLICY: RetryPolicy | None = None


def get_policy(reload: bool = False) -> RetryPolicy:
    global _POLICY
    if reload or _POLICY is None:
        _POLICY = _load_policy()
    return _POLICY


def execute_with_retry(
    tool_name: str,
    runner: Callable[[], Any],
    on_retry: Callable[[int, str, float], None] | None = None,
) -> tuple[Any, int]:
    """Run `runner` with the active retry policy.

    Returns (final_result, n_attempts). The runner is expected to return a
    ToolResult-like object with .is_error and .error / .content attributes.
    """
    policy = get_policy()
    attempts = 0
    result = None
    while attempts < policy.max_attempts:
        attempts += 1
        result = runner()
        if not getattr(result, "is_error", False):
            return result, attempts

        err_text = ""
        try:
            err_text = result.content or getattr(result, "error", "") or ""
        except Exception:
            pass
        if not policy.should_retry(tool_name, err_text):
            return result, attempts
        if attempts >= policy.max_attempts:
            return result, attempts

        delay_ms = min(policy.max_delay_ms, policy.base_delay_ms * (2 ** (attempts - 1)))
        if on_retry:
            try:
                on_retry(attempts, err_text[:120], delay_ms / 1000)
            except Exception:
                pass
        time.sleep(delay_ms / 1000)
    return result, attempts
