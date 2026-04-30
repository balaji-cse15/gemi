"""MD-file-based memory system with MEMORY.md index."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MEMORY_DIR = Path.home() / ".gemi" / "memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"


def _ensure_dir() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_INDEX.exists():
        MEMORY_INDEX.write_text("# Buddy Memory Index\n\n", encoding="utf-8")


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}
    result = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def save_memory(name: str, content: str, mem_type: str = "project", description: str = "") -> Path:
    _ensure_dir()
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    filename = f"{mem_type}_{slug}.md"
    filepath = MEMORY_DIR / filename

    file_content = f"""---
name: {name}
description: {description or name}
type: {mem_type}
---

{content}
"""
    filepath.write_text(file_content, encoding="utf-8")
    _update_index(name, filename, description)
    return filepath


def _update_index(name: str, filename: str, description: str) -> None:
    index_text = MEMORY_INDEX.read_text(encoding="utf-8")
    entry = f"- [{name}]({filename}) -- {description or name}"
    if filename in index_text:
        lines = index_text.splitlines()
        new_lines = [entry if filename in line else line for line in lines]
        MEMORY_INDEX.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        with MEMORY_INDEX.open("a", encoding="utf-8") as f:
            f.write(entry + "\n")


def list_memories() -> list[dict[str, Any]]:
    _ensure_dir()
    results: list[dict[str, Any]] = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(text)
        results.append({
            "name": fm.get("name", f.stem),
            "type": fm.get("type", "unknown"),
            "description": fm.get("description", ""),
            "path": str(f),
        })
    return results


def search_memories(query: str) -> list[dict[str, Any]]:
    query_lower = query.lower()
    results = []
    for mem in list_memories():
        if query_lower in mem["name"].lower() or query_lower in mem.get("description", "").lower():
            results.append(mem)
    return results


def get_memory(name: str) -> str | None:
    _ensure_dir()
    for f in MEMORY_DIR.glob("*.md"):
        if f.name == "MEMORY.md":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(text)
        if fm.get("name", "").lower() == name.lower() or f.stem == name:
            return text
    return None


def delete_memory(name: str) -> bool:
    _ensure_dir()
    for f in MEMORY_DIR.glob("*.md"):
        if f.name == "MEMORY.md":
            continue
        fm = _parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        if fm.get("name", "").lower() == name.lower() or f.stem == name:
            f.unlink()
            index_text = MEMORY_INDEX.read_text(encoding="utf-8")
            lines = [l for l in index_text.splitlines() if f.name not in l]
            MEMORY_INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False
