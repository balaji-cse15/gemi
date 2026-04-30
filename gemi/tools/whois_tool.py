"""WhoisTool — domain/IP whois lookup via socket."""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

WHOIS_SERVERS = {
    "com": "whois.verisign-grs.com",
    "net": "whois.verisign-grs.com",
    "org": "whois.pir.org",
    "io": "whois.nic.io",
    "dev": "whois.nic.google",
    "app": "whois.nic.google",
    "ai": "whois.nic.ai",
    "co": "whois.nic.co",
    "me": "whois.nic.me",
    "info": "whois.afilias.net",
    "xyz": "whois.nic.xyz",
}


class WhoisTool(Tool):
    name = "whois"
    description = (
        "Perform WHOIS lookup on a domain name. "
        "Returns registration info, nameservers, and dates."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Domain name to look up (e.g. 'example.com').",
            },
        },
        "required": ["domain"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        domain = kwargs.get("domain", "").strip().lower()
        if not domain:
            return ToolResult.fail("No domain provided.")

        parts = domain.split(".")
        if len(parts) < 2:
            return ToolResult.fail("Invalid domain format.")

        tld = parts[-1]
        server = WHOIS_SERVERS.get(tld, f"whois.nic.{tld}")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((server, 43))
            sock.sendall((domain + "\r\n").encode())
            response = b""
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                response += data
            sock.close()

            text = response.decode("utf-8", errors="replace")
            if len(text) > 5000:
                text = text[:5000] + "\n... (truncated)"
            return ToolResult.ok(f"WHOIS for {domain} (via {server}):\n\n{text}")

        except socket.timeout:
            return ToolResult.fail(f"WHOIS timeout connecting to {server}")
        except socket.gaierror:
            return ToolResult.fail(f"Cannot resolve WHOIS server: {server}")
        except Exception as e:
            return ToolResult.fail(f"WHOIS error: {e}")
