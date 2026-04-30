"""PortScanTool — check if local ports are open/listening."""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class PortScanTool(Tool):
    name = "port_scan"
    description = (
        "Check if local TCP ports are open/listening. "
        "Useful for verifying services are running (dev servers, databases, agent proxies)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "ports": {
                "type": "string",
                "description": "Comma-separated port numbers or range (e.g. '8080', '3000,5432', '8001-8010').",
            },
            "host": {
                "type": "string",
                "description": "Host to check (default 'localhost').",
                "default": "localhost",
            },
            "timeout": {
                "type": "number",
                "description": "Connection timeout in seconds (default 1).",
                "default": 1,
            },
        },
        "required": ["ports"],
    }

    def _parse_ports(self, ports_str: str) -> list[int]:
        ports = []
        for part in ports_str.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    for p in range(int(start), int(end) + 1):
                        ports.append(p)
                except ValueError:
                    continue
            else:
                try:
                    ports.append(int(part))
                except ValueError:
                    continue
        return ports

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        ports_str = kwargs.get("ports", "")
        host = kwargs.get("host", "localhost")
        timeout = float(kwargs.get("timeout", 1))

        if not ports_str:
            return ToolResult.fail("No ports provided.")

        ports = self._parse_ports(ports_str)
        if not ports:
            return ToolResult.fail("No valid port numbers found.")

        if len(ports) > 100:
            return ToolResult.fail("Too many ports (max 100).")

        results = []
        open_count = 0
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    results.append(f"  {port:>5d}  OPEN")
                    open_count += 1
                else:
                    results.append(f"  {port:>5d}  CLOSED")
            except socket.error:
                results.append(f"  {port:>5d}  ERROR")

        header = f"Host: {host} — {open_count}/{len(ports)} ports open"
        return ToolResult.ok(header + "\n" + "\n".join(results))
