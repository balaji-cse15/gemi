"""Reconnaissance suite — passive + light-active recon for authorized targets.

Tools:
  recon_subdomains   crt.sh certificate transparency lookup (passive, no key)
  recon_dns          DNS records: A, AAAA, MX, NS, TXT, CAA, SOA, SPF, DMARC
  recon_asn          ASN/IP ownership (BGPview, free)
  recon_fingerprint  Web tech fingerprinting (server, framework, headers)
  recon_robots       Fetch robots.txt + sitemap.xml + .well-known
  recon_email        Email enumeration via Hunter free tier hints + breach-data lookup notes
  recon_ports        Connect-scan with banner grabbing (single host)
  recon_whois        Lightweight WHOIS via RDAP (no whois binary needed)
"""
from __future__ import annotations

import json
import re
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .base import Tool, ToolResult


_UA = "Mozilla/5.0 (Gemi recon)"


def _http_json(url: str, params: dict | None = None,
               headers: dict | None = None, timeout: int = 15) -> tuple[Any, str]:
    h = {"User-Agent": _UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    try:
        r = httpx.get(url, params=params, headers=h, timeout=timeout, follow_redirects=True)
    except Exception as e:
        return None, f"request failed: {e}"
    if r.status_code >= 400:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    try:
        return r.json(), ""
    except Exception:
        return r.text, ""


# ---------------------------------------------------------------- subdomain enum

class ReconSubdomainsTool(Tool):
    name = "recon_subdomains"
    dangerous = True
    description = (
        "AUTHORIZED USE ONLY. Subdomain enumeration via crt.sh (certificate transparency logs). "
        "Passive recon — does NOT touch the target. Free, no API key."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "Apex domain (e.g. example.com)"},
            "wildcard": {"type": "boolean", "description": "Include %.domain wildcards", "default": True},
        },
        "required": ["domain"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        domain = (kwargs.get("domain") or "").strip().lower()
        if not domain:
            return ToolResult.fail("missing domain")
        wildcard = kwargs.get("wildcard", True)
        q = f"%.{domain}" if wildcard else domain
        data, err = _http_json("https://crt.sh/", params={"q": q, "output": "json"}, timeout=30)
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, list):
            return ToolResult.fail("crt.sh returned non-list")
        # Dedupe and clean
        subs: set[str] = set()
        for entry in data:
            name = entry.get("name_value", "")
            for n in name.split("\n"):
                n = n.strip().lower()
                if n and "*" not in n and (n.endswith("." + domain) or n == domain):
                    subs.add(n)
        if not subs:
            return ToolResult.ok(f"# {domain}\n(no subdomains found in crt.sh)")
        sorted_subs = sorted(subs)
        out = [f"# Subdomains for {domain}  ({len(sorted_subs)} unique)"]
        for s in sorted_subs:
            out.append(f"  {s}")
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- DNS records

class ReconDnsTool(Tool):
    name = "recon_dns"
    dangerous = True
    description = (
        "AUTHORIZED USE ONLY. DNS record lookup via Cloudflare's DoH endpoint (no extra deps). "
        "Returns A, AAAA, MX, NS, TXT, CAA, SOA in one call."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {"type": "string"},
            "types": {"type": "string", "description": "Comma-separated record types. Default: 'A,AAAA,MX,NS,TXT,CAA,SOA'"},
        },
        "required": ["domain"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        domain = (kwargs.get("domain") or "").strip().lower()
        if not domain:
            return ToolResult.fail("missing domain")
        types_str = kwargs.get("types") or "A,AAAA,MX,NS,TXT,CAA,SOA"
        record_types = [t.strip().upper() for t in types_str.split(",") if t.strip()]

        out = [f"# DNS — {domain}\n"]
        for rt in record_types:
            data, err = _http_json(
                "https://cloudflare-dns.com/dns-query",
                params={"name": domain, "type": rt},
                headers={"Accept": "application/dns-json"},
                timeout=10,
            )
            if err or not isinstance(data, dict):
                out.append(f"  {rt:<6} (error: {err or 'no data'})")
                continue
            answers = data.get("Answer", []) or []
            if not answers:
                out.append(f"  {rt:<6} (no records)")
                continue
            out.append(f"  {rt}:")
            for a in answers:
                ttl = a.get("TTL", "?")
                rdata = a.get("data", "")
                out.append(f"    {ttl:>5}s  {rdata}")
        # Special: SPF and DMARC
        for special_name, special_query in [("SPF (TXT)", domain), ("DMARC", f"_dmarc.{domain}")]:
            data, _ = _http_json(
                "https://cloudflare-dns.com/dns-query",
                params={"name": special_query, "type": "TXT"},
                headers={"Accept": "application/dns-json"},
                timeout=8,
            )
            if isinstance(data, dict):
                for ans in data.get("Answer", []) or []:
                    rdata = ans.get("data", "")
                    if special_name.startswith("SPF") and "v=spf1" not in rdata:
                        continue
                    out.append(f"  {special_name}: {rdata[:200]}")
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- ASN/IP info

class ReconAsnTool(Tool):
    name = "recon_asn"
    dangerous = True
    description = "ASN/IP ownership via BGPview API (free, no key). Pass an IP, ASN, or domain."
    input_schema = {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "IP, ASN (e.g. AS15169), or domain"},
        },
        "required": ["target"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        target = (kwargs.get("target") or "").strip()
        if not target:
            return ToolResult.fail("missing target")

        if target.upper().startswith("AS"):
            url = f"https://api.bgpview.io/asn/{target[2:]}"
        elif re.match(r"^\d+\.\d+\.\d+\.\d+$", target):
            url = f"https://api.bgpview.io/ip/{target}"
        elif ":" in target:  # IPv6 best guess
            url = f"https://api.bgpview.io/ip/{target}"
        else:
            # Resolve domain → IP first
            try:
                ip = socket.gethostbyname(target)
                url = f"https://api.bgpview.io/ip/{ip}"
            except Exception as e:
                return ToolResult.fail(f"could not resolve {target}: {e}")

        data, err = _http_json(url, timeout=20)
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, dict) or data.get("status") != "ok":
            return ToolResult.fail("BGPview returned error")
        d = data.get("data", {})
        return ToolResult.ok(json.dumps(d, indent=2)[:6000])


# ---------------------------------------------------------------- web fingerprint

class ReconFingerprintTool(Tool):
    name = "recon_fingerprint"
    dangerous = True
    description = (
        "AUTHORIZED USE ONLY. Web tech fingerprinting: probes a URL and infers server, framework, "
        "JS libraries, CMS, CDN, and security headers from response signatures."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
        },
        "required": ["url"],
    }

    _SIGNATURES = {
        # header-based
        "x-powered-by": "framework-via-header",
        "server": "server-via-header",
        "x-aspnet-version": "ASP.NET",
        "x-aspnetmvc-version": "ASP.NET MVC",
        "x-rails-runtime": "Rails",
        "x-drupal-cache": "Drupal",
        "x-generator": "framework-via-header",
        # cookie-based
        "phpsessid": "PHP",
        "jsessionid": "Java",
        "asp.net_sessionid": "ASP.NET",
        "ci_session": "CodeIgniter",
        "laravel_session": "Laravel",
    }

    _BODY_SIGNATURES = {
        "wp-content": "WordPress",
        "wp-includes": "WordPress",
        "/_next/": "Next.js",
        "__NEXT_DATA__": "Next.js",
        "data-react-helmet": "React",
        "ng-version": "Angular",
        "data-vue-meta": "Vue.js",
        "drupal-settings-json": "Drupal",
        "joomla": "Joomla",
        "shopify": "Shopify",
        "/_nuxt/": "Nuxt",
        "svelte-": "Svelte",
        "/wp-json/": "WordPress",
        "type=\"text/x-stripe\"": "Stripe",
        "googletagmanager.com/gtm.js": "Google Tag Manager",
        "cdn.jsdelivr.net": "jsDelivr CDN",
        "cdnjs.cloudflare.com": "cdnjs",
        "fastly": "Fastly CDN",
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

        out = [f"# Fingerprint — {r.url}", ""]
        out.append(f"  status:    {r.status_code}")
        out.append(f"  redirects: {len(r.history)}")
        out.append(f"  size:      {len(r.content):,} bytes")
        out.append(f"  ttfb:      {r.elapsed.total_seconds()*1000:.0f}ms")

        # Headers
        out.append("\n## Server / framework")
        techs: set[str] = set()
        for h, v in r.headers.items():
            hl = h.lower()
            if hl in {"server", "x-powered-by", "x-generator",
                      "x-aspnet-version", "x-aspnetmvc-version", "x-rails-runtime",
                      "x-drupal-cache", "x-drupal-dynamic-cache"}:
                out.append(f"  {h}: {v}")
                techs.add(v)

        # Cookie hints
        cookie_hdr = r.headers.get("set-cookie", "").lower()
        for marker, tech in [("phpsessid", "PHP"), ("jsessionid", "Java"),
                              ("asp.net_sessionid", "ASP.NET"),
                              ("laravel_session", "Laravel"),
                              ("connect.sid", "Express/Node")]:
            if marker in cookie_hdr:
                techs.add(tech)

        # Body signatures
        body = r.text[:50000]
        for sig, tech in self._BODY_SIGNATURES.items():
            if sig in body:
                techs.add(tech)

        if techs:
            out.append("\n## Detected")
            for t in sorted(techs):
                out.append(f"  • {t}")

        # Security headers audit
        sec = {
            "Content-Security-Policy":   r.headers.get("content-security-policy", ""),
            "Strict-Transport-Security": r.headers.get("strict-transport-security", ""),
            "X-Frame-Options":           r.headers.get("x-frame-options", ""),
            "X-Content-Type-Options":    r.headers.get("x-content-type-options", ""),
            "Referrer-Policy":           r.headers.get("referrer-policy", ""),
            "Permissions-Policy":        r.headers.get("permissions-policy", ""),
        }
        out.append("\n## Security headers")
        for k, v in sec.items():
            mark = "✓" if v else "✗"
            shown = (v[:80] + "…") if len(v) > 80 else (v or "(missing)")
            out.append(f"  [{mark}]  {k}: {shown}")

        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- robots / sitemap

class ReconRobotsTool(Tool):
    name = "recon_robots"
    dangerous = True
    description = (
        "AUTHORIZED USE ONLY. Fetch robots.txt, sitemap.xml, and probe common .well-known endpoints "
        "(security.txt, change-password, openid-configuration, etc.)."
    )
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    _WELL_KNOWN = [
        "security.txt", "change-password", "openid-configuration",
        "oauth-authorization-server", "openpgpkey/policy",
        "host-meta", "webfinger", "assetlinks.json",
        "apple-app-site-association",
    ]

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        out = [f"# {base}\n"]

        # robots.txt
        try:
            r = httpx.get(f"{base}/robots.txt", timeout=10, follow_redirects=True)
            if r.status_code == 200 and r.text.strip():
                out.append("## robots.txt")
                for line in r.text.splitlines()[:80]:
                    out.append(f"  {line}")
                out.append("")
        except Exception:
            pass

        # sitemap.xml
        try:
            r = httpx.get(f"{base}/sitemap.xml", timeout=10, follow_redirects=True)
            if r.status_code == 200 and r.text.strip():
                out.append("## sitemap.xml")
                # Extract <loc> tags
                locs = re.findall(r"<loc>([^<]+)</loc>", r.text[:200000])
                for loc in locs[:30]:
                    out.append(f"  {loc}")
                if len(locs) > 30:
                    out.append(f"  … ({len(locs) - 30} more)")
                out.append("")
        except Exception:
            pass

        # .well-known
        out.append("## .well-known")
        for path in self._WELL_KNOWN:
            try:
                r = httpx.get(f"{base}/.well-known/{path}", timeout=8, follow_redirects=False)
                if r.status_code < 400:
                    out.append(f"  [{r.status_code}]  /.well-known/{path}  ({len(r.content)} bytes)")
            except Exception:
                continue
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- port scan + banner

class ReconPortsTool(Tool):
    name = "recon_ports"
    dangerous = True
    description = (
        "AUTHORIZED USE ONLY. Connect-scan + banner grab on a single host. Pass a port range "
        "(e.g. '1-1024') or comma list (e.g. '22,80,443,3306,8080'). "
        "Authorized targets only."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string"},
            "ports": {"type": "string", "default": "21,22,23,25,53,80,110,143,443,445,587,993,995,3306,3389,5432,5900,6379,8080,8443,9200,11211,27017"},
            "timeout": {"type": "number", "default": 1.5},
            "concurrency": {"type": "integer", "default": 30},
        },
        "required": ["host"],
    }

    @staticmethod
    def _parse_ports(spec: str) -> list[int]:
        out: list[int] = []
        for part in spec.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    out.extend(range(int(a), int(b) + 1))
                except ValueError:
                    continue
            elif part:
                try:
                    out.append(int(part))
                except ValueError:
                    continue
        return [p for p in out if 0 < p < 65536]

    @staticmethod
    def _scan_port(host: str, port: int, timeout: float) -> dict | None:
        try:
            with socket.create_connection((host, port), timeout=timeout) as s:
                # Try to grab a banner — short read with quick timeout
                s.settimeout(min(timeout, 1.0))
                try:
                    if port in (80, 8080, 8000):
                        s.sendall(f"HEAD / HTTP/1.0\r\nHost: {host}\r\n\r\n".encode())
                    elif port in (443, 8443):
                        # Skip plaintext banner for TLS — just return port open
                        return {"port": port, "banner": "(TLS)", "service": _SERVICE.get(port, "")}
                    banner = s.recv(512)
                    return {
                        "port": port,
                        "banner": banner.decode(errors="replace").strip()[:200] or "(open, no banner)",
                        "service": _SERVICE.get(port, ""),
                    }
                except Exception:
                    return {"port": port, "banner": "(open, no banner)", "service": _SERVICE.get(port, "")}
        except (socket.timeout, ConnectionRefusedError, OSError):
            return None

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        host = (kwargs.get("host") or "").strip()
        if not host:
            return ToolResult.fail("missing host")
        ports = self._parse_ports(kwargs.get("ports") or "")
        timeout = float(kwargs.get("timeout", 1.5))
        concurrency = max(1, min(int(kwargs.get("concurrency", 30)), 100))
        if not ports:
            return ToolResult.fail("no valid ports")

        try:
            ip = socket.gethostbyname(host)
        except Exception as e:
            return ToolResult.fail(f"resolve failed: {e}")

        results = []
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self._scan_port, host, p, timeout): p for p in ports}
            for fut in as_completed(futures):
                r = fut.result()
                if r:
                    results.append(r)
        results.sort(key=lambda r: r["port"])

        out = [f"# Port scan — {host} ({ip})\n"]
        out.append(f"  Scanned {len(ports)} ports — {len(results)} open\n")
        for r in results:
            svc = f"  ({r['service']})" if r["service"] else ""
            out.append(f"  {r['port']:>5}/tcp  open{svc}")
            if r["banner"] not in ("(TLS)", "(open, no banner)"):
                first_line = r["banner"].splitlines()[0][:120]
                out.append(f"          banner: {first_line}")
        return ToolResult.ok("\n".join(out))


_SERVICE = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns",
    80: "http", 110: "pop3", 143: "imap", 443: "https",
    445: "smb", 587: "smtp-submission", 993: "imaps", 995: "pop3s",
    1433: "mssql", 3306: "mysql", 3389: "rdp", 5432: "postgres",
    5900: "vnc", 6379: "redis", 8080: "http-alt", 8443: "https-alt",
    9200: "elasticsearch", 11211: "memcached", 27017: "mongodb",
}


# ---------------------------------------------------------------- WHOIS via RDAP

class ReconWhoisRdapTool(Tool):
    name = "recon_whois"
    dangerous = True
    description = (
        "AUTHORIZED USE ONLY. Lightweight WHOIS via RDAP (no whois binary needed). Domain or IP. "
        "Uses rdap.org redirect service."
    )
    input_schema = {
        "type": "object",
        "properties": {"target": {"type": "string"}},
        "required": ["target"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        target = (kwargs.get("target") or "").strip()
        if not target:
            return ToolResult.fail("missing target")
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", target):
            url = f"https://rdap.org/ip/{target}"
        else:
            url = f"https://rdap.org/domain/{target}"
        data, err = _http_json(url, timeout=20)
        if err:
            return ToolResult.fail(err)
        if not isinstance(data, dict):
            return ToolResult.fail("unexpected RDAP response")

        out = [f"# WHOIS (RDAP) — {target}\n"]
        if "ldhName" in data:
            out.append(f"  domain: {data['ldhName']}")
        for ev in data.get("events", []) or []:
            out.append(f"  {ev.get('eventAction'):<22} {ev.get('eventDate', '')}")
        for ent in data.get("entities", []) or []:
            roles = ",".join(ent.get("roles", []))
            handle = ent.get("handle", "")
            out.append(f"  entity {handle} [{roles}]")
            for v in (ent.get("vcardArray") or [None, []])[1]:
                if isinstance(v, list) and len(v) >= 4 and v[0] in ("fn", "org", "email", "tel"):
                    out.append(f"    {v[0]}: {v[3]}")
        out.append(f"  status: {', '.join(data.get('status', []) or [])}")
        out.append(f"  ns: {', '.join(ns.get('ldhName','') for ns in data.get('nameservers', []) or [])}")
        return ToolResult.ok("\n".join(out))


RECON_TOOLS = [
    ReconSubdomainsTool(),
    ReconDnsTool(),
    ReconAsnTool(),
    ReconFingerprintTool(),
    ReconRobotsTool(),
    ReconPortsTool(),
    ReconWhoisRdapTool(),
]
