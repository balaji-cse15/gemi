"""Multi-agent orchestration — delegate tasks across the fleet.

This module supports three patterns:
  1. delegate(): run one prompt against another agent and return result
  2. vote():     run the same prompt against N agents in parallel
  3. race():     same as vote, but return the FIRST to complete

Used by:
  - The agent_call tool (in-loop delegation)
  - The /vote and /race slash commands (user-driven multi-agent)
"""
from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import AgentDef, FLEET_BY_SLUG, get_agent
from .provider import ProviderError, send_message, extract_text, extract_usage, TokenUsage


@dataclass
class DelegationResult:
    agent: str = ""
    quant: str = ""
    text: str = ""
    error: str = ""
    elapsed: float = 0.0
    usage: TokenUsage = field(default_factory=TokenUsage)
    succeeded: bool = False


def delegate(
    target_slug: str,
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.2,
    timeout: int = 120,
) -> DelegationResult:
    """Send a one-shot prompt to another agent. No tool loop — just text in/out."""
    agent = get_agent(target_slug)
    if not agent:
        return DelegationResult(agent=target_slug, error=f"Unknown agent: {target_slug}")
    if not agent.is_proxy_running():
        return DelegationResult(
            agent=target_slug,
            quant=agent.quant,
            error=f"Agent {target_slug} proxy is offline at {agent.proxy_url}",
        )

    t0 = time.time()
    try:
        response = send_message(
            agent=agent,
            messages=[{"role": "user", "content": prompt}],
            system=system or f"You are {agent.name}. {agent.role}.",
            tools=None,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        elapsed = time.time() - t0
        text = extract_text(response)
        usage = extract_usage(response)
        return DelegationResult(
            agent=target_slug, quant=agent.quant,
            text=text, elapsed=elapsed, usage=usage,
            succeeded=True,
        )
    except ProviderError as e:
        return DelegationResult(
            agent=target_slug, quant=agent.quant,
            error=str(e), elapsed=time.time() - t0,
        )
    except Exception as e:
        return DelegationResult(
            agent=target_slug, quant=agent.quant,
            error=f"Unexpected: {e}", elapsed=time.time() - t0,
        )


def _filter_running(slugs: list[str] | None) -> list[AgentDef]:
    if slugs:
        agents = [get_agent(s) for s in slugs]
        agents = [a for a in agents if a is not None]
    else:
        agents = list(FLEET_BY_SLUG.values())
    return [a for a in agents if a.is_proxy_running()]


def vote(
    prompt: str,
    targets: list[str] | None = None,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.3,
    timeout: int = 90,
    parallelism: int = 4,
) -> list[DelegationResult]:
    """Run the same prompt across multiple agents in parallel; return all results."""
    agents = _filter_running(targets)
    if not agents:
        return []

    results: list[DelegationResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallelism) as pool:
        futures = {
            pool.submit(
                delegate, a.slug, prompt, system, max_tokens, temperature, timeout
            ): a
            for a in agents
        }
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result(timeout=timeout + 5))
            except Exception as e:
                a = futures[fut]
                results.append(DelegationResult(
                    agent=a.slug, quant=a.quant, error=f"Future failed: {e}",
                ))
    return results


def race(
    prompt: str,
    targets: list[str] | None = None,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.3,
    timeout: int = 90,
    parallelism: int = 4,
) -> tuple[DelegationResult | None, list[DelegationResult]]:
    """First-to-finish wins. Returns (winner, all_completed_so_far)."""
    agents = _filter_running(targets)
    if not agents:
        return None, []

    completed: list[DelegationResult] = []
    winner: DelegationResult | None = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallelism) as pool:
        futures = {
            pool.submit(
                delegate, a.slug, prompt, system, max_tokens, temperature, timeout
            ): a
            for a in agents
        }
        try:
            for fut in concurrent.futures.as_completed(futures, timeout=timeout):
                try:
                    result = fut.result()
                    completed.append(result)
                    if result.succeeded and winner is None:
                        winner = result
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        break
                except Exception as e:
                    a = futures[fut]
                    completed.append(DelegationResult(
                        agent=a.slug, error=f"Future failed: {e}",
                    ))
        except concurrent.futures.TimeoutError:
            pass
    return winner, completed


def find_specialist(role_keyword: str) -> AgentDef | None:
    """Find first agent in the fleet whose role matches the keyword (heuristic delegation)."""
    keyword = role_keyword.lower()
    for agent in FLEET_BY_SLUG.values():
        if keyword in agent.role.lower():
            return agent
    return None
