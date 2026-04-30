"""Compact tool-call rendering — Claude Code's `⏺ Tool(args)` + `⎿ result` form.

Additive helpers; the existing tree-connector rendering in render.py keeps
working unchanged. Code paths that want the compact look (e.g. TodoWrite,
quick file reads, predictable shell commands) call into this module.

Visual pattern:

    ⏺ Read(gemi/app.py)
      ⎿ Read 856 lines

    ⏺ Bash(npm test)
      ⎿ 247 lines (ctrl-r to expand)

    ⏺ Update Todos
      ⎿ ✔ Diagnose launcher
        ◼ Building TodoWrite
        ◻ Wire permission prompt
"""
from __future__ import annotations

from typing import Any

from rich.console import Console, Group
from rich.text import Text

from . import glyphs
from .theme import get_palette, get_active_theme_name


def _format_args(name: str, args: dict[str, Any]) -> str:
    """One-line summary of tool args — file paths, commands, queries."""
    if not args:
        return ""
    # Heuristics by tool name
    if name in ("read_file", "edit_file", "write_file", "delete_file"):
        return str(args.get("file_path", "")).strip()
    if name in ("bash", "powershell", "cmd", "shell"):
        cmd = str(args.get("command", "")).strip().splitlines()[:1]
        return cmd[0] if cmd else ""
    if name == "grep":
        pat = args.get("pattern", "")
        path = args.get("path", "")
        return f"{pat!r}{f' in {path}' if path else ''}"
    if name == "glob":
        return str(args.get("pattern", ""))
    if name in ("web_fetch", "web_search"):
        return str(args.get("url") or args.get("query", ""))
    # Generic: first scalar value, truncated
    for k in ("query", "url", "path", "name", "command", "pattern", "input"):
        v = args.get(k)
        if isinstance(v, str) and v:
            return v[:80] + ("…" if len(v) > 80 else "")
    return ""


def render_tool_call_compact(
    console: Console,
    name: str,
    args: dict[str, Any],
    *,
    is_error: bool = False,
    is_progress: bool = False,
) -> None:
    """Print `⏺ Tool(arg)` for a tool call header. Use ANSI colors only — no panels."""
    p = get_palette(get_active_theme_name())
    if is_error:
        marker = glyphs.CROSS_HEAVY
        marker_color = p.error
    elif is_progress:
        marker = glyphs.TREE_BRANCH
        marker_color = p.warning
    else:
        marker = glyphs.TREE_BRANCH
        marker_color = p.buddy

    line = Text()
    line.append(f"{marker} ", style=f"bold {marker_color}")
    line.append(name, style=f"bold {p.text}")
    summary = _format_args(name, args)
    if summary:
        line.append("(", style=p.text_muted)
        line.append(summary, style=p.info)
        line.append(")", style=p.text_muted)
    console.print(line, highlight=False)


def render_tool_result_compact(
    console: Console,
    summary: str,
    *,
    is_error: bool = False,
    indent: int = 2,
) -> None:
    """Print `  ⎿ summary` for a tool result. Single line, no chrome."""
    p = get_palette(get_active_theme_name())
    pad = " " * indent
    line = Text()
    line.append(pad)
    line.append(f"{glyphs.TREE_CONTINUE} ", style=p.text_muted)
    if is_error:
        line.append(summary, style=f"bold {p.error}")
    else:
        line.append(summary, style=p.text_muted)
    console.print(line, highlight=False)


def output_summary(text: str, *, max_lines: int = 5, label: str = "Output") -> str:
    """Build a head-truncated summary like Claude Code's `Output (N lines)` form.

    Returns:
        "247 lines"                              if > max_lines and short summary OK
        "Output (247 lines, first 5 shown):..."  if you want the preview folded in
    """
    lines = text.splitlines()
    n = len(lines)
    if n == 0:
        if not text:
            return f"{label} (empty)"
        return f"{label} ({len(text)} chars)"
    if n <= max_lines:
        return f"{label} ({n} {'line' if n == 1 else 'lines'})"
    head = "\n".join(lines[:max_lines])
    return f"{label} ({n} lines, ctrl-r to expand)\n{head}\n  …{n - max_lines} more lines"
