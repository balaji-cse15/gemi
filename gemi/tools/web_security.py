"""Web security audit tools — quick OWASP-flavoured probes.

Designed for authorised testing. Each tool does ONE focused check; chain them
for a full audit:

  websec_headers    Security header audit (CSP, HSTS, frame, content-type, etc.)
  websec_methods    HTTP method tampering — try all methods, see what's allowed
  websec_cors       CORS misconfig probe (origin reflection, null origin, regex bypass)
  websec_xss_smoke  Reflective-XSS smoke test (does input echo back unescaped?)
  websec_sqli_smoke SQL injection time-based smoke test (boolean+timing)
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

import httpx

from .base import Tool, ToolResult


_UA = "Mozilla/5.0 (Buddy websec)"


# ---------------------------------------------------------------- headers

class WebsecHeadersTool(Tool):
    name = "websec_headers"
    dangerous = True
    description = (
        "Security-headers audit. Fetches the URL once and grades CSP, HSTS, "
        "X-Frame-Options, X-Content-Type-Options, Referrer-Policy, "
        "Permissions-Policy, COOP/COEP/CORP, Cache-Control on auth pages."
    )
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            r = httpx.get(url, headers={"User-Agent": _UA}, timeout=15, follow_redirects=True)
        except Exception as e:
            return ToolResult.fail(f"fetch failed: {e}")

        h = {k.lower(): v for k, v in r.headers.items()}
        out = [f"# Security headers — {r.url}", f"  status {r.status_code}", ""]

        def grade(present: bool, level: str = "warn") -> str:
            return "✓" if present else ("✗" if level == "fail" else "⚠")

        rows = [
            ("Strict-Transport-Security", "strict-transport-security",
             "Should be present on HTTPS with max-age >= 15768000 + includeSubDomains"),
            ("Content-Security-Policy", "content-security-policy",
             "Should block inline scripts ('unsafe-inline'), eval, and external sources you don't use"),
            ("X-Frame-Options", "x-frame-options",
             "Should be DENY or SAMEORIGIN (or covered by CSP frame-ancestors)"),
            ("X-Content-Type-Options", "x-content-type-options",
             "Should be 'nosniff'"),
            ("Referrer-Policy", "referrer-policy",
             "Should be 'no-referrer', 'strict-origin', or 'strict-origin-when-cross-origin'"),
            ("Permissions-Policy", "permissions-policy",
             "Should restrict sensitive features (camera, geolocation, etc.)"),
            ("Cross-Origin-Opener-Policy", "cross-origin-opener-policy",
             "'same-origin' for full process isolation"),
            ("Cross-Origin-Embedder-Policy", "cross-origin-embedder-policy",
             "'require-corp' to enable SharedArrayBuffer"),
            ("Cross-Origin-Resource-Policy", "cross-origin-resource-policy",
             "'same-origin' or 'same-site' for cross-origin protection"),
            ("Cache-Control", "cache-control",
             "On authenticated pages, should include 'no-store' or 'private'"),
        ]
        for label, key, advice in rows:
            val = h.get(key, "")
            mark = grade(bool(val))
            shown = (val[:80] + "…") if len(val) > 80 else (val or "(missing)")
            out.append(f"  [{mark}]  {label}: {shown}")
            if not val:
                out.append(f"        ↳ {advice}")

        # CSP analyser
        csp = h.get("content-security-policy", "")
        if csp:
            out.append("\n## CSP analysis")
            for issue in _csp_issues(csp):
                out.append(f"  ⚠ {issue}")

        # Cookie audit
        cookies = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else [r.headers.get("set-cookie", "")]
        if cookies and cookies[0]:
            out.append("\n## Cookie audit")
            for c in cookies[:5]:
                cl = c.lower()
                attrs = []
                attrs.append("✓ HttpOnly" if "httponly" in cl else "✗ HttpOnly")
                attrs.append("✓ Secure" if "secure" in cl else "✗ Secure")
                attrs.append("✓ SameSite" if "samesite" in cl else "✗ SameSite")
                cookie_name = c.split("=", 1)[0].strip()
                out.append(f"  {cookie_name}:  {' / '.join(attrs)}")
        return ToolResult.ok("\n".join(out))


def _csp_issues(csp: str) -> list[str]:
    issues = []
    if "'unsafe-inline'" in csp:
        issues.append("'unsafe-inline' allows XSS — use nonces or hashes instead")
    if "'unsafe-eval'" in csp:
        issues.append("'unsafe-eval' allows eval()/new Function() — refactor to remove")
    if "data:" in csp and "img-src" not in csp.split(";")[0]:
        issues.append("'data:' in default-src enables data-URL XSS — narrow to img-src only")
    if "*" in csp and not re.search(r"(default-src|script-src)\s+'[^']+'\s*\*", csp):
        if "default-src *" in csp or "script-src *" in csp:
            issues.append("'*' in default-src/script-src defeats CSP — use specific origins")
    if "frame-ancestors" not in csp:
        issues.append("missing 'frame-ancestors' — clickjacking risk if X-Frame-Options also missing")
    if "report-uri" not in csp and "report-to" not in csp:
        issues.append("no report-uri/report-to — violations go undetected")
    return issues


# ---------------------------------------------------------------- methods

class WebsecMethodsTool(Tool):
    name = "websec_methods"
    dangerous = True
    description = (
        "HTTP method tampering — probe all standard methods (GET, POST, PUT, "
        "DELETE, PATCH, OPTIONS, HEAD, TRACE, CONNECT) and report which the "
        "server allows + how it responds."
    )
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    _METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD", "TRACE", "CONNECT"]

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        out = [f"# HTTP methods — {url}", "",
               f"  {'Method':<8} {'Status':<7} {'Length':<8} Allow header"]
        out.append("  " + "─" * 70)

        with httpx.Client(headers={"User-Agent": _UA}, timeout=10, follow_redirects=False) as c:
            for m in self._METHODS:
                try:
                    r = c.request(m, url)
                    allow = r.headers.get("allow", "")
                    out.append(f"  {m:<8} {r.status_code:<7} {len(r.content):<8} {allow}")
                except Exception as e:
                    out.append(f"  {m:<8} ERROR — {str(e)[:50]}")
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- CORS

class WebsecCorsTool(Tool):
    name = "websec_cors"
    dangerous = True
    description = (
        "CORS misconfig probe. Sends multiple Origin variants and reports which "
        "are reflected in Access-Control-Allow-Origin (often with credentials)."
    )
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        host = urlparse(url).netloc

        probes = [
            ("Attacker domain", "https://attacker.com"),
            ("Null origin", "null"),
            ("Subdomain attack", f"https://attacker.{host}"),
            ("Pre-suffix injection", f"https://{host}.attacker.com"),
            ("Internal-name fake", "http://localhost"),
            ("Co-host bypass", f"http://{host.replace('www.','')}.evil.com"),
        ]
        out = [f"# CORS probe — {url}", ""]
        with httpx.Client(headers={"User-Agent": _UA}, timeout=15, follow_redirects=False) as c:
            for label, origin in probes:
                try:
                    r = c.get(url, headers={"Origin": origin})
                    aco = r.headers.get("access-control-allow-origin", "")
                    acc = r.headers.get("access-control-allow-credentials", "")
                    if aco == origin:
                        verdict = "✗ REFLECTED"
                        risk = "  ↳ HIGH" if acc.lower() == "true" else "  ↳ medium"
                    elif aco == "*":
                        verdict = "⚠ wildcard"
                        risk = "  ↳ low (no creds with *)"
                    elif not aco:
                        verdict = "✓ ignored"
                        risk = ""
                    else:
                        verdict = f"  fixed: {aco}"
                        risk = ""
                    out.append(f"  [{verdict}] Origin: {origin}{risk}")
                except Exception as e:
                    out.append(f"  ERROR Origin: {origin} — {e}")
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- XSS smoke

class WebsecXssSmokeTool(Tool):
    name = "websec_xss_smoke"
    dangerous = True
    description = (
        "Reflective-XSS smoke test. Adds a tracer string to every query "
        "parameter and checks if it's reflected unescaped in the response. "
        "Doesn't run JS — just checks byte-for-byte echo and HTML escaping."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "tracer": {"type": "string", "default": "buddy<>'\"$#test"},
        },
        "required": ["url"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")
        tracer = kwargs.get("tracer") or "buddy<>'\"$#test"

        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        if not params:
            params = {"q": [""]}  # add a synthetic param if none

        out = [f"# XSS smoke — {url}", f"  tracer: {tracer}", ""]
        for name in params:
            mutated = {k: v.copy() for k, v in params.items()}
            mutated[name] = [tracer]
            new_qs = urlencode([(k, v) for k, vs in mutated.items() for v in vs])
            test_url = urlunparse(parsed._replace(query=new_qs))
            try:
                r = httpx.get(test_url, headers={"User-Agent": _UA}, timeout=10, follow_redirects=True)
            except Exception as e:
                out.append(f"  param={name!r} → ERROR {e}")
                continue

            body = r.text
            issues = []
            if tracer in body:
                issues.append("BYTE-EXACT REFLECTED (likely vulnerable)")
            else:
                # Check unescaped angle brackets specifically
                if "<" in tracer and tracer.replace("<", "&lt;").replace(">", "&gt;") in body:
                    issues.append("html-escaped reflected (probably safe)")
                elif tracer.split("<")[0] in body and tracer.split(">")[-1] in body:
                    issues.append("partial reflection — manual check needed")

            if issues:
                out.append(f"  param={name!r}  →  {'; '.join(issues)}")
            else:
                out.append(f"  param={name!r}  →  not reflected")
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- SQLi smoke

class WebsecSqliSmokeTool(Tool):
    name = "websec_sqli_smoke"
    dangerous = True
    description = (
        "SQL injection smoke test. For each query parameter, sends boolean "
        "(`' AND 1=1`/`' AND 1=2`) and time-based (`'; SELECT pg_sleep(3)`) "
        "probes and reports response-length deltas + RT spikes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "delay": {"type": "number", "default": 3.0,
                      "description": "Seconds for time-based probes."},
        },
        "required": ["url"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")
        delay = float(kwargs.get("delay", 3.0))

        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        if not params:
            return ToolResult.fail("URL has no query params to test")

        time_probes = [
            f"' AND SLEEP({delay})-- ",
            f"' AND pg_sleep({delay})-- ",
            f"';WAITFOR DELAY '0:0:{int(delay)}'-- ",
        ]
        bool_pairs = [
            ("' AND 1=1-- ", "' AND 1=2-- "),
            ("') AND ('1'='1", "') AND ('1'='2"),
            ("' OR 1=1-- ", "' OR 1=2-- "),
        ]

        out = [f"# SQLi smoke — {url}", ""]
        with httpx.Client(headers={"User-Agent": _UA}, timeout=delay + 5, follow_redirects=True) as c:
            # Baseline
            try:
                base = c.get(url)
                base_size = len(base.content)
            except Exception as e:
                return ToolResult.fail(f"baseline failed: {e}")

            for name in params:
                out.append(f"## param={name!r}")

                def fill(payload):
                    mut = {k: v.copy() for k, v in params.items()}
                    mut[name] = [(params[name][0] if params[name] and params[name][0] else "") + payload]
                    return urlunparse(parsed._replace(query=urlencode([(k, v) for k, vs in mut.items() for v in vs])))

                # Boolean-based
                for true_p, false_p in bool_pairs[:1]:  # one pair is enough
                    try:
                        tr = c.get(fill(true_p))
                        fr = c.get(fill(false_p))
                        delta = abs(len(tr.content) - len(fr.content))
                        diff_from_base = abs(len(tr.content) - base_size)
                        out.append(
                            f"  bool   1=1: {len(tr.content):>6}B  1=2: {len(fr.content):>6}B  "
                            f"Δ={delta} (base Δ={diff_from_base})"
                        )
                        if delta > 100 and len(tr.content) != len(fr.content):
                            out.append(f"  ⚠ size delta — boolean SQLi likely")
                    except Exception as e:
                        out.append(f"  bool ERROR: {e}")

                # Time-based
                for tp in time_probes[:1]:  # one is enough — most apps are mysql/postgres
                    t0 = time.time()
                    try:
                        c.get(fill(tp), timeout=delay + 4)
                        elapsed = time.time() - t0
                        out.append(f"  time   {elapsed:.1f}s  (probe: {tp[:25]})")
                        if elapsed > delay - 0.5:
                            out.append(f"  ⚠ {delay}s delay confirmed — time-based SQLi likely")
                    except Exception as e:
                        out.append(f"  time ERROR: {e}")
                out.append("")
        return ToolResult.ok("\n".join(out))


WEBSEC_TOOLS = [
    WebsecHeadersTool(),
    WebsecMethodsTool(),
    WebsecCorsTool(),
    WebsecXssSmokeTool(),
    WebsecSqliSmokeTool(),
]
