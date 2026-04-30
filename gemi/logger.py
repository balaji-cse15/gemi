"""Structured logging — JSONL event stream for replay, debugging, and analytics.

Every interesting buddy event (turn, tool call, hook fire, error, agent switch)
is emitted as a single JSON line to ~/.gemi/logs/buddy-YYYYMMDD.jsonl.

Logs are rotated by day, ring-buffered in memory (last 1000 events), and
streamable via the /logs command.

Disabled by default; enable via:
  - GEMI_LOG=1 environment variable
  - 'logging.enabled: true' in ~/.gemi/config.json
  - logger.enable() at runtime
"""
from __future__ import annotations

import json
import os
import time
import threading
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

LOG_DIR = Path.home() / ".gemi" / "logs"
RING_SIZE = 1000


@dataclass
class LogEvent:
    ts: float = field(default_factory=time.time)
    level: str = "info"   # info, warn, error
    kind: str = ""        # turn.start, turn.end, tool.call, tool.result, hook.fire, ...
    agent: str = ""
    data: dict[str, Any] = field(default_factory=dict)


def _today_path() -> Path:
    return LOG_DIR / f"buddy-{time.strftime('%Y%m%d')}.jsonl"


class _Logger:
    def __init__(self):
        self.enabled: bool = self._initial_enabled()
        self._lock = threading.Lock()
        self._ring: deque[LogEvent] = deque(maxlen=RING_SIZE)
        self._file_handle = None
        self._file_path: Path | None = None

    @staticmethod
    def _initial_enabled() -> bool:
        if os.environ.get("GEMI_LOG"):
            return True
        cfg_file = Path.home() / ".gemi" / "config.json"
        if cfg_file.exists():
            try:
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                return bool(cfg.get("logging", {}).get("enabled", False))
            except Exception:
                return False
        return False

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False
        with self._lock:
            if self._file_handle:
                try:
                    self._file_handle.close()
                except Exception:
                    pass
                self._file_handle = None

    def _ensure_file(self) -> None:
        path = _today_path()
        if self._file_handle and self._file_path == path:
            return
        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file_handle = path.open("a", encoding="utf-8", buffering=1)
        self._file_path = path

    def log(self, kind: str, *, level: str = "info", agent: str = "", **data: Any) -> None:
        event = LogEvent(level=level, kind=kind, agent=agent, data=data)
        with self._lock:
            self._ring.append(event)
            if not self.enabled:
                return
            try:
                self._ensure_file()
                line = json.dumps(asdict(event), default=str, ensure_ascii=False)
                self._file_handle.write(line + "\n")
            except Exception:
                pass  # never let logging crash the app

    def recent(self, limit: int = 50, kind_filter: str = "") -> list[LogEvent]:
        with self._lock:
            events = list(self._ring)
        if kind_filter:
            events = [e for e in events if kind_filter in e.kind]
        return events[-limit:]

    def stats(self) -> dict[str, Any]:
        kind_counts: dict[str, int] = {}
        with self._lock:
            for e in self._ring:
                kind_counts[e.kind] = kind_counts.get(e.kind, 0) + 1
            file_path = str(self._file_path) if self._file_path else ""
            file_size = self._file_path.stat().st_size if self._file_path and self._file_path.exists() else 0
        return {
            "enabled": self.enabled,
            "ring_size": len(self._ring),
            "ring_max": RING_SIZE,
            "kind_counts": kind_counts,
            "file_path": file_path,
            "file_size": file_size,
        }


_INSTANCE: _Logger | None = None


def get_logger() -> _Logger:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = _Logger()
    return _INSTANCE


# --- Convenience helpers ---------------------------------------------

def log(kind: str, **data: Any) -> None:
    get_logger().log(kind, **data)


def log_warn(kind: str, **data: Any) -> None:
    get_logger().log(kind, level="warn", **data)


def log_error(kind: str, **data: Any) -> None:
    get_logger().log(kind, level="error", **data)
