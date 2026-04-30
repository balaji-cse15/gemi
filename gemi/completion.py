"""Smart REPL autocomplete — context-aware tab completion.

Goes beyond static slash-command + path completion:
  - After /agent, suggest agent slugs
  - After /theme, suggest theme names
  - After /resume or /delete, suggest session ids
  - After /use, suggest template names
  - After {file_path=, suggest workspace files
  - In free text, suggest file paths the conversation has referenced
  - Otherwise, fall back to filesystem path completion
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


class SmartCompleter(Completer):
    """Context-aware completer for the Buddy REPL."""

    def __init__(self, app):
        self.app = app

    # ---------------------------------------------------------------

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        text = document.text_before_cursor
        word = self._current_word(document)

        # --- Slash commands -----------------------------------------
        if text.lstrip().startswith("/") and len(text.lstrip().split()) <= 1:
            yield from self._slash_command_completions(word)
            return

        # --- After a known slash command, suggest its arguments ----
        head = text.lstrip().split()
        if head and head[0].startswith("/"):
            cmd = head[0][1:]
            from .commands.registry import COMMAND_ALIASES, COMMANDS
            cmd = COMMAND_ALIASES.get(cmd, cmd)
            yield from self._argument_completions(cmd, word)
            return

        # --- Free text — suggest paths and recent references --------
        if word and len(word) >= 2 and not word.startswith("-"):
            yield from self._path_completions(word)

    # ---------------------------------------------------------------

    @staticmethod
    def _current_word(document: Document) -> str:
        text = document.text_before_cursor
        if not text:
            return ""
        # Find current word — treat slashes (path) and dashes as part of word
        i = len(text) - 1
        while i >= 0 and (text[i].isalnum() or text[i] in "._-/\\"):
            i -= 1
        return text[i + 1:]

    # ---------------------------------------------------------------

    def _slash_command_completions(self, word: str) -> Iterable[Completion]:
        from .commands.registry import COMMANDS, COMMAND_ALIASES
        prefix = word.lstrip("/").lower()
        for name in sorted(COMMANDS.keys()):
            if not prefix or name.startswith(prefix):
                cmd = COMMANDS[name]
                yield Completion(
                    f"/{name}",
                    start_position=-len(word),
                    display=f"/{name}",
                    display_meta=cmd.description[:60],
                )
        # Aliases
        for alias, target in sorted(COMMAND_ALIASES.items()):
            if not prefix or alias.startswith(prefix):
                yield Completion(
                    f"/{alias}",
                    start_position=-len(word),
                    display=f"/{alias}",
                    display_meta=f"alias for /{target}",
                )

    # ---------------------------------------------------------------

    def _argument_completions(self, cmd: str, word: str) -> Iterable[Completion]:
        if cmd == "agent" or cmd == "delegate":
            from .config import FLEET
            yield from self._iter_agents(FLEET, word)

        elif cmd in ("launch", "ping"):
            from .config import FLEET
            yield from self._iter_agents(FLEET, word)

        elif cmd == "theme":
            from .ui.theme import list_themes
            for t in list_themes():
                if not word or t.startswith(word):
                    yield Completion(t, start_position=-len(word), display=t)

        elif cmd in ("resume", "delete", "rename"):
            from .session import list_sessions
            for s in list_sessions(limit=30):
                sid = s.get("id", "")
                if not word or sid.startswith(word):
                    yield Completion(
                        sid, start_position=-len(word),
                        display=sid[:40],
                        display_meta=s.get("title", "")[:40],
                    )

        elif cmd == "use":
            from .prompts import list_templates
            for t in list_templates():
                if not word or t.name.startswith(word):
                    yield Completion(
                        t.name, start_position=-len(word),
                        display=t.name,
                        display_meta=(t.description or "")[:40],
                    )

        elif cmd == "tools":
            for token in ("safe", "write", "yolo"):
                if not word or token.startswith(word):
                    yield Completion(token, start_position=-len(word), display=token)

        elif cmd == "hooks" or cmd == "perms" or cmd == "cache" or cmd == "workspace_context":
            for token in ("reload", "log", "clear", "off", "on"):
                if not word or token.startswith(word):
                    yield Completion(token, start_position=-len(word), display=token)

        elif cmd in ("workspace",):
            yield from self._path_completions(word, dirs_only=True)

        else:
            # Generic fallback for paths
            if word and len(word) >= 1:
                yield from self._path_completions(word)

    # ---------------------------------------------------------------

    @staticmethod
    def _iter_agents(fleet, word: str) -> Iterable[Completion]:
        for a in fleet:
            if not word or a.slug.startswith(word):
                marker = "● " if a.is_proxy_running() else "○ "
                yield Completion(
                    a.slug, start_position=-len(word),
                    display=marker + a.slug,
                    display_meta=f"{a.role} · {a.quant}",
                )

    # ---------------------------------------------------------------

    def _path_completions(self, word: str, dirs_only: bool = False) -> Iterable[Completion]:
        try:
            base = Path(word)
            if base.is_dir():
                parent = base
                prefix = ""
            else:
                parent = base.parent
                prefix = base.name
            if not parent.exists():
                # Try resolving against workspace
                if self.app and self.app.workspace:
                    parent = self.app.workspace / parent
                    if not parent.exists():
                        return
                else:
                    return
            for child in sorted(parent.iterdir()):
                name = child.name
                if name.startswith("."):
                    continue
                if dirs_only and not child.is_dir():
                    continue
                if prefix and not name.lower().startswith(prefix.lower()):
                    continue
                rel = child.name if str(parent) in (".", "") else str(parent / name)
                if child.is_dir():
                    rel += "/"
                meta = "directory" if child.is_dir() else self._file_meta(child)
                yield Completion(
                    rel, start_position=-len(word),
                    display=name + ("/" if child.is_dir() else ""),
                    display_meta=meta,
                )
        except Exception:
            return

    @staticmethod
    def _file_meta(path: Path) -> str:
        try:
            sz = path.stat().st_size
            if sz < 1024:
                return f"{sz}B"
            if sz < 1024 * 1024:
                return f"{sz // 1024}KB"
            return f"{sz // (1024 * 1024)}MB"
        except Exception:
            return ""
