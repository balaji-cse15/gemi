"""TodoList renderer — matches Claude Code's TaskListV2 visual.

Each todo has three states (pending / in_progress / completed) and renders as:

    ✔  Diagnose launcher failure          (strikethrough, dim)
    ◼  Implementing upgrades              (bold, accent color)
    ◻  Smoke-test + commit                (default)

Only ONE todo should be in_progress at any time. The widget is rebuilt from
scratch on every TodoWrite call — there's no in-place mutation, so transcripts
replay correctly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rich.console import Console, Group
from rich.text import Text

from . import glyphs
from .theme import get_palette, get_active_theme_name

TodoStatus = Literal["pending", "in_progress", "completed"]


@dataclass
class TodoItem:
    content: str
    status: TodoStatus
    activeForm: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "TodoItem":
        return cls(
            content=str(d.get("content", "")),
            status=d.get("status", "pending"),
            activeForm=str(d.get("activeForm") or d.get("active_form") or d.get("content", "")),
        )


def _icon_for(status: TodoStatus) -> tuple[str, str]:
    """Return (glyph, color_name) for a given status."""
    p = get_palette(get_active_theme_name())
    if status == "completed":
        return glyphs.TICK, p.success
    if status == "in_progress":
        return glyphs.SQUARE_SMALL_FILLED, p.buddy_shimmer  # accent / brand
    return glyphs.SQUARE_SMALL, p.text_muted


def render_todo_list(items: list[TodoItem], header: str | None = None) -> Group:
    """Build a Rich Group representing the todo list."""
    p = get_palette(get_active_theme_name())
    rows: list[Text] = []

    if header:
        rows.append(Text(header, style=f"bold {p.buddy}"))

    for it in items:
        glyph, color = _icon_for(it.status)
        line = Text()
        line.append(f"  {glyph}  ", style=color)
        if it.status == "completed":
            line.append(it.content, style=f"strike {p.text_muted}")
        elif it.status == "in_progress":
            label = it.activeForm or it.content
            line.append(label, style=f"bold {p.buddy_shimmer}")
        else:
            line.append(it.content, style=p.text)
        rows.append(line)

    if not items:
        rows.append(Text("  (no tasks)", style=f"dim {p.text_muted}"))

    # Footer summary
    total = len(items)
    if total > 0:
        done = sum(1 for i in items if i.status == "completed")
        in_prog = sum(1 for i in items if i.status == "in_progress")
        pending = total - done - in_prog
        summary = Text()
        summary.append(f"  ", style="")
        summary.append(f"{done}", style=f"bold {p.success}")
        summary.append(f" done · ", style=p.text_muted)
        if in_prog:
            summary.append(f"{in_prog}", style=f"bold {p.buddy_shimmer}")
            summary.append(f" in progress · ", style=p.text_muted)
        summary.append(f"{pending}", style=f"bold {p.text}")
        summary.append(f" open ", style=p.text_muted)
        summary.append(f"({done}/{total})", style=f"dim {p.text_muted}")
        rows.append(Text(""))
        rows.append(summary)

    return Group(*rows)


def print_todo_update(
    console: Console,
    items: list[TodoItem],
    title: str = "Update Todos",
) -> None:
    """Render a TodoWrite tool-call result inline (Claude-Code-style)."""
    p = get_palette(get_active_theme_name())
    header = Text()
    header.append(f"{glyphs.TREE_BRANCH} ", style=f"bold {p.buddy}")
    header.append(title, style=f"bold {p.text}")
    console.print(header)
    console.print(render_todo_list(items))
    console.print()
