"""Permission prompt — Claude-Code-style numbered/arrow-nav menu.

Replaces the flat `[y/n/a/d]` line with a proper navigable menu:

    Tool: bash
    Command: rm -rf node_modules

    ❯ 1. Yes
      2. Yes, and don't ask again for `rm -rf:*`
      3. No, tell Claude what to do differently (esc)

Built on `questionary` for the arrow-nav. Falls back to a plain numbered
list if questionary isn't installed (won't break the app).

Returns one of:
    "yes"            — approved this call
    "yes_always"     — approved + add rule for this prefix/tool
    "no"             — rejected, optional feedback to be passed to model
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import glyphs

PermissionDecision = Literal["yes", "yes_always", "no"]


@dataclass
class PermissionRequest:
    tool_name: str               # e.g. "bash", "write_file"
    summary: str                 # e.g. "rm -rf node_modules" or "edit gemi/app.py"
    detail: str = ""             # multi-line context (diff preview, full command, etc.)
    rule_suggestion: str = ""    # e.g. "rm -rf:*" — what "always" would whitelist
    is_dangerous: bool = False   # red banner / extra confirm if true


def _render_header(req: PermissionRequest) -> str:
    """Build the multi-line header that prints above the prompt."""
    from .theme import get_palette, get_active_theme_name
    p = get_palette(get_active_theme_name())
    glyph = glyphs.WARNING_TRI if req.is_dangerous else glyphs.INFO_I
    color = "yellow" if req.is_dangerous else "cyan"
    lines = [
        f"\n  [bold {color}]{glyph}  Tool: {req.tool_name}[/bold {color}]",
        f"  [dim]{req.summary}[/dim]",
    ]
    if req.detail:
        lines.append("")
        for ln in req.detail.splitlines()[:20]:
            lines.append(f"  [dim]│[/dim] {ln}")
    return "\n".join(lines) + "\n"


def ask_permission(req: PermissionRequest, console=None) -> tuple[PermissionDecision, str]:
    """Ask the user to approve a tool call. Returns (decision, feedback_text).

    The feedback_text is non-empty only when the user picks "no" and types
    a reason — that gets injected into the next user message so the model
    knows why and can adapt.
    """
    from rich.console import Console
    if console is None:
        console = Console()

    # Print the contextual header
    console.print(_render_header(req))

    # Build the option labels (Claude-Code-exact wording)
    options = [
        ("yes", "Yes"),
    ]
    if req.rule_suggestion:
        options.append(
            ("yes_always", f"Yes, and don't ask again for `{req.rule_suggestion}`")
        )
    else:
        options.append(("yes_always", f"Yes, and don't ask again for {req.tool_name} calls"))
    options.append(("no", "No, tell Gemi what to do differently (esc)"))

    # Try questionary first (arrow nav, numbered, single keypress)
    try:
        import questionary
        choice = questionary.select(
            "Allow this tool call?",
            choices=[
                questionary.Choice(title=label, value=val)
                for val, label in options
            ],
            qmark=glyphs.POINTER,
            instruction=" (↑/↓ to navigate, Enter to confirm, Esc to cancel)",
            use_indicator=True,
            use_shortcuts=True,
        ).ask()
        if choice is None or choice == "no":
            feedback = ""
            if choice == "no":
                feedback = questionary.text(
                    "Tell Gemi what to do differently (or leave blank to just reject):"
                ).ask() or ""
            return ("no", feedback)
        return (choice, "")
    except Exception:
        # Fallback: plain stdin numbered prompt
        return _ask_fallback(options, console)


def _ask_fallback(options, console) -> tuple[PermissionDecision, str]:
    """Plain-stdin fallback when questionary is unavailable or stdin is broken."""
    from rich.text import Text
    for i, (_, label) in enumerate(options, 1):
        line = Text()
        line.append(f"  {i}. ", style="bold")
        line.append(label)
        console.print(line)
    console.print()
    try:
        resp = input("  Choose [1/2/3] (default 3=no): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return ("no", "")
    mapping = {
        "1": "yes", "y": "yes",
        "2": "yes_always", "a": "yes_always",
        "3": "no", "n": "no", "": "no",
    }
    decision = mapping.get(resp, "no")
    feedback = ""
    if decision == "no":
        try:
            feedback = input("  Reason (optional): ").strip()
        except (EOFError, KeyboardInterrupt):
            pass
    return (decision, feedback)
