"""Session persistence — save and resume conversations."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

SESSION_DIR = Path.home() / ".gemi" / "sessions"


def _ensure_dir() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _auto_title(messages: list[dict[str, Any]]) -> str:
    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            text = msg["content"].strip().replace("\n", " ")
            if len(text) > 60:
                text = text[:57] + "..."
            return text
    return ""


def save_session(
    agent_slug: str,
    messages: list[dict[str, Any]],
    workspace: str,
    session_id: str = "",
    title: str = "",
    stats: dict[str, Any] | None = None,
) -> Path:
    _ensure_dir()
    sid = session_id or f"{agent_slug}_{int(time.time())}"
    path = SESSION_DIR / f"{sid}.json"
    data = {
        "id": sid,
        "agent": agent_slug,
        "workspace": workspace,
        "title": title or _auto_title(messages),
        "messages": messages,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "turn_count": sum(1 for m in messages if m.get("role") == "user"),
    }
    if stats:
        data["stats"] = stats
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def load_session(session_id: str) -> dict[str, Any] | None:
    _ensure_dir()
    path = SESSION_DIR / f"{session_id}.json"
    if not path.exists():
        for f in SESSION_DIR.glob("*.json"):
            if session_id in f.stem:
                path = f
                break
        else:
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    _ensure_dir()
    sessions = []
    for f in sorted(SESSION_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            title = data.get("title", "")
            if not title:
                for msg in data.get("messages", []):
                    if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                        title = msg["content"][:80].replace("\n", " ")
                        break
            size_kb = f.stat().st_size / 1024
            sessions.append({
                "id": data.get("id", f.stem),
                "agent": data.get("agent", "?"),
                "workspace": data.get("workspace", "?"),
                "saved_at": data.get("saved_at", "?"),
                "turns": data.get("turn_count", 0),
                "title": title,
                "preview": title,
                "size_kb": size_kb,
            })
        except Exception:
            continue
        if len(sessions) >= limit:
            break
    return sessions


def delete_session(session_id: str) -> bool:
    _ensure_dir()
    path = SESSION_DIR / f"{session_id}.json"
    if not path.exists():
        for f in SESSION_DIR.glob("*.json"):
            if session_id in f.stem:
                path = f
                break
        else:
            return False
    path.unlink()
    return True


def rename_session(session_id: str, new_title: str) -> bool:
    _ensure_dir()
    path = SESSION_DIR / f"{session_id}.json"
    if not path.exists():
        for f in SESSION_DIR.glob("*.json"):
            if session_id in f.stem:
                path = f
                break
        else:
            return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["title"] = new_title
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return True
    except Exception:
        return False


def fork_session(
    session_id: str,
    messages: list[dict[str, Any]],
    agent_slug: str,
    workspace: str,
) -> Path:
    _ensure_dir()
    fork_id = f"{session_id}_fork_{int(time.time())}"
    return save_session(
        agent_slug=agent_slug,
        messages=list(messages),
        workspace=workspace,
        session_id=fork_id,
        title=f"(fork) {_auto_title(messages)}",
    )


def session_count() -> int:
    _ensure_dir()
    return sum(1 for _ in SESSION_DIR.glob("*.json"))
