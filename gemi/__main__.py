"""Entry point for `python -m gemi` or the `gemi` command."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


if sys.platform == "win32":
    # Default cmd.exe codepage (cp1252) can't encode the glyphs Rich uses
    # (✻, ✓, ◇, …). Reconfigure stdout/stderr to UTF-8 so unicode rendering
    # works regardless of the user's console codepage. PowerShell 7 already
    # defaults to UTF-8; this fixes legacy cmd.exe and CI runners.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gemi",
        description="Claude-Code-like CLI wired to local agent fleet",
    )
    parser.add_argument(
        "--agent", "-a",
        default="",
        help="Agent slug (e.g. local-agent-1, local-agent-2). Auto-selects if omitted.",
    )
    parser.add_argument(
        "--workspace", "-w",
        default=".",
        help="Workspace directory (default: current directory).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show fleet status and exit.",
    )
    parser.add_argument(
        "--yolo",
        action="store_true",
        help="Bypass all tool permission checks.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Start in plan mode (agent plans before executing).",
    )
    parser.add_argument(
        "--autopilot", "--auto",
        action="store_true",
        help="Start in autopilot mode (non-stop autonomous work).",
    )
    parser.add_argument(
        "--resume", "-r",
        default="",
        nargs="?",
        const="last",
        help="Resume a saved session by ID. With no value: resumes most recent.",
    )
    parser.add_argument(
        "--profile", "-P",
        default="",
        help="Apply a profile preset (agent + mode + theme + workspace).",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List all tools with tiers and exit.",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List saved sessions and exit.",
    )
    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version and exit.",
    )
    parser.add_argument(
        "--exec", "-e",
        default="",
        dest="exec_prompt",
        help="Run a single prompt and exit (non-interactive).",
    )
    args = parser.parse_args(argv)

    if args.version:
        from . import __version__
        print(f"gemi {__version__}")
        return 0

    from .config import FLEET, get_agent
    from rich.console import Console
    from .ui.theme import GEMI_THEME

    if args.status:
        from .ui.render import render_fleet_table
        console = Console(theme=GEMI_THEME)
        render_fleet_table(console, FLEET)
        return 0

    if args.list_tools:
        from .tools.registry import ALL_TOOLS
        from .ui.render import render_tools_table
        console = Console(theme=GEMI_THEME)
        render_tools_table(console, ALL_TOOLS)
        safe = sum(1 for t in ALL_TOOLS if t.read_only)
        write = sum(1 for t in ALL_TOOLS if not t.read_only and not t.dangerous)
        yolo = sum(1 for t in ALL_TOOLS if t.dangerous)
        console.print(
            f"\n  [green]{safe} SAFE[/] | [yellow]{write} WRITE[/] | "
            f"[bold red]{yolo} YOLO[/] | {len(ALL_TOOLS)} total\n"
        )
        return 0

    if args.list_sessions:
        from .session import list_sessions
        console = Console(theme=GEMI_THEME)
        sessions = list_sessions()
        if not sessions:
            console.print("[dim]No saved sessions.[/dim]")
        else:
            console.print(f"\n[bold]Saved Sessions ({len(sessions)}):[/bold]")
            for s in sessions:
                console.print(
                    f"  {s['id'][:40]:40} {s['agent']:20} "
                    f"{s['turns']} turns  {s['saved_at']}"
                )
            console.print(f"\n[dim]Resume with: gemi --resume <session-id>[/dim]\n")
        return 0

    agent = get_agent(args.agent) if args.agent else None
    workspace = Path(args.workspace).resolve()

    from .app import BuddyApp
    app = BuddyApp(
        agent=agent,
        workspace=workspace,
        yolo=args.yolo,
        plan_mode=args.plan,
        autopilot=args.autopilot,
    )

    if args.profile:
        from .profiles import get_profile, apply_profile
        prof = get_profile(args.profile)
        if not prof:
            console = Console(theme=GEMI_THEME)
            console.print(f"[error]Profile not found: {args.profile}[/error]")
            return 1
        apply_profile(app, prof)

    if args.resume:
        target = args.resume
        if target == "last":
            from .session import list_sessions
            sessions = list_sessions(limit=1)
            if not sessions:
                console = Console(theme=GEMI_THEME)
                console.print("[error]No saved sessions to resume.[/error]")
                return 1
            target = sessions[0]["id"]
        if app.resume_session(target):
            console = Console(theme=GEMI_THEME)
            console.print(f"[success]Resumed session: {app.session_id}[/success]")
        else:
            console = Console(theme=GEMI_THEME)
            console.print(f"[error]Session not found: {target}[/error]")
            return 1

    if args.exec_prompt:
        return app.run_once(args.exec_prompt)

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
