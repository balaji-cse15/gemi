"""Rendering for assistant messages, tool calls, and tool results.

Beautified v0.11+ with:
  - Tree-connector tool call summaries
  - Bordered panels for code/diff output with syntax highlighting
  - Status icons (✓ ✗ ◐ ◌) coloured by tier and outcome
  - Word-level diff highlighting
  - Dim/active rendering for cached vs fresh tool results

v0.2 (post-Claude-Code-source-study):
  - todo_write tool calls auto-render the TodoWrite widget instead of
    raw text — see _try_todo_widget below.
  - Setting GEMI_COMPACT_RENDER=1 switches every tool call/result to the
    Claude-Code-exact `⏺ Tool(args)` / `  ⎿ result` form. The verbose
    tree-connector form is still the default.
"""
from __future__ import annotations

import os
import re
from typing import Any


def _compact_mode() -> bool:
    """Check whether the user opted into Claude-Code-style compact rendering."""
    val = os.environ.get("GEMI_COMPACT_RENDER", "").lower()
    return val in ("1", "true", "yes", "on")


def _compact_label(tool_name: str) -> str:
    """Pretty action verb for compact result labels."""
    return {
        "read_file": "Read",
        "write_file": "Wrote",
        "edit_file": "Edited",
        "delete_file": "Deleted",
        "glob": "Found",
        "grep": "Matched",
        "bash": "Output",
        "powershell": "Output",
        "cmd": "Output",
        "git": "Output",
        "web_fetch": "Fetched",
        "web_search": "Searched",
    }.get(tool_name, "Output")

from rich.box import HEAVY, ROUNDED, SIMPLE
from rich.columns import Columns
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ..query_engine import TurnResult
from . import glyphs
from .theme import get_palette, get_active_theme_name


# Tool icons - 2-3 char visual signatures
TOOL_ICONS = {
    # Shell / execution
    "bash": "$ ",   "powershell": "PS",  "git": "g ", "python_run": "py",
    "pip": "📦", "npm": "📦", "docker": "🐳",
    # File / nav
    "read_file": "📄", "write_file": "✎ ", "edit_file": "✎ ",
    "delete_file": "✕ ", "move_file": "→ ", "copy_file": "⎘ ",
    "glob": "**", "grep": "/?", "tree": "🌲", "diff": "Δ ",
    "multi_edit": "✎ᴹ",
    # Web / network
    "web_fetch": "🌐", "web_search": "🔍", "http_request": "↦ ",
    "download": "⬇ ", "port_scan": "⊞ ", "dns_lookup": "🌐", "url_parse": "🔗",
    # Data
    "json_parse": "{ }", "yaml_parse": "y ", "toml_parse": "t ", "xml_parse": "<>",
    "csv_parse": ", ", "regex": "/r", "math": "± ", "hash": "# ", "base64": "64",
    # Security
    "jwt": "🔑", "uuid": "🆔", "secrets_gen": "🔑", "dotenv": "🔑",
    "hash_crack": "💀", "crypto": "🔒", "forensics": "🔬",
    "payload_gen": "💥", "header_analysis": "📊", "subdomain": "🌐",
    "whois": "🌐", "stego": "🎭",
    # System / dev
    "system_info": "🖥 ", "env": "🔐", "process": "⚙ ", "archive": "📦",
    "clipboard": "📋", "screenshot": "📸", "watch": "👁 ", "timestamp": "🕐",
    "encode": "🔣", "template": "📝", "markdown": "📑", "notebook": "📓",
    "snippet": "✂ ", "benchmark": "⏱ ", "dependency": "🔗",
    "scaffold": "🏗 ", "code_analysis": "🧠", "sqlite": "🗄 ",
    # AI
    "think": "💭", "agent_call": "🤝", "agent_vote": "🗳 ",
}


LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".rs": "rust", ".go": "go",
    ".java": "java", ".c": "c", ".cpp": "cpp", ".h": "c",
    ".cs": "csharp", ".rb": "ruby", ".php": "php", ".sh": "bash",
    ".ps1": "powershell", ".sql": "sql", ".html": "html",
    ".css": "css", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".xml": "xml", ".md": "markdown",
    ".dockerfile": "dockerfile", ".tf": "hcl",
}


def _detect_lang(name: str, args: dict[str, Any]) -> str | None:
    fp = args.get("file_path", "")
    if fp:
        for ext, lang in LANG_MAP.items():
            if fp.lower().endswith(ext):
                return lang
    return None


def _icon(name: str) -> str:
    return TOOL_ICONS.get(name, "✻ ")


def _human_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    elif n < 65536:
        return f"{n / 1024:.1f}KB"
    elif n < 1048576:
        return f"{n / 1024:.0f}KB"
    return f"{n / 1048576:.1f}MB"


def _tier_badge(tool) -> Text:
    """Render a tier badge for a tool."""
    p = get_palette(get_active_theme_name())
    if tool is None:
        return Text("")
    if tool.dangerous:
        return Text(" YOLO ", style=f"black on {p.tier_yolo}")
    if tool.read_only:
        return Text(" SAFE ", style=f"black on {p.tier_safe}")
    return Text(" WRITE ", style=f"black on {p.tier_write}")


# ============================================================================
# TOP-LEVEL: assistant turn rendering
# ============================================================================

def render_assistant(console: Console, result: TurnResult) -> None:
    p = get_palette(get_active_theme_name())

    if result.error:
        console.print()
        console.print(Panel(
            Text(result.error, style=f"bold {p.error}"),
            title=f"[bold {p.error}]✗ error[/]",
            border_style=p.error,
            expand=False,
            padding=(0, 1),
        ))
        console.print()
        return

    for tc in result.tool_results:
        render_tool_result(console, tc)

    if result.text and not result.streamed:
        console.print()
        try:
            md = Markdown(result.text, code_theme="monokai")
            console.print(Padding(md, (0, 2)))
        except Exception:
            console.print(result.text)
        console.print()

    _render_turn_footer(console, result)


def _render_turn_footer(console: Console, result: TurnResult) -> None:
    p = get_palette(get_active_theme_name())
    if result.usage.total <= 0:
        return
    parts = []
    parts.append(f"[muted]{glyphs.BUDDY_GLYPH_SMALL}[/]")
    parts.append(f"[cost]{result.usage.input_tokens:,} in / {result.usage.output_tokens:,} out[/cost]")
    parts.append(f"[dim]{result.elapsed:.1f}s[/dim]")

    tools_used = len(result.tool_calls)
    if tools_used:
        parts.append(f"[dim]{tools_used} tool{'s' if tools_used != 1 else ''}[/dim]")

    cache_hits = getattr(result, "cache_hits", 0)
    if cache_hits:
        parts.append(f"[tool.cached]{cache_hits} cached[/]")

    cost_usd = getattr(result, "cost_usd", 0.0)
    if cost_usd > 0.0001:
        parts.append(f"[cost]~${cost_usd:.4f}[/]")

    sep = " [separator]│[/] "
    console.print(f"  {sep.join(parts)}")


# ============================================================================
# TOOL CALL — header rendering (when call starts)
# ============================================================================

def _try_todo_widget(console: Console, name: str, output: str) -> bool:
    """If this is a todo_write result, render the widget instead of raw text.

    Returns True if handled, False if the caller should fall through to the
    normal tool-result renderer.
    """
    if name != "todo_write":
        return False
    try:
        from ..tools.todo import TodoWriteTool
        from .todo_widget import TodoItem, print_todo_update
        items = [TodoItem.from_dict(d) for d in TodoWriteTool.current_todos()]
        print_todo_update(console, items)
        return True
    except Exception:
        return False


def render_tool_call(console: Console, name: str, args: dict[str, Any], tool_id: str) -> None:
    if _compact_mode():
        from .render_compact import render_tool_call_compact
        return render_tool_call_compact(console, name, args)
    from ..tools.registry import get_tool
    p = get_palette(get_active_theme_name())
    icon = _icon(name)
    tool = get_tool(name)

    summary = _summarize_tool_args(name, args)

    line = Text()
    line.append("  ")
    line.append("⎯", style="separator")
    line.append("◇", style=f"bold {p.buddy}")
    line.append("⎯ ", style="separator")
    line.append(f"{icon} ", style="tool.icon")
    line.append(name, style="tool.name")

    # Tier badge if dangerous
    if tool and tool.dangerous:
        line.append(" ")
        line.append("YOLO", style=f"bold {p.tier_yolo}")

    if summary:
        line.append("  ")
        line.append(summary)
    console.print(line, highlight=False)


# ============================================================================
# TOOL RESULT — rendered after the call completes
# ============================================================================

def render_tool_result(console: Console, result: dict[str, Any]) -> None:
    name = result.get("name", "?")
    output = result.get("output", "")
    is_error = result.get("is_error", False)

    # TodoWrite gets first-class treatment: render the widget instead of the
    # raw confirmation string. Works regardless of compact-mode setting.
    if not is_error and _try_todo_widget(console, name, output):
        return

    if _compact_mode():
        from .render_compact import render_tool_result_compact, output_summary
        if is_error:
            render_tool_result_compact(console, output[:120].splitlines()[0] if output else "(error)", is_error=True)
        else:
            render_tool_result_compact(console, output_summary(output, label=_compact_label(name)))
        return

    p = get_palette(get_active_theme_name())
    args = result.get("args", {})
    cached = result.get("cached", False)

    if is_error:
        if "BLOCKED:" in output or "DENIED" in output:
            line = Text()
            line.append("    ")
            line.append("⎯", style="separator")
            line.append("✗", style=f"bold {p.tier_yolo}")
            line.append("⎯ ", style="separator")
            line.append("BLOCKED ", style=f"bold {p.tier_yolo}")
            line.append(name, style="tool.name")
            line.append(f"  — enable /yolo to use dangerous tools", style="dim")
            console.print(line)
        else:
            line = Text()
            line.append("    ")
            line.append("⎯", style="separator")
            line.append("✗", style="error")
            line.append("⎯ ", style="separator")
            line.append(f"{name}: ", style="tool.error")
            preview = output[:200].replace("\n", " ")
            line.append(preview, style="dim")
            console.print(line)
        return

    if not output:
        return

    icon = _icon(name)
    elapsed = result.get("elapsed", 0.0)
    time_tag = f"  [dim]{elapsed:.2f}s[/dim]" if elapsed > 0.05 else ""
    cache_tag = "  [tool.cached]cached[/]" if cached else ""

    # Route to specialized renderers
    if name in ("bash", "powershell", "python_run", "git", "pip", "npm", "docker"):
        _render_shell_output(console, name, output, icon, time_tag, cache_tag)
    elif name == "read_file":
        _render_code_output(console, name, output, icon, _detect_lang(name, args), time_tag, cache_tag)
    elif name == "code_analysis":
        _render_code_output(console, name, output, icon, "json", time_tag, cache_tag)
    elif name in ("grep", "glob", "tree"):
        _render_search_output(console, name, output, icon, time_tag, cache_tag)
    elif name == "diff":
        _render_diff_output(console, name, output, icon, time_tag, cache_tag)
    elif name in ("edit_file", "multi_edit"):
        _render_edit_output(console, name, output, icon, args, time_tag, cache_tag)
    elif name == "think":
        _render_think_output(console, name, output, icon, args, time_tag)
    elif name == "agent_call":
        _render_agent_call_output(console, name, output, icon, args, time_tag, cache_tag)
    elif name == "agent_vote":
        _render_agent_vote_output(console, name, output, icon, args, time_tag, cache_tag)
    elif name in ("write_file", "delete_file", "move_file", "copy_file"):
        _render_simple_status_output(console, name, output, icon, time_tag)
    elif name in ("hash_crack", "crypto", "forensics", "payload_gen",
                  "header_analysis", "subdomain", "whois", "stego"):
        _render_security_output(console, name, output, icon, time_tag, cache_tag)
    elif name == "web_search":
        _render_websearch_output(console, name, output, icon, args, time_tag, cache_tag)
    else:
        _render_capped_output(console, name, output, icon, time_tag, cache_tag, max_lines=8)


# ============================================================================
# SPECIALIZED RENDERERS
# ============================================================================

def _result_header(name: str, icon: str, summary: str = "", time_tag: str = "",
                   cache_tag: str = "") -> Text:
    p = get_palette(get_active_theme_name())
    h = Text()
    h.append("    ")
    h.append("⎯", style="separator")
    h.append("✓", style=p.success)
    h.append("⎯ ", style="separator")
    h.append(f"{icon} ", style="tool.icon")
    h.append(name, style="tool.name")
    if summary:
        h.append(f"  {summary}", style="dim")
    if time_tag:
        h.append(time_tag.replace("[dim]", "").replace("[/dim]", ""), style="dim")
    if cache_tag:
        h.append("  cached", style="tool.cached")
    return h


def _render_shell_output(console: Console, name: str, output: str, icon: str,
                          time_tag: str = "", cache_tag: str = "") -> None:
    lines = output.splitlines()
    summary = f"[dim]{len(lines)} line{'s' if len(lines) != 1 else ''}[/dim]"
    console.print(_result_header(name, icon, summary.replace('[dim]', '').replace('[/dim]', ''),
                                 time_tag, cache_tag))
    if not lines:
        return
    if len(lines) <= 12:
        for line in lines:
            console.print(f"      [dim]│[/] {line}", highlight=False)
    else:
        for line in lines[:6]:
            console.print(f"      [dim]│[/] {line}", highlight=False)
        console.print(f"      [dim]│[/] [muted]… ({len(lines) - 12} lines hidden) …[/]")
        for line in lines[-6:]:
            console.print(f"      [dim]│[/] {line}", highlight=False)


def _render_code_output(console: Console, name: str, output: str, icon: str,
                        lang: str | None = None, time_tag: str = "",
                        cache_tag: str = "") -> None:
    lines = output.splitlines()
    size = _human_size(len(output))
    summary = f"{size}, {len(lines)} lines"
    console.print(_result_header(name, icon, summary, time_tag, cache_tag))

    if lang and len(output) < 16000:
        try:
            preview_lines = lines[:40]
            preview = "\n".join(preview_lines)
            # Strip leading "N\t" line numbers from read_file output
            if name == "read_file":
                cleaned = []
                for ln in preview_lines:
                    parts = ln.split("\t", 1)
                    cleaned.append(parts[1] if len(parts) == 2 else ln)
                preview = "\n".join(cleaned)
            syntax = Syntax(preview, lang, theme="monokai",
                            line_numbers=True, word_wrap=False, indent_guides=True)
            panel = Panel(syntax, border_style="border", expand=False, padding=(0, 0))
            console.print(Padding(panel, (0, 4)))
            if len(lines) > 40:
                console.print(f"      [muted]… ({len(lines) - 40} more lines)[/]")
        except Exception:
            pass


def _render_search_output(console: Console, name: str, output: str, icon: str,
                          time_tag: str = "", cache_tag: str = "") -> None:
    p = get_palette(get_active_theme_name())
    lines = output.splitlines()
    count = len(lines)
    console.print(_result_header(name, icon, f"{count} result{'s' if count != 1 else ''}",
                                 time_tag, cache_tag))
    if count == 0:
        return
    show = lines if count <= 12 else lines[:8]
    for line in show:
        # Bold filenames; dim line numbers and content
        match = re.match(r"^(.+?):(\d+):(.*)$", line)
        if match:
            file, lno, content = match.groups()
            t = Text()
            t.append("      ")
            t.append(file, style=f"bold {p.info}")
            t.append(":", style="dim")
            t.append(lno, style=p.warning)
            t.append(":", style="dim")
            t.append(content[:200], style="muted")
            console.print(t, highlight=False)
        else:
            console.print(f"      [muted]{line}[/]", highlight=False)
    if count > 12:
        console.print(f"      [muted]… ({count - 8} more)[/]")


def _render_diff_output(console: Console, name: str, output: str, icon: str,
                        time_tag: str = "", cache_tag: str = "") -> None:
    lines = output.splitlines()
    console.print(_result_header(name, icon, f"{len(lines)} lines", time_tag, cache_tag))
    body = []
    for line in lines[:40]:
        if line.startswith("+++") or line.startswith("---"):
            body.append(f"      [bold white]{line}[/]")
        elif line.startswith("+"):
            body.append(f"      [diff.add]{line}[/]")
        elif line.startswith("-"):
            body.append(f"      [diff.remove]{line}[/]")
        elif line.startswith("@@"):
            body.append(f"      [info]{line}[/]")
        else:
            body.append(f"      [muted]{line}[/]")
    for b in body:
        console.print(b, highlight=False)
    if len(lines) > 40:
        console.print(f"      [muted]… ({len(lines) - 40} more)[/]")


def _render_edit_output(console: Console, name: str, output: str, icon: str,
                        args: dict[str, Any], time_tag: str = "",
                        cache_tag: str = "") -> None:
    p = get_palette(get_active_theme_name())
    fp = args.get("file_path", "")
    summary = fp.split("\\")[-1].split("/")[-1] if fp else ""
    console.print(_result_header(name, icon, summary, time_tag, cache_tag))
    old = args.get("old_string", "")
    new = args.get("new_string", "")
    if not old or not new or len(old) > 800 or len(new) > 800:
        console.print(f"      [success]{output}[/]")
        return
    # Render side-by-side mini-diff
    old_lines = old.splitlines() or [""]
    new_lines = new.splitlines() or [""]
    for line in old_lines[:6]:
        console.print(f"      [diff.remove]- {line}[/]", highlight=False)
    if len(old_lines) > 6:
        console.print(f"      [muted]  … ({len(old_lines) - 6} removed lines hidden)[/]")
    for line in new_lines[:6]:
        console.print(f"      [diff.add]+ {line}[/]", highlight=False)
    if len(new_lines) > 6:
        console.print(f"      [muted]  … ({len(new_lines) - 6} added lines hidden)[/]")
    console.print(f"      [success]✓ {output}[/]")


def _render_think_output(console: Console, name: str, output: str, icon: str,
                         args: dict[str, Any], time_tag: str = "") -> None:
    p = get_palette(get_active_theme_name())
    thought = args.get("thought", "")
    h = Text()
    h.append("    ")
    h.append("⎯", style="separator")
    h.append("◆", style=p.info)
    h.append("⎯ ", style="separator")
    h.append("think ", style=f"bold {p.info}")
    h.append(f"{len(thought)} chars", style="dim")
    console.print(h)
    if thought:
        # Show first ~3 lines of the thought as a preview
        preview = "\n".join(thought.splitlines()[:3])
        if len(preview) > 200:
            preview = preview[:200] + "…"
        console.print(Padding(
            Text(preview, style="muted"),
            (0, 6),
        ))


def _render_simple_status_output(console: Console, name: str, output: str, icon: str,
                                  time_tag: str = "") -> None:
    p = get_palette(get_active_theme_name())
    h = Text()
    h.append("    ")
    h.append("⎯", style="separator")
    h.append("✓", style=p.success)
    h.append("⎯ ", style="separator")
    h.append(f"{icon} ", style="tool.icon")
    h.append(name, style="tool.name")
    h.append("  ")
    h.append(output, style=f"{p.success}")
    if time_tag:
        h.append(time_tag.replace("[dim]", "").replace("[/dim]", ""), style="dim")
    console.print(h, highlight=False)


def _render_agent_call_output(console: Console, name: str, output: str, icon: str,
                              args: dict[str, Any], time_tag: str = "",
                              cache_tag: str = "") -> None:
    p = get_palette(get_active_theme_name())
    target = args.get("agent") or args.get("role_keyword", "?")
    h = Text()
    h.append("    ")
    h.append("⎯", style="separator")
    h.append("🤝", style=p.info)
    h.append("⎯ ", style="separator")
    h.append("agent_call ", style=f"bold {p.info}")
    h.append(f"→ {target}", style=f"bold {p.buddy}")
    if time_tag:
        h.append(time_tag.replace("[dim]", "").replace("[/dim]", ""), style="dim")
    console.print(h)
    # Show response preview
    lines = output.splitlines()
    preview = lines[1:8] if len(lines) > 1 else lines[:8]
    for ln in preview:
        console.print(f"      [muted]│ {ln}[/]", highlight=False)
    if len(lines) > 9:
        console.print(f"      [muted]│ … ({len(lines) - 9} more lines)[/]")


def _render_agent_vote_output(console: Console, name: str, output: str, icon: str,
                              args: dict[str, Any], time_tag: str = "",
                              cache_tag: str = "") -> None:
    p = get_palette(get_active_theme_name())
    h = Text()
    h.append("    ")
    h.append("⎯", style="separator")
    h.append("🗳", style=p.info)
    h.append("⎯ ", style="separator")
    h.append("agent_vote ", style=f"bold {p.info}")
    if time_tag:
        h.append(time_tag.replace("[dim]", "").replace("[/dim]", ""), style="dim")
    console.print(h)
    lines = output.splitlines()
    for ln in lines[:25]:
        if ln.startswith("# Vote:"):
            console.print(f"      [bold {p.buddy}]{ln}[/]", highlight=False)
        elif ln.startswith("## "):
            console.print(f"      [bold {p.info}]{ln[3:]}[/]", highlight=False)
        else:
            console.print(f"      [muted]{ln}[/]", highlight=False)
    if len(lines) > 25:
        console.print(f"      [muted]… ({len(lines) - 25} more lines)[/]")


def _render_security_output(console: Console, name: str, output: str, icon: str,
                            time_tag: str = "", cache_tag: str = "") -> None:
    p = get_palette(get_active_theme_name())
    h = Text()
    h.append("    ")
    h.append("⎯", style="separator")
    h.append("◉", style=p.warning)
    h.append("⎯ ", style="separator")
    h.append(f"{icon} ", style="tool.icon")
    h.append(name, style="tool.name")
    h.append(" ")
    h.append("YOLO", style=f"bold {p.tier_yolo}")
    h.append(f"  {_human_size(len(output))}", style="dim")
    if time_tag:
        h.append(time_tag.replace("[dim]", "").replace("[/dim]", ""), style="dim")
    console.print(h)
    lines = output.splitlines()
    for ln in lines[:14]:
        console.print(f"      [muted]│ {ln}[/]", highlight=False)
    if len(lines) > 14:
        console.print(f"      [muted]│ … ({len(lines) - 14} more lines)[/]")


def _render_websearch_output(console: Console, name: str, output: str, icon: str,
                             args: dict[str, Any], time_tag: str = "",
                             cache_tag: str = "") -> None:
    p = get_palette(get_active_theme_name())
    query = args.get("query", "")
    h = Text()
    h.append("    ")
    h.append("⎯", style="separator")
    h.append("🔍", style=p.info)
    h.append("⎯ ", style="separator")
    h.append("web_search ", style=f"bold {p.info}")
    if query:
        h.append(f'"{query[:60]}"', style=p.text)
    if time_tag:
        h.append(time_tag.replace("[dim]", "").replace("[/dim]", ""), style="dim")
    console.print(h)
    # Each result block is title / url / snippet — colorize accordingly
    lines = output.splitlines()
    for ln in lines[:30]:
        s = ln.strip()
        if re.match(r"^\d+\. ", s):
            console.print(f"      [bold {p.buddy}]{s}[/]", highlight=False)
        elif s.startswith("http"):
            console.print(f"      [info]{s}[/]", highlight=False)
        else:
            console.print(f"      [muted]{s}[/]", highlight=False)


def _render_capped_output(console: Console, name: str, output: str, icon: str,
                          time_tag: str = "", cache_tag: str = "",
                          max_lines: int = 6) -> None:
    p = get_palette(get_active_theme_name())
    size = _human_size(len(output))
    lines = output.splitlines()
    console.print(_result_header(name, icon, size, time_tag, cache_tag))
    if len(lines) <= max_lines:
        for line in lines:
            console.print(f"      [muted]│ {line}[/]", highlight=False)
    else:
        half = max_lines // 2
        for line in lines[:half]:
            console.print(f"      [muted]│ {line}[/]", highlight=False)
        console.print(f"      [muted]│ … ({len(lines) - max_lines} hidden) …[/]")
        for line in lines[-half:]:
            console.print(f"      [muted]│ {line}[/]", highlight=False)


# ============================================================================
# SUMMARIZE TOOL ARGS for inline display
# ============================================================================

_TOOL_SUMMARY_RULES: dict[str, str] = {
    "bash": "$ {command:.100}",
    "powershell": "PS> {command:.100}",
    "read_file": "{file_path}",
    "write_file": "{file_path}",
    "edit_file": "{file_path}",
    "delete_file": "{path}",
    "move_file": "{source}",
    "copy_file": "{source}",
    "glob": "{pattern}",
    "grep": "/{pattern}/",
    "git": "git {args}",
    "pip": "pip {args}",
    "npm": "npm {args}",
    "docker": "docker {args}",
    "web_fetch": "{url:.80}",
    "web_search": "{query:.60}",
    "http_request": "{method} {url:.80}",
    "download": "{url:.80}",
    "json_parse": "{action} {file_path}",
    "yaml_parse": "{action} {file_path}",
    "toml_parse": "{action} {file_path}",
    "xml_parse": "{action} {file_path}",
    "csv_parse": "{action} {file_path}",
    "markdown": "{action} {file_path}",
    "math": "{expression:.60}",
    "regex": "{action} /{pattern:.40}/",
    "hash": "{algorithm}",
    "base64": "{action}",
    "port_scan": "{host} {ports}",
    "dns_lookup": "{domain}",
    "uuid": "{action}",
    "timestamp": "{action}",
    "encode": "{action} {format}",
    "url_parse": "{action}",
    "sqlite": "{action} {database}",
    "tree": "{path}",
    "diff": "{file_a} <-> {file_b}",
    "multi_edit": "s/{pattern}/{replacement}/",
    "hash_crack": "{action}",
    "crypto": "{action} {cipher}",
    "forensics": "{action} {file_path}",
    "payload_gen": "{type}",
    "header_analysis": "{url:.60}",
    "subdomain": "{domain}",
    "whois": "{domain}",
    "stego": "{action}",
    "snippet": "{action} {name}",
    "benchmark": "{action} {iterations} iter",
    "dependency": "{action} {file_path}",
    "scaffold": "{action} {template}",
    "agent_call": "{agent}{role_keyword} {prompt:.50}",
    "agent_vote": "{prompt:.60}",
    "system_info": "",
    "env": "{action} {name}",
    "process": "{action}",
    "archive": "{action} {path}",
    "clipboard": "{action}",
    "screenshot": "",
    "watch": "{action}",
    "code_analysis": "{action} {file_path}",
    "notebook": "{action} {file_path}",
    "template": "{action}",
    "secrets_gen": "{type}",
    "dotenv": "{action} {file_path}",
    "jwt": "{token:.30}",
}


def _summarize_tool_args(name: str, args: dict[str, Any]) -> Text:
    p = get_palette(get_active_theme_name())
    if name == "python_run":
        code = args.get("code", "")
        return Text(code[:80] + ("…" if len(code) > 80 else ""), style="muted")
    if name == "think":
        thought = args.get("thought", "")
        return Text(thought[:60] + ("…" if len(thought) > 60 else ""), style="muted")

    template = _TOOL_SUMMARY_RULES.get(name)
    if template is None:
        return Text("", style="muted")

    parts: list[str] = []
    for segment in template.split(" "):
        if not segment:
            continue
        if segment.startswith("{") and segment.rstrip("/").endswith("}"):
            clean = segment.strip("{}")
            limit = 0
            if ":." in clean:
                field_name, lim = clean.split(":.")
                limit = int(lim)
            else:
                field_name = clean
            val = str(args.get(field_name, ""))
            if limit and len(val) > limit:
                val = val[:limit] + "…"
            if val:
                parts.append(val)
        else:
            parts.append(segment)

    text = " ".join(parts).strip()
    return Text(text, style="muted")


# ============================================================================
# Fleet table
# ============================================================================

def render_fleet_table(console: Console, agents: list) -> None:
    p = get_palette(get_active_theme_name())
    table = Table(
        title=f"\n[bold {p.buddy}]✻ Agent Fleet[/]",
        title_justify="left",
        border_style=p.border,
        show_lines=False,
        box=ROUNDED,
        padding=(0, 1),
    )
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column("Slug", style=f"bold {p.info}")
    table.add_column("Role", style="dim")
    table.add_column("Quant", style=p.warning)
    table.add_column("Ctx", style="muted", justify="right")
    table.add_column("P", style="muted", justify="right")
    table.add_column("Tier", style="muted")
    table.add_column("Caps", style=p.warning)
    table.add_column("Status", justify="center")

    for i, a in enumerate(agents, 1):
        model_up = a.is_model_running()
        proxy_up = a.is_proxy_running()
        if model_up and proxy_up:
            status = Text("● READY", style=f"bold {p.success}")
        elif proxy_up:
            status = Text("◐ PROXY", style=f"bold {p.warning}")
        elif model_up:
            status = Text("◐ MODEL", style=f"bold {p.warning}")
        else:
            status = Text("○ OFF", style=f"dim {p.error}")
        caps = ", ".join(a.capability_tags) if a.capability_tags else ""
        tier_glyph = {
            "premium": glyphs.EFFORT_MAX, "high": glyphs.EFFORT_HIGH,
            "standard": glyphs.EFFORT_HIGH, "fast": glyphs.EFFORT_MEDIUM,
            "economy": glyphs.EFFORT_LOW,
        }.get(a.quality_tier, "●")
        tier_label = f"{tier_glyph} {a.quality_tier}"
        table.add_row(
            str(i), a.slug, a.role,
            a.quant or "?", f"{a.context:,}", str(a.parallel),
            tier_label, caps, status,
        )
    console.print(table)


# ============================================================================
# Tools table
# ============================================================================

def render_tools_table(console: Console, tools: list) -> None:
    p = get_palette(get_active_theme_name())
    table = Table(
        title=f"\n[bold {p.buddy}]✻ Tools[/]",
        title_justify="left",
        border_style=p.border,
        show_lines=False,
        box=ROUNDED,
        padding=(0, 1),
    )
    table.add_column("Name", style="tool.name", no_wrap=True)
    table.add_column("Tier", style="dim", width=6, justify="center")
    table.add_column("Description", style="muted")

    for t in tools:
        if t.dangerous:
            tier = Text(" YOLO  ", style=f"black on {p.tier_yolo}")
        elif t.read_only:
            tier = Text(" SAFE  ", style=f"black on {p.tier_safe}")
        else:
            tier = Text(" WRITE ", style=f"black on {p.tier_write}")
        desc = t.description[:80] + "…" if len(t.description) > 80 else t.description
        table.add_row(t.name, tier, desc)
    console.print(table)


# ============================================================================
# Status bar (for /status, /mode displays)
# ============================================================================

def render_status_bar(console: Console, agent_name: str, mode: str,
                       tokens: int, tools_count: int) -> None:
    p = get_palette(get_active_theme_name())
    parts = []
    parts.append(f"[bold {p.buddy}]✻[/]")
    parts.append(f"[bold {p.info}]{agent_name}[/]")
    if mode:
        parts.append(f"[bold {p.warning}]{mode}[/]")
    parts.append(f"[muted]{tokens:,} tokens[/]")
    parts.append(f"[muted]{tools_count} tools[/]")
    sep = " [separator]│[/] "
    console.print(f"  {sep.join(parts)}")
