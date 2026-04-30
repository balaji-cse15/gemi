"""Tool result cache — LRU cache for SAFE read-only tool calls within a turn.

When the model reads the same file twice (or runs the same grep query twice)
in a single turn, we serve the result from cache to save time and avoid
re-running the I/O. Writes invalidate the cache.

Cache is per-turn by default (cleared between turns) but can be tagged
"sticky" to persist for the whole session.

Stats are tracked for observability via /cache command.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


SAFE_CACHEABLE = {
    "read_file", "glob", "grep", "tree", "diff",
    "json_parse", "yaml_parse", "toml_parse", "xml_parse", "csv_parse",
    "code_analysis", "url_parse", "regex",
}

# Tools whose output should NEVER cache (results time-sensitive)
NEVER_CACHE = {
    "timestamp", "uuid", "secrets_gen", "system_info", "env",
    "process", "clipboard", "screenshot", "ping", "watch",
    "web_fetch", "http_request", "download", "dns_lookup",
    "port_scan", "whois", "subdomain", "header_analysis",
    "bash", "powershell", "python_run", "git",
}


@dataclass
class CacheEntry:
    output: str
    is_error: bool
    created: float
    hits: int = 0


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    saved_seconds: float = 0.0
    bytes_served: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total else 0.0


class ToolCache:
    """Bounded LRU cache for tool call results."""

    def __init__(self, max_entries: int = 256, ttl_seconds: int = 600):
        self.max_entries = max_entries
        self.ttl = ttl_seconds
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self.stats = CacheStats()
        self.enabled = True

    @staticmethod
    def _key(tool_name: str, args: dict[str, Any]) -> str:
        canon = json.dumps(args, sort_keys=True, default=str)
        h = hashlib.sha1(f"{tool_name}::{canon}".encode("utf-8")).hexdigest()
        return f"{tool_name}:{h[:16]}"

    def is_cacheable(self, tool_name: str) -> bool:
        if not self.enabled:
            return False
        if tool_name in NEVER_CACHE:
            return False
        return tool_name in SAFE_CACHEABLE

    def get(self, tool_name: str, args: dict[str, Any]) -> CacheEntry | None:
        if not self.is_cacheable(tool_name):
            return None
        key = self._key(tool_name, args)
        entry = self._entries.get(key)
        if not entry:
            self.stats.misses += 1
            return None
        if time.time() - entry.created > self.ttl:
            del self._entries[key]
            self.stats.invalidations += 1
            self.stats.misses += 1
            return None
        # LRU bump
        self._entries.move_to_end(key)
        entry.hits += 1
        self.stats.hits += 1
        self.stats.bytes_served += len(entry.output)
        return entry

    def put(self, tool_name: str, args: dict[str, Any], output: str, is_error: bool, elapsed: float = 0.0) -> None:
        if not self.is_cacheable(tool_name) or is_error:
            return
        # Don't cache truly massive outputs (waste of memory)
        if len(output) > 200_000:
            return
        key = self._key(tool_name, args)
        self._entries[key] = CacheEntry(
            output=output, is_error=is_error, created=time.time(),
        )
        self._entries.move_to_end(key)
        # Track time saved (estimated by tracking original elapsed on first call)
        if elapsed > 0:
            self.stats.saved_seconds += 0.0  # accumulated only on hits
        # Evict oldest if over capacity
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def invalidate_for_write(self, tool_name: str, args: dict[str, Any]) -> int:
        """Invalidate cache entries that may have been affected by a write tool."""
        if tool_name not in {"write_file", "edit_file", "delete_file", "move_file",
                              "copy_file", "multi_edit", "archive", "scaffold",
                              "bash", "powershell", "python_run", "git", "docker",
                              "pip", "npm"}:
            return 0
        # Conservative: invalidate all read_file/glob/grep/tree/diff entries.
        # These are the ones most likely to be stale after a write.
        affected = 0
        keys_to_drop = [
            k for k in self._entries
            if k.split(":", 1)[0] in {"read_file", "glob", "grep", "tree", "diff", "code_analysis"}
        ]
        for k in keys_to_drop:
            del self._entries[k]
            affected += 1
        self.stats.invalidations += affected
        return affected

    def clear(self) -> int:
        n = len(self._entries)
        self._entries.clear()
        return n

    def reset_stats(self) -> None:
        self.stats = CacheStats()

    def __len__(self) -> int:
        return len(self._entries)


# Singleton cache instance per-process (BuddyApp gets one)
_DEFAULT: ToolCache | None = None


def get_cache() -> ToolCache:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ToolCache()
    return _DEFAULT
