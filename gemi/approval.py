"""Diff/edit approval flow — interactive y/n/a/d gating for risky tool calls.

When a WRITE-tier tool is about to run with potentially risky args, Buddy
can pause and ask the user to approve. Triggered by:
  - File edits (write_file, edit_file, multi_edit, delete_file, move_file)
  - Shell commands matching a "risky" pattern
  - Any tool the user has flagged for approval

User responses:
  y   approve this call
  n   deny this call
  a   always approve (this tool, this session)
  d   deny and tell agent to stop
  s   show full diff / args before deciding (for edits)

Configuration in ~/.gemi/config.json:

  {
    "approval": {
      "enabled": false,
      "tools": ["write_file", "edit_file", "delete_file", "bash"],
      "auto_approved_session": []
    }
  }
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

CONFIG_FILE = Path.home() / ".gemi" / "config.json"


# Per-session always-approve list (in-memory only)
_SESSION_APPROVED: set[str] = set()
_SESSION_DENIED: set[str] = set()


def _load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {"approval": {"enabled": False, "tools": []}}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"approval": {"enabled": False, "tools": []}}


def _save_config(cfg: dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def is_enabled() -> bool:
    cfg = _load_config().get("approval") or {}
    return bool(cfg.get("enabled", False))


def set_enabled(enabled: bool) -> None:
    cfg = _load_config()
    cfg.setdefault("approval", {})["enabled"] = bool(enabled)
    _save_config(cfg)


def get_approval_tools() -> list[str]:
    cfg = _load_config().get("approval") or {}
    return list(cfg.get("tools", []) or [
        "write_file", "edit_file", "multi_edit",
        "delete_file", "move_file", "copy_file",
        "bash", "powershell",
    ])


def needs_approval(tool_name: str, dangerous_session: bool = False) -> bool:
    if not is_enabled():
        return False
    if dangerous_session:
        return False  # YOLO mode bypasses approval
    if tool_name in _SESSION_APPROVED:
        return False
    if tool_name in _SESSION_DENIED:
        return True   # will deny
    return tool_name in get_approval_tools()


def session_approve(tool_name: str) -> None:
    _SESSION_APPROVED.add(tool_name)
    _SESSION_DENIED.discard(tool_name)


def session_deny(tool_name: str) -> None:
    _SESSION_DENIED.add(tool_name)
    _SESSION_APPROVED.discard(tool_name)


def reset_session() -> None:
    _SESSION_APPROVED.clear()
    _SESSION_DENIED.clear()


def list_session_state() -> tuple[list[str], list[str]]:
    return sorted(_SESSION_APPROVED), sorted(_SESSION_DENIED)


def render_preview(tool_name: str, args: dict[str, Any]) -> str:
    """Build a human-readable preview of what the tool is about to do."""
    if tool_name in ("write_file", "edit_file", "multi_edit"):
        fp = args.get("file_path", "<?>")
        if tool_name == "edit_file":
            old = args.get("old_string", "")[:200]
            new = args.get("new_string", "")[:200]
            return (
                f"  file:    {fp}\n"
                f"  - old:   {old!r}{'…' if len(old) >= 200 else ''}\n"
                f"  + new:   {new!r}{'…' if len(new) >= 200 else ''}"
            )
        if tool_name == "write_file":
            content = args.get("content", "")[:300]
            return f"  file:    {fp}\n  content: {content!r}{'…' if len(content) >= 300 else ''}"
        if tool_name == "multi_edit":
            edits = args.get("edits", [])
            return f"  file:    {fp}\n  edits:   {len(edits)} change(s)"
    if tool_name in ("delete_file", "move_file", "copy_file"):
        return "  " + " ".join(f"{k}={v!r}" for k, v in args.items())
    if tool_name in ("bash", "powershell"):
        cmd = args.get("command", "")
        return f"  $ {cmd[:300]}{'…' if len(cmd) > 300 else ''}"
    return "  " + " ".join(f"{k}={str(v)[:60]!r}" for k, v in args.items())


def prompt_user(tool_name: str, args: dict[str, Any], console=None) -> tuple[bool, str]:
    """Prompt the user to approve this tool call.

    Returns (allow: bool, reason: str). If reason is non-empty and allow is
    False, the engine treats it as a permanent stop.
    """
    if console is None:
        from rich.console import Console
        console = Console()

    from .ui.theme import get_palette, get_active_theme_name
    palette = get_palette(get_active_theme_name())

    preview = render_preview(tool_name, args)

    console.print()
    console.print(
        f"  [bold {palette.warning}]⚠[/]  approval needed for "
        f"[bold {palette.tier_write}]{tool_name}[/]"
    )
    console.print(preview)
    console.print()
    console.print(
        f"  [bold {palette.buddy_shimmer}]y[/]es  "
        f"[bold {palette.buddy_shimmer}]n[/]o  "
        f"[bold {palette.buddy_shimmer}]a[/]lways (this session)  "
        f"[bold {palette.buddy_shimmer}]d[/]eny+stop"
    )

    try:
        answer = input("  > ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        return False, "user cancelled"

    if answer in ("y", "yes", ""):
        return True, ""
    if answer in ("a", "always"):
        session_approve(tool_name)
        return True, ""
    if answer in ("d", "deny", "stop"):
        return False, "user denied — stop here"
    return False, "user denied this call"
