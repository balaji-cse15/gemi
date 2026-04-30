"""API testing toolkit — REST and GraphQL endpoint probes.

Tools:
  api_introspect_graphql   GraphQL introspection (schema discovery)
  api_openapi_discover     Find OpenAPI/Swagger specs at common paths
  api_rate_limit_probe     Send N parallel requests, look for 429s and headers
  api_auth_bypass          Try common auth-bypass headers (X-Forwarded-For, etc.)
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .base import Tool, ToolResult


_UA = "Mozilla/5.0 (Buddy api-test)"


# ---------------------------------------------------------------- GraphQL introspect

INTROSPECTION_QUERY = """{
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind name description
      fields { name description args { name type { kind name ofType { kind name } } } type { kind name ofType { kind name } } }
      inputFields { name type { kind name ofType { kind name } } }
      enumValues { name description }
    }
  }
}"""


class ApiGraphqlIntrospectTool(Tool):
    name = "api_introspect_graphql"
    dangerous = True
    description = (
        "Run a GraphQL introspection query against an endpoint. Returns the "
        "full schema (queries, mutations, types, enums). Useful for finding "
        "hidden mutations or admin types."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "headers": {"type": "object", "description": "Optional headers (e.g. Authorization)"},
        },
        "required": ["url"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")
        h = {"User-Agent": _UA, "Content-Type": "application/json"}
        h.update(kwargs.get("headers") or {})

        try:
            r = httpx.post(url, json={"query": INTROSPECTION_QUERY}, headers=h, timeout=20)
        except Exception as e:
            return ToolResult.fail(f"request failed: {e}")
        if r.status_code >= 400:
            return ToolResult.fail(f"HTTP {r.status_code}: {r.text[:300]}")

        try:
            data = r.json()
        except Exception:
            return ToolResult.fail("non-JSON response — introspection likely disabled")

        schema = (data.get("data") or {}).get("__schema")
        if not schema:
            errs = data.get("errors", [])
            msg = "; ".join(e.get("message", "") for e in errs)
            return ToolResult.fail(f"no schema (errors: {msg or 'unknown'})")

        out = [f"# GraphQL schema — {url}", ""]
        out.append(f"  queryType:        {schema.get('queryType', {}).get('name', '?')}")
        out.append(f"  mutationType:     {(schema.get('mutationType') or {}).get('name', '(none)')}")
        out.append(f"  subscriptionType: {(schema.get('subscriptionType') or {}).get('name', '(none)')}")

        types = [t for t in schema.get("types", []) if not t.get("name", "").startswith("__")]
        out.append(f"\n  total types: {len(types)}")
        # Group by kind
        by_kind: dict[str, list] = {}
        for t in types:
            by_kind.setdefault(t["kind"], []).append(t)

        for kind in ("OBJECT", "INPUT_OBJECT", "ENUM", "INTERFACE", "UNION", "SCALAR"):
            if kind not in by_kind:
                continue
            out.append(f"\n## {kind}")
            for t in sorted(by_kind[kind], key=lambda x: x["name"])[:50]:
                fields = t.get("fields") or t.get("inputFields") or []
                out.append(f"  {t['name']}  ({len(fields) if fields else 0} fields)")

        # List interesting query/mutation fields
        query_type_name = schema.get("queryType", {}).get("name")
        mut_type_name = (schema.get("mutationType") or {}).get("name")
        for label, name in [("Queries", query_type_name), ("Mutations", mut_type_name)]:
            if not name:
                continue
            type_def = next((t for t in types if t["name"] == name), None)
            if not type_def:
                continue
            out.append(f"\n## {label}")
            for f in (type_def.get("fields") or [])[:80]:
                args_str = ", ".join(a["name"] for a in (f.get("args") or [])[:5])
                ret_type = (f.get("type") or {}).get("name") or (f.get("type") or {}).get("ofType", {}).get("name", "?")
                out.append(f"  {f['name']}({args_str}) → {ret_type}")
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- OpenAPI discover

class ApiOpenapiDiscoverTool(Tool):
    name = "api_openapi_discover"
    dangerous = True
    description = (
        "Find OpenAPI/Swagger specs at common paths. Returns list of working "
        "spec URLs and a quick endpoint summary."
    )
    input_schema = {
        "type": "object",
        "properties": {"base_url": {"type": "string"}},
        "required": ["base_url"],
    }

    _PATHS = [
        "/openapi.json", "/openapi.yaml", "/swagger.json", "/swagger.yaml",
        "/api-docs", "/api/docs", "/api/swagger.json",
        "/v1/openapi.json", "/v2/openapi.json", "/v3/api-docs",
        "/swagger-ui.html", "/swagger/index.html", "/docs", "/redoc",
        "/.well-known/openapi.json", "/api/v1/openapi.json",
    ]

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        base = (kwargs.get("base_url") or "").strip().rstrip("/")
        if not base:
            return ToolResult.fail("missing base_url")
        if not base.startswith(("http://", "https://")):
            base = "https://" + base

        out = [f"# OpenAPI discovery — {base}", ""]
        with httpx.Client(headers={"User-Agent": _UA}, timeout=10, follow_redirects=True) as c:
            for path in self._PATHS:
                try:
                    r = c.get(base + path)
                except Exception:
                    continue
                if r.status_code >= 400:
                    continue
                ct = r.headers.get("content-type", "")
                size = len(r.content)
                marker = "spec" if any(k in ct for k in ("json", "yaml")) else "html"
                out.append(f"  [{r.status_code}]  {path}  ({size:,}B, {marker})")

                # Try to parse if json
                if "json" in ct and size < 10_000_000:
                    try:
                        spec = r.json()
                        if "openapi" in spec or "swagger" in spec:
                            paths = spec.get("paths", {})
                            out.append(f"    version: {spec.get('openapi', spec.get('swagger', '?'))}")
                            out.append(f"    title:   {(spec.get('info') or {}).get('title', '?')}")
                            out.append(f"    paths:   {len(paths)}")
                            for p, methods in list(paths.items())[:8]:
                                ms = ",".join(m.upper() for m in methods.keys() if m in
                                              ("get", "post", "put", "delete", "patch"))
                                out.append(f"      {ms:<25} {p}")
                            if len(paths) > 8:
                                out.append(f"      … {len(paths) - 8} more")
                    except Exception:
                        pass
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- rate-limit probe

class ApiRateLimitProbeTool(Tool):
    name = "api_rate_limit_probe"
    dangerous = True
    description = (
        "Send N parallel requests to an endpoint and observe rate-limit "
        "behaviour: 429 status, X-RateLimit-* headers, retry-after."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "count": {"type": "integer", "default": 30},
            "concurrency": {"type": "integer", "default": 10},
        },
        "required": ["url"],
    }

    @staticmethod
    def _one(url: str, idx: int) -> dict:
        try:
            r = httpx.get(url, headers={"User-Agent": _UA}, timeout=10)
            return {
                "idx": idx,
                "status": r.status_code,
                "elapsed_ms": int(r.elapsed.total_seconds() * 1000),
                "rl_limit": r.headers.get("x-ratelimit-limit", ""),
                "rl_remaining": r.headers.get("x-ratelimit-remaining", ""),
                "rl_reset": r.headers.get("x-ratelimit-reset", ""),
                "retry_after": r.headers.get("retry-after", ""),
            }
        except Exception as e:
            return {"idx": idx, "status": -1, "error": str(e)[:60]}

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")
        count = max(1, min(int(kwargs.get("count", 30)), 200))
        concurrency = max(1, min(int(kwargs.get("concurrency", 10)), 50))

        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(self._one, url, i) for i in range(count)]
            for f in as_completed(futures):
                results.append(f.result())
        results.sort(key=lambda r: r["idx"])

        out = [f"# Rate-limit probe — {url}",
               f"  {count} requests, {concurrency} concurrent\n"]
        codes: dict[int, int] = {}
        for r in results:
            codes[r["status"]] = codes.get(r["status"], 0) + 1
        out.append("  status distribution:")
        for code, n in sorted(codes.items()):
            label = ("429 (rate limited)" if code == 429 else
                     "503 (overloaded)" if code == 503 else
                     "200 (ok)" if code == 200 else f"{code}")
            out.append(f"    {label:<24} ×{n}")

        # Show first 429 details
        first_429 = next((r for r in results if r["status"] == 429), None)
        if first_429:
            out.append(f"\n  first 429 at request #{first_429['idx']}")
            for k in ("rl_limit", "rl_remaining", "rl_reset", "retry_after"):
                v = first_429.get(k, "")
                if v:
                    out.append(f"    {k}: {v}")

        # Latency stats
        elapsed = [r["elapsed_ms"] for r in results if "elapsed_ms" in r]
        if elapsed:
            elapsed.sort()
            p50 = elapsed[len(elapsed) // 2]
            p95 = elapsed[int(len(elapsed) * 0.95)]
            out.append(f"\n  latency p50/p95: {p50}/{p95} ms")
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- auth bypass headers

class ApiAuthBypassHeadersTool(Tool):
    name = "api_auth_bypass"
    dangerous = True
    description = (
        "Try common auth-bypass header tricks (X-Forwarded-For, X-Original-URL, "
        "X-Custom-IP-Authorization, etc.) against a forbidden endpoint and "
        "report which ones change the response."
    )
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    _HEADERS = [
        ("X-Forwarded-For", "127.0.0.1"),
        ("X-Real-IP", "127.0.0.1"),
        ("X-Originating-IP", "127.0.0.1"),
        ("X-Remote-IP", "127.0.0.1"),
        ("X-Remote-Addr", "127.0.0.1"),
        ("X-Client-IP", "127.0.0.1"),
        ("X-Forwarded-Host", "localhost"),
        ("X-Original-URL", "/admin"),
        ("X-Rewrite-URL", "/admin"),
        ("X-Custom-IP-Authorization", "127.0.0.1"),
        ("Forwarded", "for=127.0.0.1;proto=https;host=localhost"),
        ("Referer", "https://localhost/admin"),
        ("X-Override-Auth", "true"),
        ("X-Skip-Auth", "1"),
    ]

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        url = (kwargs.get("url") or "").strip()
        if not url:
            return ToolResult.fail("missing url")

        out = [f"# Auth-bypass headers — {url}", ""]
        with httpx.Client(headers={"User-Agent": _UA}, timeout=10, follow_redirects=False) as c:
            try:
                base = c.get(url)
                base_status = base.status_code
                base_size = len(base.content)
            except Exception as e:
                return ToolResult.fail(f"baseline failed: {e}")

            out.append(f"  baseline: {base_status}  {base_size}B")
            out.append("")

            for h, v in self._HEADERS:
                try:
                    r = c.get(url, headers={h: v})
                    delta_status = r.status_code != base_status
                    delta_size = abs(len(r.content) - base_size) > 50
                    flag = "⚠ DIFFERENT" if (delta_status or delta_size) else "  no change"
                    out.append(f"  [{flag}]  {h}: {v}  →  {r.status_code}  {len(r.content)}B")
                except Exception as e:
                    out.append(f"  ERROR  {h}: {v}  →  {e}")
        return ToolResult.ok("\n".join(out))


API_TEST_TOOLS = [
    ApiGraphqlIntrospectTool(),
    ApiOpenapiDiscoverTool(),
    ApiRateLimitProbeTool(),
    ApiAuthBypassHeadersTool(),
]
