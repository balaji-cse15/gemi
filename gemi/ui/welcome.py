"""Welcome screen — shown when launching without an agent or with /welcome."""
from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .banner import _gradient_logo
from .theme import get_palette, get_active_theme_name
from . import glyphs


def print_welcome(console: Console) -> None:
    from ..config import FLEET
    from ..tools.registry import ALL_TOOLS

    palette = get_palette(get_active_theme_name())

    logo = _gradient_logo(palette)

    tagline = Text()
    tagline.append("\n  ")
    tagline.append("✻", style=palette.buddy_shimmer)
    tagline.append("  ", style="muted")
    tagline.append("Local-fleet AI coding assistant", style=f"bold {palette.text}")
    tagline.append("  ·  ", style="dim")
    from .. import __version__
    tagline.append(f"v{__version__}", style="dim")
    tagline.append("\n")

    # Quick stats
    stats = Table.grid(padding=(0, 2))
    stats.add_column(style=f"bold {palette.buddy}", justify="right")
    stats.add_column(style="muted")

    running = sum(1 for a in FLEET if a.is_proxy_running())
    stats.add_row("✻", f"{len(FLEET)} agents in fleet, {running} online")
    stats.add_row("◇", f"{len(ALL_TOOLS)} tools available")
    stats.add_row("⊞", "Multi-agent delegation, hooks, smart compaction")
    stats.add_row("🔒", "Three-tier permission model (SAFE / WRITE / YOLO)")

    # Quick start
    qs = Table.grid(padding=(0, 1))
    qs.add_column(style=f"bold {palette.buddy_shimmer}", no_wrap=True)
    qs.add_column(style="muted")
    qs.add_row("gemi --status", "show fleet status")
    qs.add_row("gemi -a <slug>", "launch with a specific agent")
    qs.add_row("gemi --yolo", "enable dangerous tools")
    qs.add_row("/help", "see all commands")
    qs.add_row("/agent", "switch active agent")
    qs.add_row("/theme", "change color scheme")

    quickstart_panel = Panel(
        qs,
        title=f"[bold {palette.buddy}]Quick start[/]",
        title_align="left",
        border_style=palette.border,
        padding=(0, 1),
    )

    body = Group(logo, tagline, stats, Text(""), quickstart_panel)

    console.print(Panel(
        body,
        border_style=palette.buddy,
        padding=(0, 2),
        expand=False,
    ))
