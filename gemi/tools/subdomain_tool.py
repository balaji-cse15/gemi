"""SubdomainTool — enumerate subdomains via DNS brute force."""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

COMMON_SUBDOMAINS = [
    "www", "mail", "ftp", "localhost", "webmail", "smtp", "pop", "ns1", "ns2",
    "dns", "dns1", "dns2", "mx", "mx1", "mx2", "blog", "dev", "staging", "api",
    "app", "admin", "portal", "shop", "store", "test", "demo", "beta", "alpha",
    "cdn", "static", "assets", "img", "images", "media", "files", "docs",
    "wiki", "help", "support", "status", "monitor", "git", "gitlab", "jenkins",
    "ci", "cd", "deploy", "prod", "production", "stage", "qa", "uat",
    "vpn", "remote", "proxy", "gateway", "auth", "sso", "login", "signup",
    "dashboard", "panel", "console", "manage", "manager", "internal",
    "intranet", "extranet", "db", "database", "mysql", "postgres", "redis",
    "elastic", "search", "log", "logs", "metrics", "grafana", "prometheus",
    "kibana", "vault", "secrets", "backup", "archive", "old", "legacy",
    "new", "v2", "v3", "next", "preview", "sandbox", "playground",
    "ws", "websocket", "socket", "realtime", "push", "webhook",
    "m", "mobile", "android", "ios", "web", "www2", "www3",
]


class SubdomainTool(Tool):
    name = "subdomain"
    description = (
        "Enumerate subdomains for a domain via DNS resolution. "
        "Tests common subdomain names against DNS."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Base domain to enumerate (e.g. 'example.com').",
            },
            "wordlist": {
                "type": "string",
                "description": "Path to custom subdomain wordlist (one per line).",
            },
            "timeout": {
                "type": "number",
                "description": "DNS timeout per query in seconds (default 1).",
                "default": 1,
            },
        },
        "required": ["domain"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        domain = kwargs.get("domain", "").strip()
        wordlist = kwargs.get("wordlist", "")
        timeout = float(kwargs.get("timeout", 1))

        if not domain:
            return ToolResult.fail("No domain provided.")

        subs = list(COMMON_SUBDOMAINS)
        if wordlist:
            fp = Path(wordlist) if Path(wordlist).is_absolute() else workspace / wordlist
            if fp.is_file():
                try:
                    subs.extend(fp.read_text().splitlines()[:5000])
                except Exception:
                    pass

        socket.setdefaulttimeout(timeout)
        found = []

        for sub in subs:
            sub = sub.strip().lower()
            if not sub:
                continue
            fqdn = f"{sub}.{domain}"
            try:
                ip = socket.gethostbyname(fqdn)
                found.append((fqdn, ip))
            except (socket.gaierror, socket.timeout, OSError):
                continue

        if not found:
            return ToolResult.ok(f"No subdomains found for {domain} ({len(subs)} tested).")

        lines = [f"Found {len(found)} subdomains for {domain}:"]
        for fqdn, ip in sorted(found):
            lines.append(f"  {fqdn:40s} -> {ip}")
        lines.append(f"\nTested {len(subs)} subdomain names.")
        return ToolResult.ok("\n".join(lines))
