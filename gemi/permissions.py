"""Permissions — allow/deny lists with per-tool pattern matching.

The base permission system in query_engine.py handles three tiers
(SAFE / WRITE / YOLO). This module adds a more granular layer:

  - Allow rules: auto-approve a tool call without prompting
  - Deny rules:  auto-reject a tool call (even in YOLO mode)
  - Ask rules:   require user confirmation (future: interactive)

Rules are stored at ~/.gemi/permissions.json:

  {
    "allow": [
      {"tool": "bash", "pattern": "^(ls|pwd|cat|grep|find) "},
      {"tool": "read_file", "pattern": "*"}
    ],
    "deny": [
      {"tool": "bash", "pattern": "rm -rf /|sudo |format c:"},
      {"tool": "*", "pattern": "/etc/shadow|.aws/credentials"}
    ]
  }

Rules apply ON TOP of the base tier system:
  - Deny rules override everything (even YOLO).
  - Allow rules only matter for non-YOLO sessions.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

PERMS_FILE = Path.home() / ".gemi" / "permissions.json"

# Sensible safety floor — denied even in YOLO unless user explicitly removes
DEFAULT_DENY = [
    {"tool": "bash", "pattern": r"rm\s+-rf\s+/(?!\w)"},
    {"tool": "bash", "pattern": r":\(\)\{.*:\|:&.*\};:"},  # fork bomb
    {"tool": "powershell", "pattern": r"Format-Volume"},
    {"tool": "powershell", "pattern": r"Remove-Item\s+.*-Recurse\s+-Force\s+C:\\"},
    {"tool": "*", "pattern": r"\.aws/credentials|\.ssh/id_rsa"},
]


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DEFAULT = "default"   # fall through to base tier system


@dataclass
class Rule:
    tool: str = "*"          # tool name or "*"
    pattern: str = ""        # regex against arg-values join (or empty = any)
    description: str = ""

    def matches(self, name: str, args: dict[str, Any]) -> bool:
        if self.tool != "*" and self.tool != name:
            return False
        if not self.pattern:
            return True
        haystack = " ".join(str(v) for v in args.values())
        try:
            return bool(re.search(self.pattern, haystack))
        except re.error:
            return self.pattern in haystack


@dataclass
class Permissions:
    allow: list[Rule] = field(default_factory=list)
    deny: list[Rule] = field(default_factory=list)

    def evaluate(self, name: str, args: dict[str, Any]) -> tuple[Decision, str]:
        for rule in self.deny:
            if rule.matches(name, args):
                return Decision.DENY, (
                    rule.description or f"matched deny rule '{rule.pattern}' on {rule.tool}"
                )
        for rule in self.allow:
            if rule.matches(name, args):
                return Decision.ALLOW, (
                    rule.description or f"matched allow rule on {rule.tool}"
                )
        return Decision.DEFAULT, ""

    def add_allow(self, tool: str, pattern: str = "", description: str = "") -> None:
        self.allow.append(Rule(tool=tool, pattern=pattern, description=description))

    def add_deny(self, tool: str, pattern: str = "", description: str = "") -> None:
        self.deny.append(Rule(tool=tool, pattern=pattern, description=description))


def _build_default() -> Permissions:
    p = Permissions()
    for entry in DEFAULT_DENY:
        p.add_deny(
            tool=entry.get("tool", "*"),
            pattern=entry.get("pattern", ""),
            description=entry.get("description", "default safety rule"),
        )
    return p


def load_permissions() -> Permissions:
    perms = _build_default()
    if not PERMS_FILE.exists():
        return perms
    try:
        data = json.loads(PERMS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return perms
    for entry in data.get("allow", []):
        perms.add_allow(
            tool=entry.get("tool", "*"),
            pattern=entry.get("pattern", ""),
            description=entry.get("description", ""),
        )
    for entry in data.get("deny", []):
        perms.add_deny(
            tool=entry.get("tool", "*"),
            pattern=entry.get("pattern", ""),
            description=entry.get("description", ""),
        )
    return perms


def save_permissions(perms: Permissions) -> None:
    PERMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "allow": [{"tool": r.tool, "pattern": r.pattern, "description": r.description} for r in perms.allow],
        "deny": [
            {"tool": r.tool, "pattern": r.pattern, "description": r.description}
            for r in perms.deny
            # don't re-persist defaults — they auto-apply on load
            if not any(d.get("pattern") == r.pattern and d.get("tool") == r.tool for d in DEFAULT_DENY)
        ],
    }
    PERMS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


_CACHED: Permissions | None = None


def get_permissions(reload: bool = False) -> Permissions:
    global _CACHED
    if reload or _CACHED is None:
        _CACHED = load_permissions()
    return _CACHED
