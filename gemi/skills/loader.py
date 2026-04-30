"""Skill loader — reads MD skills from skills_universal and skills_curated."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import PROJECTS_ROOT

SKILL_DIRS = [
    PROJECTS_ROOT / "skills_universal",
    PROJECTS_ROOT / "skills_curated",
]


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


def load_skill(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    fm = _parse_frontmatter(text)
    name = fm.get("name", path.stem)
    return {
        "name": name,
        "description": fm.get("description", ""),
        "type": fm.get("type", "skill"),
        "path": str(path),
        "content": text,
    }


def list_skills() -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    seen: set[str] = set()
    for skill_dir in SKILL_DIRS:
        if not skill_dir.is_dir():
            continue
        for f in sorted(skill_dir.rglob("*.md")):
            skill = load_skill(f)
            if skill and skill["name"] not in seen:
                seen.add(skill["name"])
                skills.append(skill)
    return skills


def get_skill(name: str) -> dict[str, Any] | None:
    for skill_dir in SKILL_DIRS:
        if not skill_dir.is_dir():
            continue
        for f in skill_dir.rglob("*.md"):
            if f.stem == name or f.stem.replace("-", "_") == name.replace("-", "_"):
                return load_skill(f)
    return None


def search_skills(query: str) -> list[dict[str, Any]]:
    query_lower = query.lower()
    results = []
    for skill in list_skills():
        name = skill["name"].lower()
        desc = skill.get("description", "").lower()
        if query_lower in name or query_lower in desc:
            results.append(skill)
    return results
