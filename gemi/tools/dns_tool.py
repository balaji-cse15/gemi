"""DnsLookupTool — DNS resolution for domains."""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class DnsLookupTool(Tool):
    name = "dns_lookup"
    description = (
        "Resolve DNS for a domain name. "
        "Shows IP addresses and reverse DNS. Useful for verifying services and domains."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Domain name to resolve (e.g. 'github.com').",
            },
            "reverse": {
                "type": "boolean",
                "description": "Do reverse DNS on an IP address.",
                "default": False,
            },
        },
        "required": ["domain"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        domain = kwargs.get("domain", "").strip()
        reverse = bool(kwargs.get("reverse", False))

        if not domain:
            return ToolResult.fail("No domain provided.")

        if reverse:
            try:
                hostname, aliases, addrs = socket.gethostbyaddr(domain)
                lines = [f"Reverse DNS for {domain}:"]
                lines.append(f"  Hostname: {hostname}")
                if aliases:
                    lines.append(f"  Aliases:  {', '.join(aliases)}")
                return ToolResult.ok("\n".join(lines))
            except socket.herror as e:
                return ToolResult.fail(f"Reverse DNS failed: {e}")
            except Exception as e:
                return ToolResult.fail(f"Error: {e}")

        try:
            results = socket.getaddrinfo(domain, None)
            seen = set()
            lines = [f"DNS resolution for {domain}:"]
            for family, socktype, proto, canonname, sockaddr in results:
                ip = sockaddr[0]
                if ip in seen:
                    continue
                seen.add(ip)
                family_name = "IPv4" if family == socket.AF_INET else "IPv6"
                lines.append(f"  {family_name}: {ip}")

            if not seen:
                return ToolResult.fail(f"No records found for {domain}")
            return ToolResult.ok("\n".join(lines))
        except socket.gaierror as e:
            return ToolResult.fail(f"DNS resolution failed: {e}")
        except Exception as e:
            return ToolResult.fail(f"Error: {e}")
