"""TimestampTool — convert between epoch, ISO 8601, and human-readable dates."""
from __future__ import annotations

import time as time_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class TimestampTool(Tool):
    name = "timestamp"
    description = (
        "Convert between timestamp formats. "
        "Actions: 'now' (current time in all formats), "
        "'from_epoch' (epoch→human), 'to_epoch' (date→epoch), "
        "'diff' (time between two dates), 'add' (add duration to date)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'now', 'from_epoch', 'to_epoch', 'diff', 'add'.",
                "enum": ["now", "from_epoch", "to_epoch", "diff", "add"],
            },
            "value": {
                "type": "string",
                "description": "Epoch seconds, ISO date, or start date.",
            },
            "value2": {
                "type": "string",
                "description": "End date (for diff action).",
            },
            "days": {"type": "integer", "description": "Days to add (for add action).", "default": 0},
            "hours": {"type": "integer", "description": "Hours to add (for add action).", "default": 0},
            "minutes": {"type": "integer", "description": "Minutes to add.", "default": 0},
        },
        "required": ["action"],
    }

    def _parse_date(self, s: str) -> datetime | None:
        for fmt in [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
        ]:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "now":
            now = datetime.now(timezone.utc)
            local = datetime.now()
            return ToolResult.ok(
                f"UTC:     {now.isoformat()}\n"
                f"Local:   {local.isoformat()}\n"
                f"Epoch:   {int(now.timestamp())}\n"
                f"Epoch ms: {int(now.timestamp() * 1000)}"
            )

        elif action == "from_epoch":
            value = kwargs.get("value", "")
            if not value:
                return ToolResult.fail("value (epoch) required.")
            try:
                ts = float(value)
                if ts > 1e12:
                    ts /= 1000
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                local = datetime.fromtimestamp(ts)
                return ToolResult.ok(
                    f"UTC:   {dt.isoformat()}\n"
                    f"Local: {local.isoformat()}\n"
                    f"Human: {dt.strftime('%A, %B %d, %Y %I:%M:%S %p UTC')}"
                )
            except Exception as e:
                return ToolResult.fail(f"Invalid epoch: {e}")

        elif action == "to_epoch":
            value = kwargs.get("value", "")
            if not value:
                return ToolResult.fail("value (date) required.")
            dt = self._parse_date(value)
            if not dt:
                return ToolResult.fail(f"Could not parse date: {value}")
            epoch = int(dt.timestamp())
            return ToolResult.ok(f"Epoch:    {epoch}\nEpoch ms: {epoch * 1000}")

        elif action == "diff":
            v1 = kwargs.get("value", "")
            v2 = kwargs.get("value2", "")
            if not v1 or not v2:
                return ToolResult.fail("value and value2 required.")
            d1, d2 = self._parse_date(v1), self._parse_date(v2)
            if not d1 or not d2:
                return ToolResult.fail("Could not parse dates.")
            delta = abs(d2 - d1)
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return ToolResult.ok(
                f"Difference: {days}d {hours}h {minutes}m {seconds}s\n"
                f"Total seconds: {int(delta.total_seconds())}\n"
                f"Total hours: {delta.total_seconds() / 3600:.1f}"
            )

        elif action == "add":
            value = kwargs.get("value", "")
            if not value:
                return ToolResult.fail("value (start date) required.")
            dt = self._parse_date(value)
            if not dt:
                return ToolResult.fail(f"Could not parse: {value}")
            delta = timedelta(
                days=int(kwargs.get("days", 0)),
                hours=int(kwargs.get("hours", 0)),
                minutes=int(kwargs.get("minutes", 0)),
            )
            result = dt + delta
            return ToolResult.ok(f"Result: {result.isoformat()}\nEpoch: {int(result.timestamp())}")

        return ToolResult.fail(f"Unknown action: {action}")
