"""Slash command registry and dispatcher."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..app import BuddyApp

CommandHandler = Callable[["BuddyApp", list[str]], None]


class Command:
    def __init__(self, name: str, description: str, handler: CommandHandler):
        self.name = name
        self.description = description
        self.handler = handler


COMMANDS: dict[str, Command] = {}


def register(name: str, description: str) -> Callable[[CommandHandler], CommandHandler]:
    def decorator(fn: CommandHandler) -> CommandHandler:
        COMMANDS[name] = Command(name, description, fn)
        return fn
    return decorator


COMMAND_ALIASES: dict[str, str] = {
    "q": "quit",
    "x": "exit",
    "s": "save",
    "c": "clear",
    "r": "resume",
    "h": "help",
    "a": "agent",
    "t": "tools",
    "p": "ping",
    "u": "undo",
    "st": "stats",
    "ctx": "context",
    "ap": "autopilot",
    "tp": "template",
    "l": "launch",
    "d": "diff",
    "fk": "fork",
    "rn": "rename",
    "fl": "fleet",
    "rw": "rewind",
    "tl": "timeline",
    "v": "vote",
    "rc": "race",
    "dg": "delegate",
    "ws": "workspace_context",
    "ch": "cache",
    "pm": "perms",
    "hk": "hooks",
    "sp": "spend",
    "th": "theme",
    "w": "welcome",
    "pl": "plugins",
    "mc": "mcp",
    "j": "jobs",
    "lg": "logs",
    "u_": "use",
    "tk": "task",
    "pr": "profile",
    "ap_": "approval",
    "ll": "ls",
    "find_": "find",
}


def is_command(text: str) -> bool:
    return text.strip().startswith("/")


def handle_command(app: "BuddyApp", text: str) -> bool:
    parts = text.strip().split(maxsplit=1)
    cmd_name = parts[0].lstrip("/")
    args = parts[1].split() if len(parts) > 1 else []

    resolved = COMMAND_ALIASES.get(cmd_name, cmd_name)
    cmd = COMMANDS.get(resolved)
    if not cmd:
        app.console.print(f"[error]Unknown command: /{cmd_name}[/error]")
        app.console.print(f"[dim]Type /help for available commands.[/dim]")
        return True

    cmd.handler(app, args)
    return True


# --- Built-in commands ---

COMMAND_CATEGORIES = {
    "Session": ["clear", "save", "resume", "sessions", "delete", "rename", "fork", "export", "undo", "history", "compact", "rewind", "timeline", "profile"],
    "Modes": ["yolo", "plan", "autopilot", "mode", "approval"],
    "Fleet": ["agent", "status", "fleet", "ping", "launch", "template", "config", "vote", "race", "delegate", "task"],
    "Tools": ["tools", "skills", "memory", "cache", "hooks", "perms", "plugins", "mcp", "retrypolicy"],
    "Shell": ["sh", "ps", "cmd", "run", "ls", "cat", "pwd", "cd", "find"],
    "Background": ["bg", "jobs"],
    "Templates": ["use", "templates"],
    "Navigation": ["workspace", "workspace_context", "git", "diff"],
    "Tuning": ["temp", "tokens", "context", "search"],
    "Display": ["theme", "welcome"],
    "Logging": ["logs"],
    "System": ["help", "stats", "cost", "spend", "exit", "quit"],
}


@register("help", "Show available commands")
def cmd_help(app: "BuddyApp", args: list[str]) -> None:
    from rich.table import Table
    from rich.panel import Panel
    from rich.box import ROUNDED
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    rev_aliases: dict[str, list[str]] = {}
    for alias, target in COMMAND_ALIASES.items():
        rev_aliases.setdefault(target, []).append(alias)

    cat_glyph = {
        "Session":    "◇",
        "Modes":      "◈",
        "Fleet":      "✻",
        "Tools":      "◆",
        "Navigation": "▶",
        "Tuning":     "⚙",
        "Display":    "🎨",
        "System":     "ⓘ",
    }
    cat_color = {
        "Session":    palette.info,
        "Modes":      palette.warning,
        "Fleet":      palette.buddy,
        "Tools":      palette.success,
        "Navigation": palette.info,
        "Tuning":     palette.text_muted,
        "Display":    palette.buddy_shimmer,
        "System":     palette.text_muted,
    }

    app.console.print()
    app.console.print(
        f"  [bold {palette.buddy}]✻ Buddy commands[/]  "
        f"[muted]({len(COMMANDS)} commands, {len(COMMAND_ALIASES)} aliases)[/]"
    )

    shown = set()
    for category, names in COMMAND_CATEGORIES.items():
        cmds_in_cat = [(n, COMMANDS[n]) for n in names if n in COMMANDS]
        if not cmds_in_cat:
            continue
        app.console.print()
        glyph = cat_glyph.get(category, "·")
        color = cat_color.get(category, palette.text_muted)
        app.console.print(f"  [bold {color}]{glyph}  {category}[/]")
        for name, cmd in cmds_in_cat:
            alias_str = ""
            if name in rev_aliases:
                aliases_text = ", ".join(f"/{a}" for a in rev_aliases[name])
                alias_str = f"  [dim]({aliases_text})[/]"
            app.console.print(
                f"      [command]/{name:<18}[/]  [muted]{cmd.description}[/]{alias_str}"
            )
            shown.add(name)

    uncategorized = [(n, c) for n, c in sorted(COMMANDS.items()) if n not in shown]
    if uncategorized:
        app.console.print(f"\n  [bold {palette.text_muted}]·  Other[/]")
        for name, cmd in uncategorized:
            app.console.print(f"      [command]/{name:<18}[/]  [muted]{cmd.description}[/]")

    app.console.print()
    app.console.print(
        f"  [dim]tip:[/]  type [bold {palette.buddy_shimmer}]{{[/] for multi-line input  "
        f"[dim]·[/]  [bold {palette.buddy_shimmer}]/theme[/] to change colors  "
        f"[dim]·[/]  [bold {palette.buddy_shimmer}]/welcome[/] for the splash screen"
    )
    app.console.print()


@register("agent", "Open the agent picker, or /agent <slug> to switch directly")
def cmd_agent(app: "BuddyApp", args: list[str]) -> None:
    from ..config import FLEET, get_agent
    from ..ui.picker import show_picker
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    if args:
        slug = args[0]
        agent = get_agent(slug)
        if not agent:
            slug_lower = slug.lower()
            for a in FLEET:
                if a.slug.endswith(slug_lower) or slug_lower == a.name.lower():
                    agent = a
                    break
        if not agent:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  agent not found: [bold]{slug}[/]")
            avail = ", ".join(a.slug for a in FLEET)
            app.console.print(f"  [muted]available:[/] {avail}\n")
            return
        app.set_agent(agent)
        glyph = "●" if agent.is_proxy_running() else "○"
        app.console.print(
            f"\n  [bold {palette.buddy}]✻[/]  switched to "
            f"[bold {palette.info}]{agent.name}[/]  "
            f"[{palette.success if agent.is_proxy_running() else palette.error}]{glyph}[/]  "
            f"[muted]{agent.quant} · {agent.role}[/]\n"
        )
        return

    # No args — open the picker
    if not app.engine:
        app.console.print(f"\n  [muted]no agent active[/]\n")
        return
    result = show_picker(
        app.console, FLEET,
        current_slug=app.engine.agent.slug,
        yolo=app.yolo, plan=app.plan_mode, auto=app.autopilot,
    )
    kind = result.get("kind")
    if kind == "agent":
        target = FLEET[result["index"]]
        app.set_agent(target)
        glyph = "●" if target.is_proxy_running() else "○"
        app.console.print(
            f"\n  [bold {palette.buddy}]✻[/]  switched to "
            f"[bold {palette.info}]{target.name}[/]  "
            f"[{palette.success if target.is_proxy_running() else palette.error}]{glyph}[/]  "
            f"[muted]{target.quant} · {target.role}[/]\n"
        )
    elif kind == "yolo":
        app.set_yolo(not app.yolo)
        state = "ON" if app.yolo else "OFF"
        app.console.print(f"\n  [bold {palette.yolo}]⚡[/]  YOLO mode: [bold]{state}[/]\n")
    elif kind == "plan":
        app.set_plan_mode(not app.plan_mode)
        state = "ON" if app.plan_mode else "OFF"
        app.console.print(f"\n  [bold {palette.plan}]◇[/]  PLAN mode: [bold]{state}[/]\n")
    elif kind == "auto":
        app.set_autopilot(not app.autopilot)
        state = "ON" if app.autopilot else "OFF"
        app.console.print(f"\n  [bold {palette.auto}]↻[/]  AUTO mode: [bold]{state}[/]\n")
    else:
        app.console.print(f"\n  [muted](picker dismissed)[/]\n")


@register("status", "Show fleet status table")
def cmd_status(app: "BuddyApp", args: list[str]) -> None:
    from ..config import FLEET
    from ..ui.render import render_fleet_table
    app.console.print()
    render_fleet_table(app.console, FLEET)
    app.console.print()



@register("clear", "Clear conversation history")
def cmd_clear(app: "BuddyApp", args: list[str]) -> None:
    if app.engine:
        app.engine.clear()
    app.console.clear()
    app.console.print("[success]Conversation cleared.[/success]\n")


@register("cost", "Show token usage for this session")
def cmd_cost(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    u = app.engine.total_usage
    msgs = len(app.engine.messages)
    app.console.print(f"\n[command]Session Usage:[/command]")
    app.console.print(f"  Input tokens:  {u.input_tokens:,}")
    app.console.print(f"  Output tokens: {u.output_tokens:,}")
    app.console.print(f"  Total tokens:  {u.total:,}")
    app.console.print(f"  Messages:      {msgs}")
    app.console.print()


@register("workspace", "Show or change workspace directory")
def cmd_workspace(app: "BuddyApp", args: list[str]) -> None:
    from pathlib import Path
    if args:
        new_ws = Path(args[0]).resolve()
        if new_ws.is_dir():
            app.workspace = new_ws
            if app.engine:
                app.engine.workspace = new_ws
            app.console.print(f"[success]Workspace: {new_ws}[/success]")
        else:
            app.console.print(f"[error]Not a directory: {new_ws}[/error]")
    else:
        app.console.print(f"  Workspace: {app.workspace}")


@register("skills", "List available skills from the fleet")
def cmd_skills(app: "BuddyApp", args: list[str]) -> None:
    from ..skills.loader import list_skills
    skills = list_skills()
    if not skills:
        app.console.print("[dim]No skills found.[/dim]")
        return
    app.console.print(f"\n[command]Skills ({len(skills)}):[/command]")
    for s in skills[:50]:
        app.console.print(f"  [tool.name]{s['name']:30}[/tool.name] {s.get('description', '')[:50]}")
    if len(skills) > 50:
        app.console.print(f"  [dim]... and {len(skills) - 50} more[/dim]")
    app.console.print()


@register("memory", "Show or search memory")
def cmd_memory(app: "BuddyApp", args: list[str]) -> None:
    from ..memory.store import list_memories, search_memories
    if args:
        query = " ".join(args)
        results = search_memories(query)
        app.console.print(f"\n[command]Memory search: {query}[/command]")
        for m in results:
            app.console.print(f"  [{m['type']}] {m['name']}: {m.get('description', '')[:60]}")
    else:
        memories = list_memories()
        app.console.print(f"\n[command]Memories ({len(memories)}):[/command]")
        for m in memories:
            app.console.print(f"  [{m['type']}] {m['name']}")
    app.console.print()


@register("yolo", "Toggle YOLO mode (bypass all permissions)")
def cmd_yolo(app: "BuddyApp", args: list[str]) -> None:
    app.set_yolo(not app.yolo)
    state = "[bold yellow]ON[/bold yellow]" if app.yolo else "[dim]OFF[/dim]"
    app.console.print(f"  YOLO mode: {state} — all tool permissions {'bypassed' if app.yolo else 'enforced'}")


@register("plan", "Toggle plan mode (agent plans before executing)")
def cmd_plan(app: "BuddyApp", args: list[str]) -> None:
    app.set_plan_mode(not app.plan_mode)
    state = "[bold blue]ON[/bold blue]" if app.plan_mode else "[dim]OFF[/dim]"
    app.console.print(f"  Plan mode: {state} — agent {'will plan before acting' if app.plan_mode else 'executes directly'}")


@register("autopilot", "Toggle autopilot mode (non-stop autonomous work)")
def cmd_autopilot(app: "BuddyApp", args: list[str]) -> None:
    app.set_autopilot(not app.autopilot)
    state = "[bold cyan]ON[/bold cyan]" if app.autopilot else "[dim]OFF[/dim]"
    app.console.print(f"  Autopilot: {state} — agent {'works non-stop until done' if app.autopilot else 'waits for input each turn'}")
    if app.autopilot:
        app.console.print("  [dim]Ctrl+C to interrupt. Permissions auto-bypassed in autopilot.[/dim]")


@register("mode", "Show current mode settings")
def cmd_mode(app: "BuddyApp", args: list[str]) -> None:
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    def state_glyph(on: bool, on_color: str) -> str:
        if on:
            return f"[bold {on_color}]●[/]"
        return f"[dim {palette.text_subtle}]○[/]"

    app.console.print()
    app.console.print(f"  [bold {palette.buddy}]✻ execution modes[/]")
    app.console.print()
    app.console.print(f"      {state_glyph(app.yolo, palette.yolo)}  "
                      f"[bold {palette.yolo if app.yolo else palette.text_subtle}]YOLO[/]"
                      f"        [muted]bypass all permissions, enable dangerous tools[/]")
    app.console.print(f"      {state_glyph(app.plan_mode, palette.plan)}  "
                      f"[bold {palette.plan if app.plan_mode else palette.text_subtle}]PLAN[/]"
                      f"        [muted]agent plans before executing[/]")
    app.console.print(f"      {state_glyph(app.autopilot, palette.auto)}  "
                      f"[bold {palette.auto if app.autopilot else palette.text_subtle}]AUTO[/]"
                      f"        [muted]non-stop autonomous work[/]")

    if app.engine:
        agent = app.engine.agent
        app.console.print()
        app.console.print(f"  [bold {palette.buddy}]✻ active agent[/]")
        app.console.print()
        app.console.print(f"      [bold {palette.info}]{agent.name}[/]  "
                          f"[muted]{agent.slug}[/]")
        app.console.print(f"      [muted]model:[/]   {agent.short_model}  "
                          f"[bold {palette.warning}]{agent.quant}[/]")
        app.console.print(f"      [muted]context:[/] {agent.context:,} tokens  "
                          f"[muted]·[/]  parallel = {agent.parallel}")
        caps = ", ".join(agent.capability_tags) or "standard"
        app.console.print(f"      [muted]caps:[/]    {caps}")
    app.console.print()


@register("save", "Save current session")
def cmd_save(app: "BuddyApp", args: list[str]) -> None:
    sid = args[0] if args else ""
    path = app.save_current_session(session_id=sid)
    if path:
        app.console.print(f"[success]Session saved: {path.name}[/success]")
    else:
        app.console.print("[dim]Nothing to save (no messages yet).[/dim]")


@register("resume", "Resume a saved session")
def cmd_resume(app: "BuddyApp", args: list[str]) -> None:
    if not args:
        app.console.print("[dim]Usage: /resume <session-id>[/dim]")
        app.console.print("[dim]Use /sessions to list saved sessions.[/dim]")
        return
    if app.resume_session(args[0]):
        app.console.print(f"[success]Resumed session: {app.session_id}[/success]")
        app.console.print(f"  Agent: [agent.name]{app.engine.agent.name}[/agent.name]")
        app.console.print(f"  Turns: {app.engine.turn_count}")
    else:
        app.console.print(f"[error]Session not found: {args[0]}[/error]")


@register("sessions", "List saved sessions")
def cmd_sessions(app: "BuddyApp", args: list[str]) -> None:
    from ..session import list_sessions, session_count
    sessions = list_sessions()
    if not sessions:
        app.console.print("[dim]No saved sessions.[/dim]")
        return
    total = session_count()
    app.console.print(f"\n[command]Saved Sessions ({total} total, showing {len(sessions)}):[/command]")
    for s in sessions:
        size = f"{s['size_kb']:.0f}KB" if s.get('size_kb', 0) >= 1 else "<1KB"
        app.console.print(
            f"  [tool.name]{s['id'][:40]:40}[/tool.name] "
            f"{s['agent']:15} {s['turns']:2d}t  {size:>5}  {s['saved_at']}"
        )
        if s.get("preview"):
            app.console.print(f"    [dim]{s['preview']}[/dim]")
    app.console.print(f"\n[dim]Resume: /resume <id> | Delete: /delete <id>[/dim]\n")


@register("delete", "Delete a saved session")
def cmd_delete(app: "BuddyApp", args: list[str]) -> None:
    from ..session import delete_session
    if not args:
        app.console.print("[dim]Usage: /delete <session-id>[/dim]")
        return
    if delete_session(args[0]):
        app.console.print(f"[success]Deleted session: {args[0]}[/success]")
    else:
        app.console.print(f"[error]Session not found: {args[0]}[/error]")


@register("tools", "List tools (optionally filter by name, tier, or search)")
def cmd_tools_v2(app: "BuddyApp", args: list[str]) -> None:
    from ..tools.registry import ALL_TOOLS
    from ..ui.render import render_tools_table

    if not args:
        render_tools_table(app.console, ALL_TOOLS)
        safe = sum(1 for t in ALL_TOOLS if t.read_only)
        write = sum(1 for t in ALL_TOOLS if not t.read_only and not t.dangerous)
        yolo = sum(1 for t in ALL_TOOLS if t.dangerous)
        app.console.print(
            f"\n  [green]{safe} SAFE[/] | [yellow]{write} WRITE[/] | "
            f"[bold red]{yolo} YOLO[/] | {len(ALL_TOOLS)} total\n"
        )
        return

    query = args[0].lower()
    if query in ("safe", "read", "readonly"):
        filtered = [t for t in ALL_TOOLS if t.read_only]
    elif query in ("write",):
        filtered = [t for t in ALL_TOOLS if not t.read_only and not t.dangerous]
    elif query in ("yolo", "dangerous", "danger"):
        filtered = [t for t in ALL_TOOLS if t.dangerous]
    else:
        filtered = [t for t in ALL_TOOLS if query in t.name or query in t.description.lower()]

    if filtered:
        render_tools_table(app.console, filtered)
    else:
        app.console.print(f"[dim]No tools matching '{query}'.[/dim]")


@register("compact", "Compact conversation history to free context")
def cmd_compact(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    before = len(app.engine.messages)
    app.engine._compact_messages()
    after = len(app.engine.messages)
    removed = before - after
    if removed > 0:
        app.console.print(f"[success]Compacted: removed {removed} old messages ({before} -> {after})[/success]")
    else:
        app.console.print(f"[dim]Nothing to compact ({after} messages, within budget).[/dim]")


@register("export", "Export conversation to markdown file")
def cmd_export(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine or not app.engine.messages:
        app.console.print("[dim]Nothing to export.[/dim]")
        return
    md = app.engine.export_markdown()
    filename = args[0] if args else f"gemi_export_{int(__import__('time').time())}.md"
    fp = app.workspace / filename
    fp.write_text(md, encoding="utf-8")
    app.console.print(f"[success]Exported {len(app.engine.messages)} messages to {fp.name}[/success]")


@register("undo", "Remove the last user/assistant exchange")
def cmd_undo(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    if app.engine.undo():
        app.console.print(f"[success]Undone. {len(app.engine.messages)} messages remaining.[/success]")
    else:
        app.console.print("[dim]Nothing to undo.[/dim]")


@register("retry", "Retry the last message")
def cmd_retry(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine or not app.engine.messages:
        app.console.print("[dim]No messages to retry.[/dim]")
        return
    last_user = None
    for msg in reversed(app.engine.messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            last_user = msg["content"]
            break
    if not last_user:
        app.console.print("[dim]No user message to retry.[/dim]")
        return
    app.engine.undo()
    app.console.print(f"[dim]Retrying: {last_user[:80]}...[/dim]")
    from ..ui.render import render_assistant
    try:
        result = app.engine.query(last_user)
        render_assistant(app.console, result)
    except Exception as e:
        app.console.print(f"[error]Retry failed: {e}[/error]")


@register("config", "Show system configuration")
def cmd_config(app: "BuddyApp", args: list[str]) -> None:
    from ..tools.registry import ALL_TOOLS
    app.console.print(f"\n[command]Configuration:[/command]")
    app.console.print(f"  Version:      {__import__('gemi').__version__}")
    app.console.print(f"  Workspace:    {app.workspace}")
    app.console.print(f"  Tools:        {len(ALL_TOOLS)}")
    app.console.print(f"  Commands:     {len(COMMANDS)}")
    if app.engine:
        a = app.engine.agent
        app.console.print(f"  Agent:        {a.name} ({a.slug})")
        app.console.print(f"  Model:        {a.short_model} ({a.quant})")
        app.console.print(f"  Context:      {a.context:,} tokens")
        app.console.print(f"  Max tokens:   {app.engine.max_tokens:,}")
        app.console.print(f"  Temperature:  {app.engine.temperature}")
        app.console.print(f"  Messages:     {len(app.engine.messages)}")
    app.console.print(f"  YOLO:         {'ON' if app.yolo else 'OFF'}")
    app.console.print(f"  Plan:         {'ON' if app.plan_mode else 'OFF'}")
    app.console.print(f"  Autopilot:    {'ON' if app.autopilot else 'OFF'}")
    app.console.print()


@register("history", "Show conversation history summary")
def cmd_history(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine or not app.engine.messages:
        app.console.print("[dim]No conversation history.[/dim]")
        return
    app.console.print(f"\n[command]Conversation History ({app.engine.turn_count} turns):[/command]")
    turn = 0
    for msg in app.engine.messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if role == "user" and isinstance(content, str):
            turn += 1
            preview = content[:100].replace("\n", " ")
            app.console.print(f"  [bold]{turn:3d}.[/bold] [user.prompt]{preview}{'...' if len(content) > 100 else ''}[/user.prompt]")
        elif role == "assistant" and isinstance(content, list):
            tool_count = sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use")
            text_len = sum(len(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text")
            parts = []
            if text_len:
                parts.append(f"{text_len} chars")
            if tool_count:
                parts.append(f"{tool_count} tools")
            app.console.print(f"       [dim]-> {', '.join(parts) if parts else '(empty)'}[/dim]")
    app.console.print()


@register("search", "Search conversation history for a keyword")
def cmd_search(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine or not app.engine.messages:
        app.console.print("[dim]No conversation history to search.[/dim]")
        return
    if not args:
        app.console.print("[dim]Usage: /search <keyword>[/dim]")
        return
    query = " ".join(args).lower()
    hits = []
    for i, msg in enumerate(app.engine.messages):
        content = msg.get("content", "")
        role = msg.get("role", "?")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "") + b.get("content", "")
                for b in content if isinstance(b, dict)
            )
        else:
            continue
        if query in text.lower():
            preview = text[:120].replace("\n", " ")
            hits.append((i, role, preview))

    if hits:
        app.console.print(f"\n[command]Search results for '{query}' ({len(hits)} hits):[/command]")
        for idx, role, preview in hits[:20]:
            tag = "[bold]user[/]" if role == "user" else "[dim]asst[/]"
            app.console.print(f"  msg {idx:3d} {tag}  {preview}{'...' if len(preview) >= 120 else ''}")
        if len(hits) > 20:
            app.console.print(f"  [dim]... {len(hits) - 20} more matches[/dim]")
    else:
        app.console.print(f"[dim]No matches for '{query}'.[/dim]")
    app.console.print()


@register("temp", "Show or set temperature (0.0-1.0)")
def cmd_temp(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    if args:
        try:
            val = float(args[0])
            if not 0.0 <= val <= 1.0:
                app.console.print("[error]Temperature must be 0.0-1.0[/error]")
                return
            app.engine.temperature = val
            app.console.print(f"[success]Temperature set to {val}[/success]")
        except ValueError:
            app.console.print("[error]Invalid number. Usage: /temp 0.5[/error]")
    else:
        app.console.print(f"  Temperature: {app.engine.temperature}")
        app.console.print(f"  [dim]Usage: /temp <0.0-1.0> — lower = more deterministic[/dim]")


@register("tokens", "Show or set max output tokens")
def cmd_tokens(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    if args:
        try:
            val = int(args[0])
            if val < 64:
                app.console.print("[error]Minimum 64 tokens[/error]")
                return
            ceiling = app.engine.agent.context // 2
            if val > ceiling:
                app.console.print(f"[warning]Capped to {ceiling} (half of {app.engine.agent.context} context)[/warning]")
                val = ceiling
            app.engine.max_tokens = val
            app.console.print(f"[success]Max output tokens set to {val:,}[/success]")
        except ValueError:
            app.console.print("[error]Invalid number. Usage: /tokens 4096[/error]")
    else:
        app.console.print(f"  Max output tokens: {app.engine.max_tokens:,}")
        app.console.print(f"  Context budget:    {app.engine.agent.context:,}")
        app.console.print(f"  [dim]Usage: /tokens <number>[/dim]")


@register("git", "Show git status for the workspace")
def cmd_git(app: "BuddyApp", args: list[str]) -> None:
    import subprocess
    ws = str(app.workspace)

    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ws, capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        app.console.print("[error]git not found on PATH[/error]")
        return
    except Exception as e:
        app.console.print(f"[error]git error: {e}[/error]")
        return

    if branch.returncode != 0:
        app.console.print(f"[dim]Not a git repository: {app.workspace}[/dim]")
        return

    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=ws, capture_output=True, text=True, timeout=5,
    )
    log = subprocess.run(
        ["git", "log", "--oneline", "-5"],
        cwd=ws, capture_output=True, text=True, timeout=5,
    )

    app.console.print(f"\n[command]Git — {app.workspace}[/command]")
    app.console.print(f"  Branch: [bold bright_magenta]{branch.stdout.strip()}[/bold bright_magenta]")

    lines = status.stdout.strip().splitlines() if status.stdout.strip() else []
    if lines:
        app.console.print(f"  Status: [yellow]{len(lines)} changed file{'s' if len(lines) != 1 else ''}[/yellow]")
        for line in lines[:10]:
            app.console.print(f"    [dim]{line}[/dim]")
        if len(lines) > 10:
            app.console.print(f"    [dim]... {len(lines) - 10} more[/dim]")
    else:
        app.console.print(f"  Status: [green]clean[/green]")

    if log.stdout.strip():
        app.console.print(f"  Recent commits:")
        for line in log.stdout.strip().splitlines():
            app.console.print(f"    [dim]{line}[/dim]")
    app.console.print()


@register("ping", "Test agent connectivity and response time")
def cmd_ping(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No agent selected.[/dim]")
        return
    import time
    agent = app.engine.agent
    app.console.print(f"  Pinging {agent.name} at {agent.proxy_url}...")
    t0 = time.time()
    try:
        from ..provider import ping_agent
        ok = ping_agent(agent, timeout=10)
        elapsed = time.time() - t0
        if ok:
            app.console.print(f"  [success]OK[/success] — {elapsed:.1f}s response time")
        else:
            app.console.print(f"  [error]FAILED[/error] — agent returned non-200 after {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - t0
        app.console.print(f"  [error]FAILED[/error] — {e} ({elapsed:.1f}s)")


@register("template", "Show Qwen 3.6 chat template status for current agent")
def cmd_template(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No agent selected.[/dim]")
        return
    agent = app.engine.agent
    app.console.print(f"\n[command]Chat Template — {agent.name}:[/command]")
    app.console.print(f"  Model:     {agent.short_model}")
    app.console.print(f"  Qwen 3.6:  {'yes' if agent.is_qwen36 else 'no'}")

    if not agent.is_qwen36:
        app.console.print(f"  [dim]Not a Qwen 3.6 model — template fix not needed.[/dim]")
        app.console.print()
        return

    if agent.needs_template_fix:
        tp = agent.template_path
        if tp and tp.exists():
            app.console.print(f"  Fix:       [success]applied[/success]")
            app.console.print(f"  Path:      [dim]{tp}[/dim]")
        else:
            app.console.print(f"  Fix:       [error]configured but file missing[/error]")
    else:
        app.console.print(f"  Fix:       [warning]NOT applied[/warning]")
        app.console.print(f"  [dim]Tool calls may use broken XML format.[/dim]")
        app.console.print(f"  [dim]Buddy has fallback parsing, but applying the template is recommended.[/dim]")

    app.console.print(f"\n  [bold]To apply the fix to llama-server:[/bold]")
    from ..templates import QWEN36_TOOL_FIX
    app.console.print(f"  llama-server ... --chat-template-file \"{QWEN36_TOOL_FIX}\"")
    app.console.print(f"\n  [dim]The patched template converts tool calls from broken XML to standard JSON format.[/dim]")
    app.console.print(f"  [dim]Source: github.com/abysslover/qwen36_tool_calling_failure[/dim]")
    app.console.print()


@register("context", "Show context window usage breakdown")
def cmd_context(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    from ..query_engine import _estimate_tokens
    est = _estimate_tokens(app.engine.messages, app.engine.system_prompt)
    budget = app.engine.agent.context
    used_pct = (est / budget * 100) if budget else 0
    sys_tokens = len(app.engine.system_prompt) // 4

    user_msgs = sum(1 for m in app.engine.messages if m.get("role") == "user")
    asst_msgs = sum(1 for m in app.engine.messages if m.get("role") == "assistant")
    tool_blocks = 0
    for m in app.engine.messages:
        content = m.get("content", [])
        if isinstance(content, list):
            tool_blocks += sum(1 for b in content if isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result"))

    bar_width = 30
    filled = int(bar_width * min(used_pct, 100) / 100)
    bar_color = "green" if used_pct < 50 else "yellow" if used_pct < 75 else "bold red"
    bar = f"[{bar_color}]{'█' * filled}{'░' * (bar_width - filled)}[/{bar_color}]"

    app.console.print(f"\n[command]Context Budget:[/command]")
    app.console.print(f"  {bar} {est:,} / {budget:,} tokens ({used_pct:.0f}%)")
    app.console.print(f"\n  System prompt:  ~{sys_tokens:,} tokens")
    app.console.print(f"  Messages:       {len(app.engine.messages)} ({user_msgs} user, {asst_msgs} assistant)")
    app.console.print(f"  Tool blocks:    {tool_blocks}")
    app.console.print(f"  Turns:          {app.engine.turn_count}")
    app.console.print(f"  Max output:     {app.engine.max_tokens:,}")

    remaining = budget - est - app.engine.max_tokens
    if remaining < 0:
        app.console.print(f"\n  [bold red]WARNING: over budget by ~{-remaining:,} tokens. Use /compact or /clear.[/bold red]")
    elif remaining < budget * 0.15:
        app.console.print(f"\n  [yellow]Low headroom: ~{remaining:,} tokens remaining. Consider /compact.[/yellow]")
    else:
        app.console.print(f"\n  [dim]Headroom: ~{remaining:,} tokens[/dim]")
    app.console.print()


@register("stats", "Show session statistics and per-tool breakdown")
def cmd_stats(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    s = app.engine.get_stats()
    app.console.print(f"\n[command]Session Statistics:[/command]")
    app.console.print(f"  Turns:          {s['turns']}")
    app.console.print(f"  Total time:     {s['total_elapsed']:.1f}s")
    app.console.print(f"  Input tokens:   {s['input_tokens']:,}")
    app.console.print(f"  Output tokens:  {s['output_tokens']:,}")
    app.console.print(f"  Total tokens:   {s['total_tokens']:,}")
    app.console.print(f"  Tool calls:     {s['total_tool_calls']} ({s['total_tool_errors']} errors)")
    app.console.print(f"  Tool time:      {s['total_tool_time']:.1f}s")

    if s["tool_stats"]:
        app.console.print(f"\n  [bold]Per-Tool Breakdown:[/bold]")
        sorted_tools = sorted(s["tool_stats"].items(), key=lambda x: x[1]["calls"], reverse=True)
        for name, ts in sorted_tools:
            err_tag = f" [bold red]{ts['errors']}err[/]" if ts["errors"] else ""
            app.console.print(
                f"    [tool.name]{name:20}[/tool.name] "
                f"{ts['calls']:3d} calls  {ts['time']:.1f}s{err_tag}"
            )
    app.console.print()


@register("launch", "Start an agent's llama-server and proxy")
def cmd_launch(app: "BuddyApp", args: list[str]) -> None:
    import subprocess
    if not args:
        if app.engine:
            slug = app.engine.agent.slug
        else:
            app.console.print("[dim]Usage: /launch <agent-slug>[/dim]")
            return
    else:
        slug = args[0]
    from ..config import get_agent, FLEET
    agent = get_agent(slug)
    if not agent:
        slug_lower = slug.lower()
        for a in FLEET:
            if a.slug.endswith(slug_lower) or slug_lower in a.slug:
                agent = a
                break
    if not agent:
        app.console.print(f"[error]Agent not found: {slug}[/error]")
        return
    if agent.is_proxy_running():
        app.console.print(f"[success]{agent.name} is already running.[/success]")
        return
    app.console.print(f"  Starting {agent.name} ({agent.slug})...")
    launcher_dir = agent.path / "launcher"
    launcher = launcher_dir / "start.ps1"
    if not launcher.exists():
        app.console.print(f"[error]No launcher found at {launcher}[/error]")
        return
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(launcher), "-Proxy"],
            cwd=str(launcher_dir.parent),
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            app.console.print(f"[success]{agent.name} started.[/success]")
            if result.stdout.strip():
                for line in result.stdout.strip().splitlines()[-5:]:
                    app.console.print(f"  [dim]{line}[/dim]")
        else:
            app.console.print(f"[error]Launch failed (exit {result.returncode})[/error]")
            if result.stderr.strip():
                for line in result.stderr.strip().splitlines()[-3:]:
                    app.console.print(f"  [dim]{line}[/dim]")
    except subprocess.TimeoutExpired:
        app.console.print(f"[warning]Launch timed out after 60s — agent may still be starting.[/warning]")
    except Exception as e:
        app.console.print(f"[error]Launch error: {e}[/error]")


@register("rename", "Rename current or saved session")
def cmd_rename(app: "BuddyApp", args: list[str]) -> None:
    from ..session import rename_session
    if not args:
        app.console.print("[dim]Usage: /rename <new title> or /rename <session-id> <new title>[/dim]")
        return
    if len(args) >= 2 and not args[0].startswith('"'):
        from ..session import load_session
        maybe_session = load_session(args[0])
        if maybe_session:
            title = " ".join(args[1:])
            if rename_session(args[0], title):
                app.console.print(f"[success]Renamed to: {title}[/success]")
            else:
                app.console.print(f"[error]Rename failed.[/error]")
            return
    title = " ".join(args)
    if app.session_id:
        if rename_session(app.session_id, title):
            app.console.print(f"[success]Session renamed: {title}[/success]")
        else:
            app.console.print(f"[error]Save the session first (/save), then rename.[/error]")
    else:
        path = app.save_current_session()
        if path:
            rename_session(path.stem, title)
            app.console.print(f"[success]Saved and renamed: {title}[/success]")
        else:
            app.console.print("[dim]Nothing to save/rename.[/dim]")


@register("fork", "Fork conversation at current point")
def cmd_fork(app: "BuddyApp", args: list[str]) -> None:
    from ..session import fork_session
    if not app.engine or not app.engine.messages:
        app.console.print("[dim]No conversation to fork.[/dim]")
        return
    path = fork_session(
        session_id=app.session_id or "unsaved",
        messages=app.engine.messages,
        agent_slug=app.engine.agent.slug,
        workspace=str(app.workspace),
    )
    app.console.print(f"[success]Forked to: {path.stem}[/success]")
    app.console.print(f"[dim]Resume the fork with: /resume {path.stem}[/dim]")


@register("diff", "Show git diff for the workspace")
def cmd_diff(app: "BuddyApp", args: list[str]) -> None:
    import subprocess
    ws = str(app.workspace)
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ws, capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        app.console.print("[error]git not found on PATH[/error]")
        return
    if branch.returncode != 0:
        app.console.print(f"[dim]Not a git repository: {app.workspace}[/dim]")
        return
    diff_args = ["git", "diff"]
    if args:
        if args[0] == "staged":
            diff_args.append("--cached")
        elif args[0] == "stat":
            diff_args.append("--stat")
        else:
            diff_args.extend(args)
    result = subprocess.run(
        diff_args, cwd=ws, capture_output=True, text=True, timeout=15,
    )
    output = result.stdout.strip()
    if not output:
        app.console.print("[dim]No changes.[/dim]")
        return
    lines = output.splitlines()
    app.console.print(f"\n[command]Diff — {len(lines)} lines:[/command]")
    shown = 0
    max_show = 60
    for line in lines:
        if shown >= max_show:
            app.console.print(f"  [dim]... ({len(lines) - max_show} more lines)[/dim]")
            break
        if line.startswith("+") and not line.startswith("+++"):
            app.console.print(f"  [bold green]{line}[/bold green]")
        elif line.startswith("-") and not line.startswith("---"):
            app.console.print(f"  [bold red]{line}[/bold red]")
        elif line.startswith("@@"):
            app.console.print(f"  [bold cyan]{line}[/bold cyan]")
        elif line.startswith("diff "):
            app.console.print(f"  [bold white]{line}[/bold white]")
        else:
            app.console.print(f"  [dim]{line}[/dim]")
        shown += 1
    app.console.print()


@register("fleet", "Show detailed fleet status with template info")
def cmd_fleet(app: "BuddyApp", args: list[str]) -> None:
    from ..config import FLEET
    from rich.table import Table
    table = Table(title="Fleet Status", border_style="bright_magenta", show_lines=False)
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column("Agent", style="cyan")
    table.add_column("Quant", style="white")
    table.add_column("Ctx", style="dim", justify="right")
    table.add_column("P", style="dim", justify="right")
    table.add_column("Template", style="dim")
    table.add_column("Model", style="dim")
    table.add_column("Proxy", style="dim")

    for i, a in enumerate(FLEET, 1):
        model_up = a.is_model_running()
        proxy_up = a.is_proxy_running()
        model_st = "[bold green]UP[/]" if model_up else "[dim red]--[/]"
        proxy_st = "[bold green]UP[/]" if proxy_up else "[dim red]--[/]"
        if a.is_qwen36 and a.needs_template_fix:
            tp = a.template_path
            tpl = "[green]fixed[/]" if tp and tp.exists() else "[red]missing[/]"
        elif a.is_qwen36:
            tpl = "[yellow]default[/]"
        else:
            tpl = "[dim]n/a[/]"
        active = ""
        if app.engine and app.engine.agent.slug == a.slug:
            active = " [bold white]*[/]"
        table.add_row(
            str(i), f"{a.slug}{active}", a.quant or "?",
            f"{a.context:,}", str(a.parallel), tpl, model_st, proxy_st,
        )
    app.console.print()
    app.console.print(table)
    qwen_count = sum(1 for a in FLEET if a.is_qwen36)
    fixed_count = sum(1 for a in FLEET if a.is_qwen36 and a.needs_template_fix)
    app.console.print(f"\n  [dim]{qwen_count} Qwen 3.6 agents, {fixed_count} with template fix configured[/dim]")
    app.console.print(f"  [dim]Use /launch <slug> to start an agent[/dim]\n")


@register("rewind", "Rewind conversation to turn N (drops everything after)")
def cmd_rewind(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    if not args:
        app.console.print("[dim]Usage: /rewind <turn-number>[/dim]")
        app.console.print(f"[dim]Current turn: {app.engine.turn_count}. Use /timeline to see turns.[/dim]")
        return
    try:
        target = int(args[0])
    except ValueError:
        app.console.print("[error]Invalid turn number.[/error]")
        return
    if app.engine.rewind_to(target):
        app.console.print(
            f"[success]Rewound to turn {target}. {len(app.engine.messages)} messages remain.[/success]"
        )
    else:
        app.console.print(f"[error]Turn {target} not found in snapshots.[/error]")


@register("timeline", "Show conversation timeline with turn anchors")
def cmd_timeline(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    if not app.engine.snapshots:
        app.console.print("[dim]No snapshots yet — submit a message first.[/dim]")
        return
    import time
    app.console.print(f"\n[command]Timeline ({len(app.engine.snapshots)} turns):[/command]")
    now = time.time()
    for s in app.engine.snapshots:
        age = now - s.timestamp
        if age < 60:
            age_str = f"{int(age)}s ago"
        elif age < 3600:
            age_str = f"{int(age/60)}m ago"
        else:
            age_str = f"{int(age/3600)}h ago"
        marker = "[bold cyan]*[/]" if s.turn == app.engine.turn_count else " "
        app.console.print(
            f"  {marker} t{s.turn:>3}  [dim]{age_str:>10}[/dim]  "
            f"[user.prompt]{s.user_preview[:80]}[/user.prompt]"
        )
    app.console.print(f"\n[dim]Use /rewind <n> to jump back. /undo to remove the last turn.[/dim]\n")


@register("vote", "Run a prompt against all running agents in parallel and compare")
def cmd_vote(app: "BuddyApp", args: list[str]) -> None:
    if not args:
        app.console.print("[dim]Usage: /vote <prompt>[/dim]")
        return
    from ..orchestration import vote
    from ..config import FLEET
    prompt = " ".join(args)
    running = [a for a in FLEET if a.is_proxy_running()]
    if not running:
        app.console.print("[error]No agents running. Use /launch to start one.[/error]")
        return
    app.console.print(f"  Running prompt across {len(running)} agents in parallel...")
    results = vote(prompt=prompt, max_tokens=1024, timeout=120)
    if not results:
        app.console.print("[error]No responses received.[/error]")
        return
    app.console.print(f"\n[command]Vote results ({len(results)} responses):[/command]\n")
    for r in sorted(results, key=lambda x: x.elapsed):
        if r.error:
            app.console.print(f"[error]✗ {r.agent}[/error] [dim]{r.error[:80]}[/dim]")
            continue
        header = f"[agent.name]{r.agent}[/agent.name] [dim]({r.quant}, {r.elapsed:.1f}s, {r.usage.input_tokens}/{r.usage.output_tokens} tok)[/dim]"
        app.console.print(f"  {header}")
        for line in r.text.strip().splitlines()[:15]:
            app.console.print(f"    [dim]{line}[/dim]")
        if len(r.text.splitlines()) > 15:
            app.console.print(f"    [dim]... ({len(r.text.splitlines()) - 15} more lines)[/dim]")
        app.console.print()


@register("race", "First-to-finish wins; cancel the rest")
def cmd_race(app: "BuddyApp", args: list[str]) -> None:
    if not args:
        app.console.print("[dim]Usage: /race <prompt>[/dim]")
        return
    from ..orchestration import race
    prompt = " ".join(args)
    app.console.print(f"  Racing all running agents...")
    winner, completed = race(prompt=prompt, max_tokens=1024, timeout=120)
    if not winner:
        app.console.print("[error]No agent won (all errored or timed out).[/error]")
        if completed:
            app.console.print(f"[dim]{len(completed)} agents completed/errored:[/dim]")
            for r in completed:
                app.console.print(f"  [dim]{r.agent}: {r.error or 'no text'}[/dim]")
        return
    app.console.print(f"\n[success]Winner: {winner.agent} ({winner.quant}) in {winner.elapsed:.1f}s[/success]\n")
    app.console.print(winner.text)
    app.console.print()


@register("delegate", "Send a one-shot prompt to a specific agent: /delegate <slug> <prompt>")
def cmd_delegate(app: "BuddyApp", args: list[str]) -> None:
    if len(args) < 2:
        app.console.print("[dim]Usage: /delegate <agent-slug> <prompt>[/dim]")
        return
    from ..orchestration import delegate
    slug = args[0]
    prompt = " ".join(args[1:])
    app.console.print(f"  Delegating to {slug}...")
    result = delegate(target_slug=slug, prompt=prompt, max_tokens=2048, timeout=180)
    if not result.succeeded:
        app.console.print(f"[error]Delegation failed: {result.error}[/error]")
        return
    app.console.print(
        f"\n[success]✓ {result.agent}[/success] [dim]({result.quant}, "
        f"{result.elapsed:.1f}s, {result.usage.input_tokens}/{result.usage.output_tokens} tok)[/dim]\n"
    )
    app.console.print(result.text)
    app.console.print()


@register("hooks", "List or reload hooks from ~/.gemi/hooks.json")
def cmd_hooks(app: "BuddyApp", args: list[str]) -> None:
    from ..hooks import list_hooks, list_log, initialize, HOOKS_FILE
    if args and args[0] in ("reload", "load"):
        n = initialize()
        app.console.print(f"[success]Reloaded {n} hook(s) from {HOOKS_FILE}[/success]")
        return
    if args and args[0] == "log":
        log = list_log(20)
        if not log:
            app.console.print("[dim]No hook events logged.[/dim]")
            return
        app.console.print(f"\n[command]Recent hook events ({len(log)}):[/command]")
        for e in log[-20:]:
            allow = "[green]ALLOW[/]" if e["allow"] else "[bold red]BLOCK[/]"
            app.console.print(
                f"  {allow} {e['event']:14} {e['tool'] or '-':14} "
                f"[dim]{e['matcher']:12} {e['elapsed']*1000:.0f}ms[/dim]"
            )
            if e["message"]:
                app.console.print(f"        [dim]{e['message'][:100]}[/dim]")
        return
    hooks = list_hooks()
    if not hooks:
        app.console.print(f"[dim]No hooks loaded. Configure in {HOOKS_FILE}[/dim]")
        app.console.print("[dim]Schema: [{event, matcher, command, timeout, block_on_failure, description}][/dim]")
        return
    app.console.print(f"\n[command]Active hooks ({len(hooks)}):[/command]")
    for h in hooks:
        block = " [bold red]BLOCKING[/]" if h.block_on_failure else ""
        app.console.print(
            f"  [bold]{h.event:18}[/bold] [dim]matcher=[/dim]{h.matcher:20} "
            f"[dim]timeout={h.timeout}s{block}[/dim]"
        )
        if h.description:
            app.console.print(f"      [dim]{h.description}[/dim]")
        if h.command:
            app.console.print(f"      [dim cyan]$ {h.command[:80]}[/dim cyan]")
    app.console.print(f"\n[dim]Use /hooks reload to re-read {HOOKS_FILE.name}. /hooks log to see firings.[/dim]\n")


@register("perms", "Show permission rules (allow/deny lists)")
def cmd_perms(app: "BuddyApp", args: list[str]) -> None:
    from ..permissions import get_permissions, PERMS_FILE
    if args and args[0] == "reload":
        get_permissions(reload=True)
        app.console.print(f"[success]Permissions reloaded from {PERMS_FILE}[/success]")
        return
    perms = get_permissions()
    app.console.print(f"\n[command]Permission rules:[/command]")
    app.console.print(f"  File: [dim]{PERMS_FILE}[/dim]")
    if perms.allow:
        app.console.print(f"\n  [bold green]ALLOW ({len(perms.allow)}):[/bold green]")
        for r in perms.allow:
            app.console.print(f"    {r.tool:18} [dim]{r.pattern}[/dim]")
            if r.description:
                app.console.print(f"      [dim]{r.description}[/dim]")
    if perms.deny:
        app.console.print(f"\n  [bold red]DENY ({len(perms.deny)}):[/bold red]")
        for r in perms.deny:
            app.console.print(f"    {r.tool:18} [dim]{r.pattern}[/dim]")
            if r.description:
                app.console.print(f"      [dim]{r.description}[/dim]")
    if not perms.allow and not perms.deny:
        app.console.print(f"  [dim]No custom rules. Default safety denies are still active.[/dim]")
    app.console.print()


@register("cache", "Show or clear tool result cache stats")
def cmd_cache(app: "BuddyApp", args: list[str]) -> None:
    if not app.engine:
        app.console.print("[dim]No session active.[/dim]")
        return
    cache = app.engine._cache
    if args and args[0] in ("clear", "flush"):
        n = cache.clear()
        app.console.print(f"[success]Cleared {n} cache entries.[/success]")
        return
    if args and args[0] in ("off", "disable"):
        cache.enabled = False
        app.console.print("[warning]Tool cache disabled.[/warning]")
        return
    if args and args[0] in ("on", "enable"):
        cache.enabled = True
        app.console.print("[success]Tool cache enabled.[/success]")
        return
    s = cache.stats
    app.console.print(f"\n[command]Tool result cache:[/command]")
    app.console.print(f"  Enabled:        {'yes' if cache.enabled else 'no'}")
    app.console.print(f"  Entries:        {len(cache)}/{cache.max_entries}")
    app.console.print(f"  TTL:            {cache.ttl}s")
    app.console.print(f"  Hits:           {s.hits}")
    app.console.print(f"  Misses:         {s.misses}")
    app.console.print(f"  Hit rate:       {s.hit_rate:.1f}%")
    app.console.print(f"  Bytes served:   {s.bytes_served:,}")
    app.console.print(f"  Invalidations:  {s.invalidations}")
    app.console.print(f"\n[dim]/cache clear | /cache off | /cache on[/dim]\n")


@register("workspace_context", "Show or reload BUDDY.md/CLAUDE.md/AGENTS.md context files")
def cmd_workspace_context(app: "BuddyApp", args: list[str]) -> None:
    from ..workspace_context import summarize_context
    if args and args[0] in ("reload", "refresh"):
        n = app.reload_workspace_context()
        app.console.print(f"[success]Reloaded {n} context file(s).[/success]")
        return
    ctx = app.workspace_ctx
    app.console.print(f"\n[command]Workspace context — {app.workspace}:[/command]")
    app.console.print(f"  Git root:  [dim]{ctx.git_root or '(none)'}[/dim]")
    app.console.print(f"  Files:     {len(ctx.files)}")
    app.console.print(f"  Total:     {ctx.total_chars:,} chars")
    if ctx.files:
        app.console.print()
        for f in ctx.files:
            trunc = " [yellow][truncated][/yellow]" if f.is_truncated else ""
            app.console.print(f"    [bold]{f.relative}[/bold]  [dim]{len(f.content):,} chars[/dim]{trunc}")
            app.console.print(f"      [dim]{f.path}[/dim]")
    else:
        app.console.print(f"\n  [dim]No context files found. Drop a BUDDY.md or CLAUDE.md in the workspace.[/dim]")
    app.console.print(f"\n[dim]/workspace_context reload to re-read from disk.[/dim]\n")


@register("spend", "Show kWh/USD breakdown across this session, today, and lifetime")
def cmd_spend(app: "BuddyApp", args: list[str]) -> None:
    from ..cost import get_tracker
    import time
    tracker = get_tracker()
    persisted = tracker.get_lifetime()

    app.console.print(f"\n[command]Energy & cost estimate:[/command]")
    app.console.print(f"  GPU watts:      {tracker.config.gpu_watts:.0f}W")
    app.console.print(f"  Rate:           ${tracker.config.rate_usd_per_kwh:.3f}/kWh")

    sess = tracker.session
    if sess.turns:
        app.console.print(f"\n  [bold]This session:[/bold]")
        app.console.print(f"    Turns:        {sess.turns}")
        app.console.print(f"    Inference:    {sess.total_seconds:.1f}s")
        app.console.print(f"    Energy:       {sess.total_kwh*1000:.2f} Wh")
        app.console.print(f"    Estimate:     ${sess.total_usd:.4f}")

    today = time.strftime("%Y-%m-%d")
    day = persisted["daily"].get(today, {})
    if day:
        app.console.print(f"\n  [bold]Today ({today}):[/bold]")
        app.console.print(f"    Turns:        {day['turns']}")
        app.console.print(f"    Energy:       {day['kwh']*1000:.2f} Wh")
        app.console.print(f"    Estimate:     ${day['usd']:.4f}")

    by_agent = persisted.get("by_agent", {})
    if by_agent:
        app.console.print(f"\n  [bold]By agent (lifetime):[/bold]")
        for slug, stats in sorted(by_agent.items(), key=lambda x: x[1]["usd"], reverse=True)[:6]:
            app.console.print(
                f"    [agent.name]{slug:20}[/agent.name] "
                f"{stats['turns']:>4}t  {stats['kwh']*1000:>6.1f} Wh  ${stats['usd']:.4f}"
            )

    lifetime = persisted.get("lifetime", {})
    if lifetime.get("turns"):
        app.console.print(f"\n  [bold]Lifetime:[/bold]")
        app.console.print(f"    Turns:        {lifetime['turns']}")
        app.console.print(f"    Energy:       {lifetime['kwh']:.4f} kWh")
        app.console.print(f"    Estimate:     ${lifetime['usd']:.4f}")
    app.console.print()


@register("theme", "Show or switch color theme")
def cmd_theme(app: "BuddyApp", args: list[str]) -> None:
    from ..ui.theme import (
        list_themes, get_active_theme_name, set_active_theme,
        reload_theme, get_palette,
    )
    palette = get_palette(get_active_theme_name())
    themes = list_themes()
    current = get_active_theme_name()

    if not args:
        app.console.print()
        app.console.print(f"  [bold {palette.buddy}]✻ themes[/]")
        app.console.print()
        for t in themes:
            marker = f"[bold {palette.success}]●[/]" if t == current else f"[dim {palette.text_subtle}]○[/]"
            label_style = f"bold {palette.buddy_shimmer}" if t == current else palette.text_muted
            app.console.print(f"      {marker}  [bold {label_style}]{t}[/]")
        app.console.print()
        app.console.print(
            f"  [muted]usage:[/]  [bold {palette.buddy_shimmer}]/theme <name>[/]  "
            f"[muted]to switch and persist[/]"
        )
        app.console.print()
        return

    target = args[0].lower()
    if target not in themes:
        app.console.print(f"  [bold {palette.error}]✗[/]  unknown theme: [bold]{target}[/]")
        app.console.print(f"  [muted]available:[/]  {', '.join(themes)}")
        return

    if not set_active_theme(target):
        app.console.print(f"  [bold {palette.error}]✗[/]  failed to save theme")
        return

    new_theme = reload_theme()
    # Rebuild console with new theme
    from rich.console import Console as _Console
    app.console = _Console(theme=new_theme)
    new_palette = get_palette(target)
    app.console.print()
    app.console.print(
        f"  [bold {new_palette.buddy}]✻[/]  theme changed to "
        f"[bold {new_palette.buddy_shimmer}]{target}[/]  "
        f"[muted]· persisted to ~/.gemi/config.json[/]"
    )
    app.console.print()


@register("welcome", "Show the welcome splash screen")
def cmd_welcome(app: "BuddyApp", args: list[str]) -> None:
    from ..ui.welcome import print_welcome
    print_welcome(app.console)


# ----- shell shortcuts (run directly, no agent) ---------------------

@register("sh", "Run a bash command directly: /sh ls -la")
def cmd_sh(app: "BuddyApp", args: list[str]) -> None:
    if not args:
        app.console.print("[dim]usage: /sh <command>  or just  ! <command>[/]")
        return
    command = " ".join(args)
    app._run_quick_shell(command)


@register("ps", "Run a PowerShell command directly: /ps Get-Process")
def cmd_ps(app: "BuddyApp", args: list[str]) -> None:
    if not args:
        app.console.print("[dim]usage: /ps <powershell command>[/]")
        return
    from ..tools.registry import get_tool
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    command = " ".join(args)
    tool = get_tool("powershell")
    result = tool.execute(app.workspace, command=command, timeout=60)
    prefix = f"  [bold {palette.buddy}]PS>[/]"
    if result.is_error:
        app.console.print(f"\n{prefix} [bold]{command}[/]")
        for line in (result.error or "").splitlines()[:20]:
            app.console.print(f"      [dim]{line}[/]")
    else:
        app.console.print(f"\n{prefix} [bold]{command}[/]")
        for line in result.output.splitlines()[:30]:
            app.console.print(f"      [muted]{line}[/]")
    app.console.print()


@register("cmd", "Run a Windows cmd.exe command directly")
def cmd_cmd(app: "BuddyApp", args: list[str]) -> None:
    if not args:
        app.console.print("[dim]usage: /cmd <cmd command>[/]")
        return
    from ..tools.registry import get_tool
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    command = " ".join(args)
    tool = get_tool("cmd")
    result = tool.execute(app.workspace, command=command, timeout=60)
    prefix = f"  [bold {palette.buddy}]C:>[/]"
    if result.is_error:
        app.console.print(f"\n{prefix} [bold]{command}[/]")
        for line in (result.error or "").splitlines()[:20]:
            app.console.print(f"      [dim]{line}[/]")
    else:
        app.console.print(f"\n{prefix} [bold]{command}[/]")
        for line in result.output.splitlines()[:30]:
            app.console.print(f"      [muted]{line}[/]")
    app.console.print()


@register("ls", "List workspace files (quick directory listing)")
def cmd_ls_quick(app: "BuddyApp", args: list[str]) -> None:
    from pathlib import Path
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    target = Path(args[0]) if args else app.workspace
    if not target.is_absolute():
        target = app.workspace / target
    if not target.is_dir():
        app.console.print(f"  [bold {palette.error}]✗[/]  not a directory: {target}")
        return
    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except Exception as e:
        app.console.print(f"  [bold {palette.error}]✗[/]  {e}")
        return
    app.console.print()
    app.console.print(f"  [bold {palette.info}]📂 {target}[/]")
    app.console.print()
    dirs = [e for e in entries if e.is_dir()]
    files = [e for e in entries if not e.is_dir()]
    for d in dirs[:50]:
        app.console.print(f"      [bold {palette.buddy_shimmer}]/{d.name}[/]")
    for f in files[:80]:
        try:
            sz = f.stat().st_size
            sz_str = f"{sz}B" if sz < 1024 else f"{sz//1024}KB" if sz < 1048576 else f"{sz//1048576}MB"
        except Exception:
            sz_str = "?"
        app.console.print(f"      [muted]{f.name:<40} {sz_str:>8}[/]")
    if len(dirs) > 50 or len(files) > 80:
        app.console.print(f"      [dim]… {(len(dirs)-50) + (len(files)-80)} more entries[/]")
    app.console.print()


@register("cat", "Print a file's contents directly (quick view)")
def cmd_cat_quick(app: "BuddyApp", args: list[str]) -> None:
    from pathlib import Path
    from rich.syntax import Syntax
    from rich.panel import Panel
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    if not args:
        app.console.print("[dim]usage: /cat <path>[/]")
        return
    target = Path(args[0])
    if not target.is_absolute():
        target = app.workspace / target
    if not target.is_file():
        app.console.print(f"  [bold {palette.error}]✗[/]  not a file: {target}")
        return
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        app.console.print(f"  [bold {palette.error}]✗[/]  {e}")
        return
    # Lang detection
    suffix = target.suffix.lower()
    lang = {".py": "python", ".js": "javascript", ".ts": "typescript",
            ".rs": "rust", ".go": "go", ".sh": "bash", ".ps1": "powershell",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml",
            ".toml": "toml", ".xml": "xml", ".html": "html", ".css": "css",
            ".md": "markdown"}.get(suffix)
    app.console.print()
    app.console.print(f"  [bold {palette.info}]📄 {target}[/]  [muted]({len(content):,} chars)[/]")
    if lang and len(content) < 50000:
        try:
            from rich.padding import Padding
            syntax = Syntax(content[:50000], lang, theme="monokai",
                            line_numbers=True, indent_guides=True)
            app.console.print(Padding(Panel(syntax, border_style=palette.border, expand=False),
                                       (0, 2)))
            return
        except Exception:
            pass
    for i, line in enumerate(content.splitlines()[:100], 1):
        app.console.print(f"      [dim]{i:>4}[/]  {line}")
    if len(content.splitlines()) > 100:
        app.console.print(f"      [dim]… ({len(content.splitlines()) - 100} more lines)[/]")
    app.console.print()


@register("pwd", "Print working directory")
def cmd_pwd(app: "BuddyApp", args: list[str]) -> None:
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    app.console.print(f"\n  [bold {palette.info}]📂 {app.workspace}[/]\n")


@register("cd", "Change workspace directory: /cd <path>")
def cmd_cd(app: "BuddyApp", args: list[str]) -> None:
    from pathlib import Path
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    if not args:
        app.console.print(f"\n  [bold {palette.info}]📂 {app.workspace}[/]\n")
        return
    target = Path(args[0])
    if not target.is_absolute():
        target = app.workspace / target
    target = target.resolve()
    if not target.is_dir():
        app.console.print(f"  [bold {palette.error}]✗[/]  not a directory: {target}")
        return
    app.workspace = target
    if app.engine:
        app.engine.workspace = target
    app.console.print(f"\n  [bold {palette.success}]●[/]  workspace: [bold {palette.info}]{target}[/]\n")


@register("find", "Search files by name pattern: /find *.py")
def cmd_find_quick(app: "BuddyApp", args: list[str]) -> None:
    from ..tools.registry import get_tool
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    if not args:
        app.console.print("[dim]usage: /find <glob pattern>[/]")
        return
    pattern = args[0]
    tool = get_tool("glob")
    result = tool.execute(app.workspace, pattern=f"**/{pattern}")
    if result.is_error:
        app.console.print(f"  [bold {palette.error}]✗[/]  {result.error}")
        return
    lines = result.output.splitlines()
    app.console.print(f"\n  [bold {palette.info}]🔍 {pattern}[/]  [muted]({len(lines)} matches)[/]")
    for line in lines[:50]:
        app.console.print(f"      [muted]{line}[/]")
    if len(lines) > 50:
        app.console.print(f"      [dim]… {len(lines) - 50} more[/]")
    app.console.print()


@register("run", "Detect & run a project task: /run [task]  (uses task_runner)")
def cmd_run_task(app: "BuddyApp", args: list[str]) -> None:
    from ..tools.registry import get_tool
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    tool = get_tool("task_runner")
    if not args:
        result = tool.execute(app.workspace, action="list")
        app.console.print(f"\n{result.output}\n")
        return
    task = args[0]
    extra = " ".join(args[1:]) if len(args) > 1 else ""
    result = tool.execute(app.workspace, action="run", task=task, extra_args=extra)
    if result.is_error:
        app.console.print(f"\n  [bold {palette.error}]✗[/]  {result.error}\n")
    else:
        app.console.print(f"\n{result.output}\n")


@register("plugins", "List loaded custom plugins from ~/.gemi/plugins/")
def cmd_plugins(app: "BuddyApp", args: list[str]) -> None:
    from .. import plugins as plugins_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    if args and args[0] in ("reload", "refresh"):
        infos = plugins_module.reload()
        n_ok = sum(1 for p in infos if p.loaded)
        n_tools = sum(len(p.tools) for p in infos)
        app.console.print(
            f"\n  [bold {palette.buddy}]✻[/]  reloaded {n_ok} plugin(s), "
            f"{n_tools} tool(s)\n"
        )
        return

    if args and args[0] == "example":
        path = plugins_module.write_example_plugin()
        app.console.print(f"\n  [bold {palette.success}]✓[/]  example plugin written to: [bold]{path}[/]")
        app.console.print(f"  [muted]rename to .py and reload to activate[/]\n")
        return

    plugins = plugins_module.list_loaded()
    app.console.print()
    app.console.print(
        f"  [bold {palette.buddy}]✻ plugins[/]  "
        f"[muted]({plugins_module.PLUGINS_DIR})[/]"
    )
    if not plugins:
        app.console.print(f"\n  [muted]no plugins loaded. drop a .py file in the plugins dir.[/]")
        app.console.print(f"  [muted]/plugins example to write a sample plugin.[/]\n")
        return
    for p in plugins:
        app.console.print()
        if p.loaded:
            app.console.print(f"      [bold {palette.success}]●[/]  [bold {palette.info}]{p.name}[/]")
            app.console.print(f"        [muted]tools:[/] {', '.join(p.tools) or '(none)'}")
        else:
            app.console.print(f"      [bold {palette.error}]✗[/]  [bold]{p.name}[/]")
            app.console.print(f"        [error]{p.error[:120]}[/]")
        app.console.print(f"        [dim]{p.path}[/]")
    app.console.print()
    app.console.print(f"  [muted]/plugins reload[/]  [dim]·[/]  [muted]/plugins example[/]\n")


@register("mcp", "List or reload MCP servers from ~/.gemi/mcp.json")
def cmd_mcp(app: "BuddyApp", args: list[str]) -> None:
    from .. import mcp as mcp_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    if args and args[0] in ("reload", "refresh"):
        app.console.print(f"\n  [muted]reloading MCP servers...[/]")
        summary = mcp_module.reload()
        for name, info in summary.items():
            mark = f"[bold {palette.success}]✓[/]" if info["ok"] else f"[bold {palette.error}]✗[/]"
            app.console.print(
                f"    {mark}  [bold]{name}[/]  "
                f"[muted]{info.get('tools', 0)} tool(s)[/]" +
                (f"  [error]{info['error'][:80]}[/]" if info.get("error") else "")
            )
        app.console.print()
        return

    if args and args[0] == "example":
        path = mcp_module.write_example_config()
        app.console.print(f"\n  [bold {palette.success}]✓[/]  example MCP config: [bold]{path}[/]")
        app.console.print(f"  [muted]edit, rename to mcp.json, then /mcp reload[/]\n")
        return

    if args and args[0] == "stop":
        mcp_module.shutdown_all()
        app.console.print(f"\n  [bold {palette.success}]●[/]  all MCP servers stopped\n")
        return

    if args and args[0] == "tools":
        target = args[1] if len(args) > 1 else None
        servers = mcp_module.list_servers()
        if target:
            servers = [s for s in servers if s.name == target]
        if not servers:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  no matching server\n")
            return
        app.console.print()
        for s in servers:
            app.console.print(f"  [bold {palette.info}]{s.name}[/]  [muted]({len(s.tool_names)} tool(s))[/]")
            for n in s.tool_names:
                app.console.print(f"      [tool.name]{n}[/]")
            app.console.print()
        return

    if args and args[0] == "check":
        # Validate config: missing env vars, bad commands, etc.
        import json as _json, shutil as _shutil, os as _os, re as _re
        cfg_path = mcp_module.MCP_CONFIG
        if not cfg_path.exists():
            app.console.print(f"\n  [bold {palette.error}]✗[/]  no mcp.json at {cfg_path}\n")
            return
        try:
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  invalid JSON: {e}\n")
            return
        servers = cfg.get("servers", {})
        app.console.print()
        app.console.print(f"  [bold {palette.buddy}]✻ MCP config check[/]  [muted]({cfg_path})[/]")
        env_pat = _re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
        ok_count = err_count = warn_count = 0
        for name, spec in servers.items():
            if not isinstance(spec, dict):
                continue
            transport = spec.get("transport", "stdio")
            enabled = spec.get("enabled", True)
            issues = []
            warnings = []
            # Check command exists for stdio
            if transport == "stdio":
                cmd = spec.get("command", "")
                if cmd and not _shutil.which(cmd):
                    issues.append(f"command not on PATH: {cmd}")
            # Check env vars referenced
            text_blob = _json.dumps(spec)
            for var in env_pat.findall(text_blob):
                if not _os.environ.get(var):
                    warnings.append(f"${{{var}}} not set")
            # Render line
            if not enabled:
                app.console.print(f"    [dim]·  {name:<22}[/]  [muted]disabled[/]")
                continue
            if issues:
                err_count += 1
                app.console.print(f"    [bold {palette.error}]✗[/]  [bold]{name:<22}[/]  [error]{'; '.join(issues)}[/]")
            elif warnings:
                warn_count += 1
                app.console.print(f"    [bold {palette.warning}]⚠[/]  [bold]{name:<22}[/]  [warning]{'; '.join(warnings)}[/]")
            else:
                ok_count += 1
                app.console.print(f"    [bold {palette.success}]✓[/]  [bold]{name:<22}[/]  [muted]ready[/]")
        app.console.print()
        app.console.print(
            f"  [muted]summary:[/]  "
            f"[{palette.success}]{ok_count} ready[/]  [dim]·[/]  "
            f"[{palette.warning}]{warn_count} need credentials[/]  [dim]·[/]  "
            f"[{palette.error}]{err_count} broken[/]\n"
        )
        return

    if args and args[0] == "enable":
        if len(args) < 2:
            app.console.print(f"\n  [muted]usage:[/] [bold {palette.buddy_shimmer}]/mcp enable <server>[/]\n")
            return
        # Toggle the enabled flag for the named server
        import json as _json
        cfg_path = mcp_module.MCP_CONFIG
        if not cfg_path.exists():
            app.console.print(f"\n  [bold {palette.error}]✗[/]  no mcp.json\n")
            return
        try:
            data = _json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  invalid JSON: {e}\n")
            return
        servers = data.get("servers", {})
        if args[1] not in servers:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  no such server: {args[1]}\n")
            return
        servers[args[1]]["enabled"] = True
        cfg_path.write_text(_json.dumps(data, indent=2), encoding="utf-8")
        app.console.print(f"\n  [bold {palette.success}]✓[/]  enabled [bold]{args[1]}[/]  [muted](run /mcp reload to start)[/]\n")
        return

    if args and args[0] == "disable":
        if len(args) < 2:
            app.console.print(f"\n  [muted]usage:[/] [bold {palette.buddy_shimmer}]/mcp disable <server>[/]\n")
            return
        import json as _json
        cfg_path = mcp_module.MCP_CONFIG
        try:
            data = _json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  invalid mcp.json\n")
            return
        if args[1] not in data.get("servers", {}):
            app.console.print(f"\n  [bold {palette.error}]✗[/]  no such server: {args[1]}\n")
            return
        data["servers"][args[1]]["enabled"] = False
        cfg_path.write_text(_json.dumps(data, indent=2), encoding="utf-8")
        app.console.print(f"\n  [bold {palette.warning}]●[/]  disabled [bold]{args[1]}[/]  [muted](run /mcp reload)[/]\n")
        return

    servers = mcp_module.list_servers()
    app.console.print()
    app.console.print(
        f"  [bold {palette.buddy}]✻ MCP servers[/]  "
        f"[muted]({mcp_module.MCP_CONFIG})[/]"
    )
    if not servers:
        app.console.print(f"\n  [muted]no servers configured. /mcp example to write a sample config.[/]\n")
        return
    for s in servers:
        if s.is_running and s.initialized:
            mark = f"[bold {palette.success}]●[/]"
            label = "[bold]running[/]"
        elif s.error:
            mark = f"[bold {palette.error}]✗[/]"
            label = f"[error]error[/]"
        else:
            mark = f"[bold {palette.warning}]◐[/]"
            label = f"[warning]initializing[/]"
        app.console.print()
        app.console.print(f"      {mark}  [bold {palette.info}]{s.name}[/]  {label}  "
                          f"[muted]{s.tools_count} tool(s)[/]")
        app.console.print(f"        [muted]command:[/]  [dim]{s.command} {' '.join(s.args)}[/]")
        if s.error:
            app.console.print(f"        [error]{s.error[:120]}[/]")
    app.console.print()
    app.console.print(
        f"  [muted]/mcp reload[/]  [dim]·[/]  [muted]/mcp stop[/]  [dim]·[/]  [muted]/mcp example[/]\n"
    )


@register("bg", "Run a shell command in the background: /bg <command>")
def cmd_bg(app: "BuddyApp", args: list[str]) -> None:
    from .. import background as bg_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    if not args:
        app.console.print(f"\n  [muted]usage:[/]  [bold {palette.buddy_shimmer}]/bg <shell command>[/]\n")
        return
    cmd_string = " ".join(args)
    job = bg_module.spawn_shell(cmd_string, title=cmd_string, cwd=str(app.workspace))
    app.console.print(
        f"  [bold {palette.buddy}]●[/]  bg [bold]{job.id}[/] started  "
        f"[muted]{cmd_string[:60]}[/]"
    )


@register("jobs", "List active and recent background jobs")
def cmd_jobs(app: "BuddyApp", args: list[str]) -> None:
    from .. import background as bg_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    if args and args[0] in ("clear", "purge"):
        n = bg_module.clear_completed()
        app.console.print(f"\n  [bold {palette.success}]●[/]  cleared {n} completed job(s)\n")
        return

    if args and args[0] == "cancel" and len(args) > 1:
        ok = bg_module.cancel(args[1])
        if ok:
            app.console.print(f"\n  [bold {palette.warning}]●[/]  cancelled {args[1]}\n")
        else:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  could not cancel {args[1]}\n")
        return

    if args and args[0].startswith("bg") and len(args[0]) > 2:
        job = bg_module.get_job(args[0])
        if not job:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  no such job: {args[0]}\n")
            return
        app.console.print()
        state_color = {
            "running":   palette.warning,
            "done":      palette.success,
            "failed":    palette.error,
            "cancelled": palette.text_muted,
            "pending":   palette.text_muted,
        }.get(job.state, palette.text)
        app.console.print(f"  [bold {state_color}]{job.id}[/]  [bold]{job.state}[/]  "
                          f"[muted]{job.title}[/]  [dim]{job.elapsed:.1f}s[/]")
        if job.exit_code is not None:
            app.console.print(f"  [muted]exit code:[/] {job.exit_code}")
        if job.error:
            app.console.print(f"  [error]{job.error}[/]")
        if job.output:
            app.console.print()
            for line in job.output.splitlines()[-20:]:
                app.console.print(f"      [muted]│ {line}[/]")
        app.console.print()
        return

    jobs = bg_module.list_jobs(include_done=True)
    app.console.print()
    app.console.print(f"  [bold {palette.buddy}]✻ background jobs[/]  [muted]({len(jobs)} total)[/]")
    if not jobs:
        app.console.print(f"\n  [muted]no jobs. start one with [/][bold {palette.buddy_shimmer}]/bg <command>[/]\n")
        return
    for j in jobs:
        state_color = {
            "running":   palette.warning,
            "done":      palette.success,
            "failed":    palette.error,
            "cancelled": palette.text_muted,
            "pending":   palette.text_muted,
        }.get(j.state, palette.text)
        glyph = {
            "running": "◌", "done": "●", "failed": "✗",
            "cancelled": "○", "pending": "○",
        }.get(j.state, "·")
        app.console.print(
            f"      [bold {state_color}]{glyph}[/]  [bold]{j.id}[/]  "
            f"[{state_color}]{j.state:<10}[/]  "
            f"[dim]{j.elapsed:5.1f}s[/]  "
            f"[muted]{j.title[:60]}[/]"
        )
    app.console.print()
    app.console.print(
        f"  [muted]/jobs <id>[/]  [dim]·[/]  [muted]/jobs cancel <id>[/]  "
        f"[dim]·[/]  [muted]/jobs clear[/]\n"
    )


@register("logs", "Show recent gemi log events (structured JSONL)")
def cmd_logs(app: "BuddyApp", args: list[str]) -> None:
    from .. import logger as logger_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    log = logger_module.get_logger()

    if args and args[0] in ("on", "enable"):
        log.enable()
        app.console.print(f"\n  [bold {palette.success}]●[/]  logging enabled — writing to [bold]{logger_module._today_path()}[/]\n")
        return
    if args and args[0] in ("off", "disable"):
        log.disable()
        app.console.print(f"\n  [bold {palette.warning}]●[/]  logging disabled\n")
        return
    if args and args[0] == "stats":
        s = log.stats()
        app.console.print()
        app.console.print(f"  [bold {palette.buddy}]✻ log stats[/]")
        app.console.print(f"      [muted]enabled:[/]  {'yes' if s['enabled'] else 'no'}")
        app.console.print(f"      [muted]ring:[/]     {s['ring_size']}/{s['ring_max']}")
        app.console.print(f"      [muted]file:[/]     {s['file_path'] or '(none)'}")
        app.console.print(f"      [muted]size:[/]     {s['file_size']} bytes")
        if s["kind_counts"]:
            app.console.print(f"\n      [muted]events by kind:[/]")
            for kind, count in sorted(s["kind_counts"].items(), key=lambda x: -x[1])[:15]:
                app.console.print(f"          {count:>5}  [bold {palette.info}]{kind}[/]")
        app.console.print()
        return

    kind_filter = args[0] if args else ""
    events = log.recent(limit=30, kind_filter=kind_filter)
    app.console.print()
    title = f"  [bold {palette.buddy}]✻ recent log events[/]"
    if kind_filter:
        title += f"  [muted]filter: {kind_filter}[/]"
    app.console.print(title)
    if not events:
        app.console.print(f"\n  [muted]no events. enable with [/][bold {palette.buddy_shimmer}]/logs on[/]\n")
        return
    import time as _time
    now = _time.time()
    for e in events:
        age = now - e.ts
        if age < 60:
            age_s = f"{int(age)}s"
        elif age < 3600:
            age_s = f"{int(age/60)}m"
        else:
            age_s = f"{int(age/3600)}h"
        level_color = {
            "info": palette.text_muted,
            "warn": palette.warning,
            "error": palette.error,
        }.get(e.level, palette.text)
        data_str = " ".join(f"{k}={str(v)[:30]}" for k, v in list(e.data.items())[:3])
        app.console.print(
            f"      [dim]{age_s:>4}[/]  [bold {level_color}]{e.level:<5}[/]  "
            f"[bold {palette.info}]{e.kind:<24}[/]  [muted]{data_str}[/]"
        )
    app.console.print()
    app.console.print(f"  [muted]/logs <kind>[/]  [dim]·[/]  [muted]/logs stats[/]  [dim]·[/]  [muted]/logs on|off[/]\n")


@register("templates", "List available prompt templates")
def cmd_templates(app: "BuddyApp", args: list[str]) -> None:
    from .. import prompts as prompts_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    templates = prompts_module.list_templates()
    app.console.print()
    app.console.print(
        f"  [bold {palette.buddy}]✻ prompt templates[/]  "
        f"[muted]({prompts_module.TEMPLATES_DIR})[/]"
    )
    if not templates:
        app.console.print(f"\n  [muted]no templates. they will be auto-seeded on first /templates call.[/]\n")
        return
    for t in templates:
        app.console.print()
        app.console.print(f"      [bold {palette.info}]{t.name}[/]  [muted]{t.description}[/]")
        if t.variables:
            app.console.print(f"        [muted]vars:[/]  {', '.join(t.variables)}")
    app.console.print()
    app.console.print(
        f"  [muted]usage:[/]  [bold {palette.buddy_shimmer}]/use <name> key=value ...[/]\n"
    )


@register("use", "Render a prompt template and submit it: /use <name> key=value ...")
def cmd_use(app: "BuddyApp", args: list[str]) -> None:
    from .. import prompts as prompts_module
    from ..ui.render import render_assistant
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    if not args:
        app.console.print(f"\n  [muted]usage:[/]  [bold {palette.buddy_shimmer}]/use <template> [key=value ...][/]")
        app.console.print(f"  [muted]use[/]  [bold {palette.buddy_shimmer}]/templates[/]  [muted]to list available templates[/]\n")
        return
    name = args[0]
    template = prompts_module.load_template(name)
    if not template:
        app.console.print(f"\n  [bold {palette.error}]✗[/]  no template: [bold]{name}[/]")
        avail = prompts_module.list_templates()
        if avail:
            app.console.print(f"  [muted]available:[/] {', '.join(t.name for t in avail)}\n")
        return
    arg_string = " ".join(args[1:])
    parsed = prompts_module.parse_args(arg_string)
    rendered, err = prompts_module.render(template, parsed)
    if err:
        app.console.print(f"\n  [bold {palette.warning}]⚠[/]  {err}\n")

    app.console.print()
    app.console.print(f"  [bold {palette.buddy}]✻[/]  rendered template [bold]{name}[/]")

    # Submit the rendered prompt as a normal turn
    if not app.engine:
        app.console.print(f"  [bold {palette.error}]✗[/]  no agent — cannot submit\n")
        return
    try:
        app._streaming_started = False
        result = app.engine.query(rendered)
        if app._streaming_started:
            app.console.print()
            app._streaming_started = False
            from ..ui.render import render_tool_result
            for tc in result.tool_results:
                render_tool_result(app.console, tc)
            app._render_usage(result)
        else:
            render_assistant(app.console, result)
    except Exception as e:
        app.console.print(f"\n  [bold {palette.error}]✗[/]  {e}\n")


@register("profile", "List, save, or apply a profile preset")
def cmd_profile(app: "BuddyApp", args: list[str]) -> None:
    from .. import profiles as profiles_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    if not args:
        profiles = profiles_module.list_profiles()
        active = profiles_module.get_active_profile_name()
        app.console.print()
        app.console.print(f"  [bold {palette.buddy}]✻ profiles[/]  [muted]({len(profiles)} saved)[/]")
        if not profiles:
            app.console.print(f"\n  [muted]no profiles. /profile save <name> to create one.[/]\n")
            return
        for p in profiles:
            marker = f"[bold {palette.success}]●[/]" if p.name == active else f"[dim {palette.text_subtle}]○[/]"
            mode_bits = []
            if p.yolo: mode_bits.append(f"[bold {palette.yolo}]YOLO[/]")
            if p.plan_mode: mode_bits.append(f"[bold {palette.plan}]PLAN[/]")
            if p.autopilot: mode_bits.append(f"[bold {palette.auto}]AUTO[/]")
            modes = "  ".join(mode_bits) or "[dim]normal[/]"
            app.console.print()
            app.console.print(
                f"      {marker}  [bold {palette.info}]{p.name}[/]  "
                f"[muted]{p.description or ''}[/]"
            )
            app.console.print(
                f"        [muted]agent:[/] {p.agent or '(any)'}  "
                f"[muted]theme:[/] {p.theme or '(current)'}  "
                f"[muted]modes:[/] {modes}"
            )
        app.console.print()
        app.console.print(
            f"  [muted]/profile <name>[/]  [dim]·[/]  "
            f"[muted]/profile save <name>[/]  [dim]·[/]  "
            f"[muted]/profile delete <name>[/]\n"
        )
        return

    sub = args[0]
    if sub == "save":
        if len(args) < 2:
            app.console.print(f"\n  [muted]usage:[/] [bold {palette.buddy_shimmer}]/profile save <name> [description...][/]\n")
            return
        name = args[1]
        desc = " ".join(args[2:]) if len(args) > 2 else ""
        profile = profiles_module.capture_current(app, name, desc)
        app.console.print(
            f"\n  [bold {palette.success}]✓[/]  saved profile [bold]{name}[/]\n"
        )
        return

    if sub == "delete":
        if len(args) < 2:
            app.console.print(f"\n  [muted]usage:[/] [bold {palette.buddy_shimmer}]/profile delete <name>[/]\n")
            return
        if profiles_module.delete_profile(args[1]):
            app.console.print(f"\n  [bold {palette.success}]✓[/]  deleted profile [bold]{args[1]}[/]\n")
        else:
            app.console.print(f"\n  [bold {palette.error}]✗[/]  no such profile: {args[1]}\n")
        return

    # Apply profile
    profile = profiles_module.get_profile(sub)
    if not profile:
        app.console.print(f"\n  [bold {palette.error}]✗[/]  no profile: [bold]{sub}[/]")
        avail = ", ".join(p.name for p in profiles_module.list_profiles()) or "(none)"
        app.console.print(f"  [muted]available:[/] {avail}\n")
        return
    profiles_module.apply_profile(app, profile)
    profiles_module.set_active(profile.name)
    app.console.print(
        f"\n  [bold {palette.buddy}]✻[/]  applied profile [bold {palette.buddy_shimmer}]{profile.name}[/]"
    )
    if profile.description:
        app.console.print(f"  [muted]{profile.description}[/]")
    app.console.print()


@register("approval", "Toggle interactive approval flow for risky tools")
def cmd_approval(app: "BuddyApp", args: list[str]) -> None:
    from .. import approval as approval_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    if args and args[0] in ("on", "enable"):
        approval_module.set_enabled(True)
        app.console.print(f"\n  [bold {palette.warning}]⚠[/]  approval flow enabled — risky tools will prompt y/n/a/d\n")
        return
    if args and args[0] in ("off", "disable"):
        approval_module.set_enabled(False)
        app.console.print(f"\n  [bold {palette.success}]●[/]  approval flow disabled\n")
        return
    if args and args[0] == "reset":
        approval_module.reset_session()
        app.console.print(f"\n  [bold {palette.success}]●[/]  cleared session approval state\n")
        return

    enabled = approval_module.is_enabled()
    tools = approval_module.get_approval_tools()
    approved, denied = approval_module.list_session_state()
    app.console.print()
    app.console.print(f"  [bold {palette.buddy}]✻ approval flow[/]")
    app.console.print(f"      [muted]enabled:[/]  {'yes' if enabled else 'no'}")
    app.console.print(f"      [muted]gated:[/]    {', '.join(tools) or '(none)'}")
    if approved:
        app.console.print(f"      [muted]session-approved:[/]  [{palette.success}]{', '.join(approved)}[/]")
    if denied:
        app.console.print(f"      [muted]session-denied:[/]    [{palette.error}]{', '.join(denied)}[/]")
    app.console.print()
    app.console.print(f"  [muted]/approval on|off|reset[/]\n")


@register("retrypolicy", "Show or configure tool retry policy")
def cmd_retrypolicy(app: "BuddyApp", args: list[str]) -> None:
    from .. import retry as retry_module
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    if args and args[0] == "reload":
        retry_module.get_policy(reload=True)
        app.console.print(f"\n  [bold {palette.success}]●[/]  retry policy reloaded from config\n")
        return

    p = retry_module.get_policy()
    app.console.print()
    app.console.print(f"  [bold {palette.buddy}]✻ retry policy[/]")
    app.console.print(f"      [muted]enabled:[/]      {'yes' if p.enabled else 'no'}")
    app.console.print(f"      [muted]max attempts:[/] {p.max_attempts}")
    app.console.print(f"      [muted]base delay:[/]   {p.base_delay_ms}ms")
    app.console.print(f"      [muted]max delay:[/]    {p.max_delay_ms}ms")
    app.console.print(f"      [muted]tools:[/]        {', '.join(p.tools)}")
    app.console.print()
    app.console.print(f"  [muted]edit ~/.gemi/config.json under \"retry\" then /retrypolicy reload[/]\n")


@register("task", "Spawn a sub-agent task: /task <prompt>  (uses task tool)")
def cmd_task(app: "BuddyApp", args: list[str]) -> None:
    """Convenience wrapper that just submits 'use the task tool to: <prompt>'."""
    from ..ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())
    if not args:
        app.console.print(f"\n  [muted]usage:[/]  [bold {palette.buddy_shimmer}]/task <prompt>[/]\n")
        return
    prompt = " ".join(args)
    if not app.engine:
        app.console.print(f"\n  [bold {palette.error}]✗[/]  no agent active\n")
        return
    instruction = (
        f"Use the `task` tool to spawn a sub-agent that will complete this task:\n\n"
        f"{prompt}\n\n"
        f"Pass the prompt clearly so the sub-agent has full context."
    )
    try:
        app._streaming_started = False
        result = app.engine.query(instruction)
        from ..ui.render import render_assistant, render_tool_result
        if app._streaming_started:
            app.console.print()
            app._streaming_started = False
            for tc in result.tool_results:
                render_tool_result(app.console, tc)
            app._render_usage(result)
        else:
            render_assistant(app.console, result)
    except Exception as e:
        app.console.print(f"\n  [bold {palette.error}]✗[/]  {e}\n")


@register("exit", "Exit Buddy")
def cmd_exit(app: "BuddyApp", args: list[str]) -> None:
    app._auto_save_on_exit()
    app.running = False


@register("quit", "Exit Buddy")
def cmd_quit(app: "BuddyApp", args: list[str]) -> None:
    app._auto_save_on_exit()
    app.running = False
