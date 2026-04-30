"""Inline agent/model picker — Claude-Code-style menu.

Shows a numbered list of agents with the currently active one marked, then
reads a single keystroke (1-9, 0 for the 10th) to switch. Falls back to
showing the picker without selection if the user hits Esc/Ctrl+C.

Layout (inspired by Claude Code's Models menu):

    ╭─ ✻ Models ──────────────────────────────────────╮
    │  1  Mini Max Gemi          Q4_K_M    high       │
    │  2  Local Agent 2          Q5_K_M    standard   │
    │  3  Local Agent 3       ✓  Q4_K_M    high       │
    │  4  Local Agent 4          IQ3_M     fast       │
    │  ...                                             │
    │  Effort                                          │
    │  l  YOLO  ⚪                                     │
    │  k  PLAN  ⚪                                     │
    │  j  AUTO  ⚪                                     │
    ╰──────────────────────────────────────────────────╯
"""
from __future__ import annotations

import sys
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import glyphs
from .theme import get_palette, get_active_theme_name


def _quality_tier_glyph(tier: str) -> str:
    return {
        "premium":  glyphs.EFFORT_MAX,
        "high":     glyphs.EFFORT_HIGH,
        "standard": glyphs.EFFORT_HIGH,
        "fast":     glyphs.EFFORT_MEDIUM,
        "economy":  glyphs.EFFORT_LOW,
    }.get(tier, "●")


def _read_single_key() -> str:
    """Read one keystroke from stdin without requiring Enter (best-effort)."""
    if sys.platform == "win32":
        try:
            import msvcrt
            ch = msvcrt.getwch()
            return ch
        except Exception:
            return input("> ").strip()
    try:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return input("> ").strip()


def render_agent_menu(console: Console, fleet, current_slug: str = "",
                      yolo: bool = False, plan: bool = False, auto: bool = False) -> None:
    """Render the agent picker as a styled panel."""
    palette = get_palette(get_active_theme_name())

    table = Table.grid(padding=(0, 1))
    table.add_column(style=f"bold {palette.buddy_shimmer}", width=3, justify="right")
    table.add_column(width=3, justify="center")
    table.add_column(no_wrap=True)
    table.add_column(width=3, justify="center")
    table.add_column(style=f"bold {palette.warning}", width=8)
    table.add_column(style="dim", width=10)
    table.add_column(style="muted", width=20)

    for i, a in enumerate(fleet, 1):
        key = str(i) if i < 10 else "0"
        active = a.slug == current_slug
        glyph = _quality_tier_glyph(a.quality_tier)

        if active:
            check = Text("✓", style=f"bold {palette.success}")
            name = Text(a.name, style=f"bold {palette.info}")
        else:
            check = Text(" ", style="dim")
            name = Text(a.name, style="muted")

        running = a.is_proxy_running()
        status = Text("●" if running else "○", style=palette.success if running else palette.error)

        table.add_row(
            f"{key}",
            status,
            name,
            check,
            a.quant or "?",
            a.quality_tier,
            a.role[:20],
        )

    # Mode toggles (lower section, like Claude Code's Effort menu)
    table.add_row("", "", Text(""), Text(""), "", "", "")  # spacer
    table.add_row(
        Text("y", style=f"bold {palette.buddy_shimmer}"),
        Text("⚡", style=palette.yolo) if yolo else Text(" ", style="dim"),
        Text("YOLO", style=f"bold {palette.yolo}" if yolo else "muted"),
        Text("✓", style=f"bold {palette.success}") if yolo else Text(" "),
        "",
        "",
        "bypass permissions",
    )
    table.add_row(
        Text("p", style=f"bold {palette.buddy_shimmer}"),
        Text("◇", style=palette.plan) if plan else Text(" ", style="dim"),
        Text("PLAN", style=f"bold {palette.plan}" if plan else "muted"),
        Text("✓", style=f"bold {palette.success}") if plan else Text(" "),
        "",
        "",
        "plan before executing",
    )
    table.add_row(
        Text("a", style=f"bold {palette.buddy_shimmer}"),
        Text("↻", style=palette.auto) if auto else Text(" ", style="dim"),
        Text("AUTO", style=f"bold {palette.auto}" if auto else "muted"),
        Text("✓", style=f"bold {palette.success}") if auto else Text(" "),
        "",
        "",
        "non-stop autonomous",
    )

    panel = Panel(
        table,
        title=f"[bold {palette.buddy}]✻ Agents & Modes[/]",
        title_align="left",
        border_style=palette.buddy,
        padding=(0, 1),
        expand=False,
    )
    console.print(panel)


def show_picker(console: Console, fleet, current_slug: str = "",
                yolo: bool = False, plan: bool = False, auto: bool = False) -> dict[str, Any]:
    """Display the picker and read a single key.

    Returns a dict describing the action:
      {"kind": "agent", "index": N}        — switch to fleet[N]
      {"kind": "yolo"}                     — toggle YOLO
      {"kind": "plan"}                     — toggle PLAN
      {"kind": "auto"}                     — toggle AUTO
      {"kind": "none"}                     — cancelled
    """
    render_agent_menu(console, fleet, current_slug, yolo, plan, auto)
    palette = get_palette(get_active_theme_name())
    console.print(
        f"  [muted]press [bold {palette.buddy_shimmer}]1-9[/]"
        f"[muted] for agent · [/][bold {palette.buddy_shimmer}]y[/]"
        f"[muted]/[/][bold {palette.buddy_shimmer}]p[/]"
        f"[muted]/[/][bold {palette.buddy_shimmer}]a[/]"
        f"[muted] for modes · [/][bold {palette.buddy_shimmer}]Esc[/]"
        f"[muted] to cancel[/]"
    )
    try:
        ch = _read_single_key()
    except (KeyboardInterrupt, EOFError):
        return {"kind": "none"}

    if not ch:
        return {"kind": "none"}
    ch = ch.strip().lower()
    if ch in ("\x1b", "\x03", "q", "esc"):
        return {"kind": "none"}
    if ch.isdigit():
        idx = int(ch)
        # 1-9 → 0-8 ; 0 → 9 (the 10th)
        idx = idx - 1 if idx >= 1 else 9
        if 0 <= idx < len(fleet):
            return {"kind": "agent", "index": idx}
        return {"kind": "none"}
    if ch == "y":
        return {"kind": "yolo"}
    if ch == "p":
        return {"kind": "plan"}
    if ch == "a":
        return {"kind": "auto"}
    return {"kind": "none"}
