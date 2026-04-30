"""Workspace context loader — auto-discovers BUDDY.md, CLAUDE.md, AGENTS.md.

Walks UP from the workspace directory to the filesystem root looking for
project-specific context files. The closest one wins (most-specific to least).

Files (in priority order):
  1. BUDDY.md       — Buddy-specific instructions
  2. CLAUDE.md      — Claude Code-style instructions (compatibility)
  3. AGENTS.md      — Agent-fleet-specific instructions
  4. .buddy/context.md   — Hidden context file

The loader stops walking up at the first git repo root (.git/) it finds,
so context doesn't leak across unrelated projects.

The discovered content is injected into the system prompt as a
"## Workspace Context" section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

CONTEXT_FILENAMES = ["BUDDY.md", "CLAUDE.md", "AGENTS.md", ".buddy/context.md"]
# Tight caps so small-context agents (8K) aren't overwhelmed by a single
# large project doc. Users can read the full file via /cat <name>.md.
MAX_TOTAL_CHARS = 4_000
MAX_PER_FILE = 2_000


@dataclass
class ContextFile:
    path: Path
    content: str
    relative: str = ""

    @property
    def is_truncated(self) -> bool:
        return len(self.content) >= MAX_PER_FILE


@dataclass
class WorkspaceContext:
    workspace: Path
    files: list[ContextFile] = field(default_factory=list)
    total_chars: int = 0
    git_root: Path | None = None

    @property
    def has_content(self) -> bool:
        return bool(self.files)

    def to_system_block(self) -> str:
        if not self.files:
            return ""
        parts = ["## Workspace Context\n"]
        parts.append(
            "The following files were auto-loaded from the workspace. "
            "They contain project-specific instructions you should follow.\n"
        )
        for f in self.files:
            parts.append(f"\n### {f.relative}\n")
            parts.append(f.content)
            if f.is_truncated:
                parts.append("\n[truncated]")
        return "\n".join(parts)


def _find_git_root(start: Path) -> Path | None:
    cur = start.resolve()
    while True:
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def discover_context(workspace: Path) -> WorkspaceContext:
    """Find and load workspace context files. Walks up to git root or filesystem root."""
    ws = workspace.resolve()
    ctx = WorkspaceContext(workspace=ws)
    ctx.git_root = _find_git_root(ws)
    stop_at = ctx.git_root.parent if ctx.git_root else ws.anchor

    seen_paths: set[Path] = set()
    cur = ws
    chars_remaining = MAX_TOTAL_CHARS

    while True:
        for filename in CONTEXT_FILENAMES:
            candidate = cur / filename
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if len(content) > MAX_PER_FILE:
                content = content[:MAX_PER_FILE] + "\n... [truncated]"
            if len(content) > chars_remaining:
                content = content[:chars_remaining] + "\n... [budget exceeded]"
            chars_remaining -= len(content)
            try:
                rel = str(resolved.relative_to(ws))
            except ValueError:
                rel = str(resolved)
            ctx.files.append(ContextFile(path=resolved, content=content, relative=rel))
            ctx.total_chars += len(content)
            if chars_remaining <= 0:
                return ctx

        # Stop if we hit git root or filesystem root
        if ctx.git_root and cur == ctx.git_root:
            break
        if cur.parent == cur:
            break
        cur = cur.parent

    return ctx


def summarize_context(ctx: WorkspaceContext) -> str:
    if not ctx.files:
        return "(no workspace context found)"
    parts = []
    for f in ctx.files:
        size = f"{len(f.content):,}"
        trunc = " [truncated]" if f.is_truncated else ""
        parts.append(f"  {f.relative}  {size} chars{trunc}")
    return "\n".join(parts)
