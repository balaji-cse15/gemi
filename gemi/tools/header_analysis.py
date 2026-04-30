"""HeaderAnalysisTool — analyze HTTP security headers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

SECURITY_HEADERS = {
    "Strict-Transport-Security": {
        "good": "Present — enforces HTTPS",
        "missing": "MISSING — vulnerable to SSL stripping",
    },
    "Content-Security-Policy": {
        "good": "Present — mitigates XSS and injection",
        "missing": "MISSING — no XSS protection via CSP",
    },
    "X-Content-Type-Options": {
        "good": "Present — prevents MIME sniffing",
        "missing": "MISSING — vulnerable to MIME sniffing",
        "expected": "nosniff",
    },
    "X-Frame-Options": {
        "good": "Present — prevents clickjacking",
        "missing": "MISSING — vulnerable to clickjacking",
    },
    "X-XSS-Protection": {
        "good": "Present (legacy browser XSS filter)",
        "missing": "Missing (not critical with CSP)",
    },
    "Referrer-Policy": {
        "good": "Present — controls referrer leakage",
        "missing": "MISSING — may leak sensitive URL data",
    },
    "Permissions-Policy": {
        "good": "Present — restricts browser features",
        "missing": "MISSING — no feature restrictions",
    },
    "X-Permitted-Cross-Domain-Policies": {
        "good": "Present",
        "missing": "Missing (low risk unless using Flash/PDF plugins)",
    },
}

INFORMATION_HEADERS = ["Server", "X-Powered-By", "X-AspNet-Version", "X-AspNetMvc-Version"]


class HeaderAnalysisTool(Tool):
    name = "header_analysis"
    description = (
        "Fetch and analyze HTTP security headers for a URL. "
        "Checks for missing security headers and information leakage."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to analyze.",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (default 10).",
                "default": 10,
            },
        },
        "required": ["url"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        timeout = int(kwargs.get("timeout", 10))

        if not url:
            return ToolResult.fail("No URL provided.")

        try:
            import httpx
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        except Exception as e:
            return ToolResult.fail(f"Request failed: {e}")

        headers = dict(resp.headers)
        lines = [f"URL: {url}", f"Status: {resp.status_code}", ""]

        lines.append("=== Security Headers ===")
        good = 0
        total = len(SECURITY_HEADERS)
        for header, info in SECURITY_HEADERS.items():
            val = headers.get(header.lower(), headers.get(header, ""))
            if val:
                lines.append(f"  [+] {header}: {val[:80]}")
                lines.append(f"      {info['good']}")
                good += 1
            else:
                lines.append(f"  [-] {header}")
                lines.append(f"      {info['missing']}")

        score = int(good / total * 100)
        lines.append(f"\nScore: {good}/{total} ({score}%)")

        info_leak = []
        for h in INFORMATION_HEADERS:
            val = headers.get(h.lower(), headers.get(h, ""))
            if val:
                info_leak.append(f"  {h}: {val}")

        if info_leak:
            lines.append("\n=== Information Leakage ===")
            lines.extend(info_leak)
            lines.append("  Recommendation: Remove server version headers in production")

        cookies = resp.headers.get_list("set-cookie") if hasattr(resp.headers, "get_list") else []
        if cookies:
            lines.append(f"\n=== Cookies ({len(cookies)}) ===")
            for c in cookies[:5]:
                flags = []
                cl = c.lower()
                if "secure" in cl:
                    flags.append("Secure")
                else:
                    flags.append("NO-Secure")
                if "httponly" in cl:
                    flags.append("HttpOnly")
                else:
                    flags.append("NO-HttpOnly")
                if "samesite" in cl:
                    flags.append("SameSite")
                name = c.split("=")[0].strip()
                lines.append(f"  {name}: {', '.join(flags)}")

        return ToolResult.ok("\n".join(lines))
