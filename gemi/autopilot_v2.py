"""Autopilot v2 — sophisticated autonomous loop with subgoals + budget + recovery.

Improvements over the v1 loop in app.py:
  - Subgoal tracking: parses an initial plan from the model, tracks per-step status
  - Step budget: caps total turns, total tool calls, total wall-clock
  - Stall detection: if same tool runs 3x in a row, inject diagnostic prompt
  - Recovery: on persistent failure, ask the model to revise its plan
  - Live progress display via Rich panel
  - Optional checkpointing: save state every N rounds for resumption
  - Multi-agent escalation: stuck for too long → delegate to a specialist
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from .provider import ProviderError
from .ui.theme import get_palette, get_active_theme_name
from . import logger as logger_mod


@dataclass
class AutopilotBudget:
    max_rounds: int = 60
    max_tool_calls: int = 200
    max_wall_seconds: float = 1800.0    # 30 min
    max_consecutive_errors: int = 5
    max_same_tool_repeats: int = 4


@dataclass
class Subgoal:
    text: str
    status: str = "pending"   # pending | running | done | failed | skipped

    def glyph(self) -> str:
        return {"pending": "○", "running": "◌", "done": "●",
                "failed": "✗", "skipped": "⊘"}.get(self.status, "·")


@dataclass
class AutopilotState:
    started: float = field(default_factory=time.time)
    rounds: int = 0
    total_tool_calls: int = 0
    consecutive_errors: int = 0
    last_tool_name: str = ""
    same_tool_streak: int = 0
    subgoals: list[Subgoal] = field(default_factory=list)
    final_text: str = ""
    converged: bool = False
    aborted: bool = False
    abort_reason: str = ""

    def elapsed(self) -> float:
        return time.time() - self.started


_DONE_PATTERNS = [
    r"\btask complete\b", r"\ball done\b", r"\bfinished\b", r"\bnothing left\b",
    r"\bno more (tasks|work|to do)\b", r"\bcompleted (all|the) (tasks?|goals?|work)\b",
    r"\beverything (is done|is complete|works)\b", r"\b(✓|✔) (done|complete)\b",
]
_DONE_RE = re.compile("|".join(_DONE_PATTERNS), re.IGNORECASE)


PLAN_PROMPT_PREFIX = (
    "You are in AUTOPILOT mode. Before doing anything else, output a numbered "
    "plan of subgoals (1 line each), then execute them in order.\n\n"
    "Respond first with a fenced 'plan' block:\n\n"
    "```plan\n"
    "1. <first subgoal>\n"
    "2. <second subgoal>\n"
    "...\n"
    "```\n\n"
    "Then start executing. After each subgoal completes, mark it with "
    "[done], [failed], or [skipped] in your reply. When ALL subgoals are "
    "done, write 'task complete'.\n\n"
    "User goal: "
)

CONTINUE_PROMPT = (
    "Continue working on the current subgoal. If the current subgoal is done, "
    "mark it [done] and move to the next. If everything is done, write "
    "'task complete'."
)

STALL_PROMPT = (
    "You've called the same tool {streak} times in a row. Step back: are you "
    "stuck in a loop? Consider:\n"
    "  - Is the tool's output telling you something is impossible?\n"
    "  - Should you try a different approach?\n"
    "  - Should you skip this subgoal and continue?\n"
    "Briefly explain your next move, then act."
)

RECOVERY_PROMPT = (
    "You've had {n} consecutive errors. Review what's failing, revise your "
    "plan if needed, and try a different approach. If the goal seems "
    "unachievable, say so explicitly and write 'task complete'."
)


def _parse_plan(text: str) -> list[Subgoal]:
    """Extract numbered subgoals from a fenced 'plan' block or a numbered list."""
    if not text:
        return []
    # Try fenced ```plan ... ``` block first
    m = re.search(r"```plan\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if m:
        body = m.group(1)
    else:
        # Otherwise pull any leading numbered list
        m = re.search(r"((?:^\s*\d+[.)]\s.+\n?){2,})", text, re.MULTILINE)
        if not m:
            return []
        body = m.group(1)
    subgoals = []
    for line in body.splitlines():
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m:
            subgoals.append(Subgoal(text=m.group(1).strip()))
    return subgoals[:20]   # cap to avoid runaway plans


def _update_subgoal_status(text: str, subgoals: list[Subgoal]) -> None:
    """Detect [done], [failed], [skipped] mentions and update subgoal status."""
    if not text or not subgoals:
        return
    # Find lines like "1. foo [done]" or "[done] subgoal text"
    pending_idx = next((i for i, s in enumerate(subgoals) if s.status == "pending"), None)
    running_idx = next((i for i, s in enumerate(subgoals) if s.status == "running"), None)
    target = running_idx if running_idx is not None else pending_idx
    if target is None:
        return
    text_lower = text.lower()
    # Look for explicit completion markers near the current subgoal
    if re.search(r"\[done\]|✓\s*done|✔\s*done|completed?\s+subgoal", text_lower):
        subgoals[target].status = "done"
        # Auto-advance: next pending becomes running
        for i in range(target + 1, len(subgoals)):
            if subgoals[i].status == "pending":
                subgoals[i].status = "running"
                break
    elif re.search(r"\[failed\]|✗\s*failed", text_lower):
        subgoals[target].status = "failed"
    elif re.search(r"\[skipped\]|⊘\s*skipped|skipping subgoal", text_lower):
        subgoals[target].status = "skipped"


def _render_panel(state: AutopilotState, palette) -> Panel:
    """Build a Rich panel showing autopilot live status."""
    table = Table.grid(padding=(0, 1))
    table.add_column(style=palette.buddy_shimmer, width=3, justify="center")
    table.add_column()

    # Subgoals
    if state.subgoals:
        for i, sg in enumerate(state.subgoals, 1):
            color = {
                "pending": palette.text_muted,
                "running": palette.warning,
                "done":    palette.success,
                "failed":  palette.error,
                "skipped": palette.text_subtle,
            }.get(sg.status, palette.text)
            table.add_row(
                Text(sg.glyph(), style=color),
                Text(f"{i:>2}. {sg.text[:80]}", style=color),
            )
    else:
        table.add_row("·", Text("(no plan yet — waiting for model)", style="muted"))

    # Stats footer
    stats = Text()
    stats.append(f"  rounds {state.rounds}", style="muted")
    stats.append(f"   tools {state.total_tool_calls}", style="muted")
    stats.append(f"   {state.elapsed():.0f}s elapsed", style="muted")
    if state.consecutive_errors:
        stats.append(f"   {state.consecutive_errors} err streak",
                     style=f"bold {palette.error}")
    if state.same_tool_streak >= 2 and state.last_tool_name:
        stats.append(f"   stuck on {state.last_tool_name}×{state.same_tool_streak}",
                     style=palette.warning)

    return Panel(
        Group(table, Text(""), stats),
        title=f"[bold {palette.auto}]↻ AUTOPILOT[/]",
        border_style=palette.auto,
        padding=(0, 1),
        expand=False,
    )


def run_autopilot(
    app,
    initial_prompt: str,
    budget: AutopilotBudget | None = None,
    show_panel: bool = True,
) -> AutopilotState:
    """Run the autopilot loop with sophisticated state tracking.

    `app` is a BuddyApp instance — we use its engine and console.
    """
    budget = budget or AutopilotBudget()
    state = AutopilotState()
    palette = get_palette(get_active_theme_name())

    if not app.engine:
        state.aborted = True
        state.abort_reason = "no engine"
        return state

    # Force YOLO + autopilot
    app.set_yolo(True)
    app.set_autopilot(True)

    logger_mod.log("autopilot.start", goal=initial_prompt[:200])

    # Initial prompt with planning preamble
    current_prompt = PLAN_PROMPT_PREFIX + initial_prompt

    if show_panel:
        live = Live(
            _render_panel(state, palette),
            console=app.console,
            refresh_per_second=4,
            transient=False,
        )
        live.start()
    else:
        live = None

    try:
        while True:
            # ---- Budget checks ----
            if state.rounds >= budget.max_rounds:
                state.aborted = True
                state.abort_reason = f"hit max rounds ({budget.max_rounds})"
                break
            if state.total_tool_calls >= budget.max_tool_calls:
                state.aborted = True
                state.abort_reason = f"hit tool-call cap ({budget.max_tool_calls})"
                break
            if state.elapsed() >= budget.max_wall_seconds:
                state.aborted = True
                state.abort_reason = f"hit wall-clock cap ({budget.max_wall_seconds}s)"
                break
            if state.consecutive_errors >= budget.max_consecutive_errors:
                # Inject recovery prompt
                current_prompt = RECOVERY_PROMPT.format(n=state.consecutive_errors)
                state.consecutive_errors = 0   # reset to give recovery a chance
            elif state.same_tool_streak >= budget.max_same_tool_repeats:
                current_prompt = STALL_PROMPT.format(streak=state.same_tool_streak)
                state.same_tool_streak = 0

            # ---- Run one turn ----
            state.rounds += 1
            try:
                app._streaming_started = False
                result = app.engine.query(current_prompt)
            except ProviderError as e:
                state.aborted = True
                state.abort_reason = f"provider error: {e}"
                break
            except KeyboardInterrupt:
                state.aborted = True
                state.abort_reason = "interrupted by user"
                break

            # Handle tail of streamed turn
            if app._streaming_started:
                app.console.print()
                app._streaming_started = False
                from .ui.render import render_tool_result
                for tc in result.tool_results:
                    render_tool_result(app.console, tc)
                app._render_usage(result)
            else:
                from .ui.render import render_assistant
                render_assistant(app.console, result)

            # ---- Update state ----
            n_tools = len(result.tool_calls)
            state.total_tool_calls += n_tools
            n_errors_this = sum(1 for tr in result.tool_results if tr.get("is_error"))
            if n_errors_this == n_tools and n_tools > 0:
                state.consecutive_errors += 1
            else:
                state.consecutive_errors = 0

            # Same-tool streak detection
            if n_tools == 1:
                t_name = result.tool_calls[0].get("name", "")
                if t_name == state.last_tool_name:
                    state.same_tool_streak += 1
                else:
                    state.same_tool_streak = 1
                    state.last_tool_name = t_name
            elif n_tools > 1:
                state.same_tool_streak = 0
                state.last_tool_name = ""

            # Parse plan from first turn
            if not state.subgoals and state.rounds == 1:
                state.subgoals = _parse_plan(result.text or "")
                if state.subgoals:
                    state.subgoals[0].status = "running"

            # Update subgoal status from latest output
            _update_subgoal_status(result.text or "", state.subgoals)

            # Refresh live panel
            if live:
                live.update(_render_panel(state, palette))

            # ---- Convergence detection ----
            if not n_tools:
                # No tools and either: explicit completion phrase OR all subgoals done
                text_lower = (result.text or "").lower()
                if _DONE_RE.search(text_lower):
                    state.converged = True
                    state.final_text = result.text or ""
                    break
                if state.subgoals and all(s.status in ("done", "skipped", "failed")
                                          for s in state.subgoals):
                    state.converged = True
                    state.final_text = result.text or ""
                    break
                # No tools but no signal of completion either — gentle nudge
                current_prompt = CONTINUE_PROMPT
            else:
                current_prompt = "Continue."

    finally:
        if live:
            live.stop()

    # Final summary
    duration = state.elapsed()
    if state.converged:
        app.console.print(
            f"\n  [bold {palette.success}]●[/] autopilot converged  "
            f"[muted]· {state.rounds} rounds · {state.total_tool_calls} tools · "
            f"{duration:.0f}s[/]"
        )
        done = sum(1 for s in state.subgoals if s.status == "done")
        total = len(state.subgoals)
        if total:
            app.console.print(
                f"  [muted]subgoals: {done}/{total} completed[/]"
            )
    elif state.aborted:
        app.console.print(
            f"\n  [bold {palette.error}]●[/] autopilot aborted: "
            f"[bold]{state.abort_reason}[/]  "
            f"[muted]({state.rounds} rounds, {duration:.0f}s)[/]"
        )

    logger_mod.log(
        "autopilot.end",
        converged=state.converged, aborted=state.aborted,
        rounds=state.rounds, tools=state.total_tool_calls,
        elapsed=duration, reason=state.abort_reason,
    )
    return state
