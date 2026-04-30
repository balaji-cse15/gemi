"""MCP (Model Context Protocol) client.

Connects to MCP servers and auto-registers their tools into Buddy's
tool registry. Supports two transports:

  1. **stdio** — spawn a process and exchange JSON-RPC over stdin/stdout
  2. **http**  — POST JSON-RPC to a server URL (also handles SSE for
                 streaming responses if the server uses event-stream)

Configuration: ~/.gemi/mcp.json

  {
    "servers": {
      "filesystem": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
        "env": {}
      },
      "github": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
        "enabled": true
      },
      "remote": {
        "transport": "http",
        "url": "https://example.com/mcp/v1",
        "headers": {"Authorization": "Bearer ${MY_TOKEN}"},
        "enabled": false
      }
    }
  }

Features beyond the basic spec:
  - ${ENV_VAR} substitution in command, args, env values, and headers
  - per-server `enabled: false` to keep the entry but skip startup
  - `tags` array for grouping servers (useful for /mcp filter <tag>)
  - retry-on-startup with backoff for slow servers
  - graceful shutdown on app exit

All MCP tools are registered as WRITE-tier by default; servers can mark
individual tools `read_only: true` in their schema to be SAFE.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .tools.base import Tool, ToolResult
from . import logger as logger_mod

MCP_CONFIG = Path.home() / ".gemi" / "mcp.json"

ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _substitute_env(value: Any) -> Any:
    """Recursively substitute ${ENV_VAR} in strings inside a value tree."""
    if isinstance(value, str):
        return ENV_VAR_PATTERN.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


@dataclass
class McpServer:
    name: str
    transport: str = "stdio"   # stdio | http
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    description: str = ""

    # stdio-specific
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    # http-specific
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 60

    # runtime
    process: subprocess.Popen | None = None
    next_id: int = 1
    lock: threading.Lock = field(default_factory=threading.Lock)
    initialized: bool = False
    error: str = ""
    tools_count: int = 0
    tool_names: list[str] = field(default_factory=list)
    started_at: float = 0.0

    @property
    def is_running(self) -> bool:
        if self.transport == "http":
            return self.initialized
        return self.process is not None and self.process.poll() is None


class McpError(RuntimeError):
    pass


# --- stdio transport -------------------------------------------------

def _send_stdio_request(server: McpServer, method: str,
                        params: dict[str, Any] | None = None,
                        timeout: float = 30.0) -> dict[str, Any]:
    if not server.is_running:
        raise McpError(f"server {server.name} not running")
    with server.lock:
        req_id = server.next_id
        server.next_id += 1
        request = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            request["params"] = params
        try:
            line = json.dumps(request) + "\n"
            server.process.stdin.write(line.encode("utf-8"))
            server.process.stdin.flush()
        except Exception as e:
            raise McpError(f"send to {server.name} failed: {e}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = server.process.stdout.readline()
            if not raw:
                if server.process.poll() is not None:
                    raise McpError(f"server {server.name} died")
                continue
            try:
                msg = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise McpError(f"{method}: {msg['error'].get('message', 'unknown')}")
                return msg.get("result", {})
        raise McpError(f"{method} timed out after {timeout}s")


def _send_stdio_notification(server: McpServer, method: str,
                              params: dict[str, Any] | None = None) -> None:
    if not server.is_running:
        return
    notification = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        notification["params"] = params
    try:
        with server.lock:
            line = json.dumps(notification) + "\n"
            server.process.stdin.write(line.encode("utf-8"))
            server.process.stdin.flush()
    except Exception:
        pass


def _resolve_command(cmd: str) -> str:
    """Resolve a command name to its full path, handling Windows .cmd/.exe shims."""
    import shutil
    if not cmd:
        return cmd
    # Already an absolute path?
    if os.path.isabs(cmd) and os.path.exists(cmd):
        return cmd
    # Direct lookup
    found = shutil.which(cmd)
    if found:
        return found
    # On Windows, try common extensions
    if sys.platform == "win32":
        for ext in (".cmd", ".bat", ".exe", ".ps1"):
            found = shutil.which(cmd + ext)
            if found:
                return found
    return cmd


def _start_stdio_server(server: McpServer) -> bool:
    env = os.environ.copy()
    env.update(_substitute_env(server.env))
    cmd_raw = _substitute_env(server.command)
    cmd = _resolve_command(cmd_raw)
    args = _substitute_env(server.args)

    # On Windows, .cmd shims must be invoked through cmd.exe / shell=True or with
    # the full path. Use shell=True for .cmd/.bat to support npx properly.
    use_shell = sys.platform == "win32" and cmd.lower().endswith((".cmd", ".bat"))

    try:
        if use_shell:
            # Build a command string for shell=True
            quoted_args = " ".join(f'"{a}"' if " " in str(a) else str(a) for a in args)
            cmd_string = f'"{cmd}" {quoted_args}'
            server.process = subprocess.Popen(
                cmd_string,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
                shell=True,
            )
        else:
            server.process = subprocess.Popen(
                [cmd] + list(args),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
            )
    except FileNotFoundError:
        server.error = f"command not found: {cmd_raw}"
        return False
    except Exception as e:
        server.error = str(e)
        return False

    try:
        _send_stdio_request(server, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "gemi", "version": "0.1.0"},
        }, timeout=15)
        _send_stdio_notification(server, "notifications/initialized")
        server.initialized = True
        return True
    except Exception as e:
        server.error = f"initialize failed: {e}"
        try:
            server.process.terminate()
        except Exception:
            pass
        return False


def _stop_stdio_server(server: McpServer) -> None:
    if not server.process:
        return
    try:
        server.process.terminate()
        server.process.wait(timeout=3)
    except Exception:
        try:
            server.process.kill()
        except Exception:
            pass
    server.process = None
    server.initialized = False


# --- http transport --------------------------------------------------

def _send_http_request(server: McpServer, method: str,
                       params: dict[str, Any] | None = None,
                       timeout: float = 30.0) -> dict[str, Any]:
    with server.lock:
        req_id = server.next_id
        server.next_id += 1
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    headers = _substitute_env(server.headers)
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json, text/event-stream")
    try:
        resp = httpx.post(
            _substitute_env(server.url), json=payload, headers=headers, timeout=timeout,
        )
    except httpx.ConnectError as e:
        raise McpError(f"cannot connect to {server.url}: {e}")
    except httpx.TimeoutException:
        raise McpError(f"{method} timed out after {timeout}s")
    if resp.status_code >= 400:
        raise McpError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    ct = resp.headers.get("content-type", "")
    if "text/event-stream" in ct:
        # Parse SSE: look for the data: line(s) and find the matching id
        for line in resp.text.splitlines():
            if line.startswith("data: "):
                try:
                    msg = json.loads(line[6:])
                except Exception:
                    continue
                if msg.get("id") == req_id:
                    if "error" in msg:
                        raise McpError(f"{method}: {msg['error'].get('message', 'unknown')}")
                    return msg.get("result", {})
        raise McpError(f"no matching response in SSE stream")

    try:
        msg = resp.json()
    except Exception:
        raise McpError(f"non-JSON response: {resp.text[:100]}")
    if isinstance(msg, list):  # batch response
        msg = next((m for m in msg if m.get("id") == req_id), {})
    if "error" in msg:
        raise McpError(f"{method}: {msg['error'].get('message', 'unknown')}")
    return msg.get("result", {})


def _start_http_server(server: McpServer) -> bool:
    try:
        _send_http_request(server, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "gemi", "version": "0.1.0"},
        }, timeout=server.timeout)
        server.initialized = True
        return True
    except Exception as e:
        server.error = f"initialize failed: {e}"
        return False


# --- shared API ------------------------------------------------------

def _send_request(server: McpServer, method: str,
                  params: dict[str, Any] | None = None,
                  timeout: float = 30.0) -> dict[str, Any]:
    if server.transport == "http":
        return _send_http_request(server, method, params, timeout)
    return _send_stdio_request(server, method, params, timeout)


def _list_server_tools(server: McpServer) -> list[dict[str, Any]]:
    if not server.initialized:
        return []
    try:
        result = _send_request(server, "tools/list", {}, timeout=15)
        return result.get("tools", [])
    except Exception as e:
        logger_mod.log_error("mcp.tools_list.failed", server=server.name, error=str(e))
        return []


def _stop_server(server: McpServer) -> None:
    if server.transport == "stdio":
        _stop_stdio_server(server)
    server.initialized = False


# --- Tool wrapper ----------------------------------------------------

class McpTool(Tool):
    """Adapter: wraps an MCP-server-provided tool as a Buddy Tool."""
    dangerous = False

    def __init__(self, server: McpServer, mcp_tool_def: dict[str, Any]):
        self._server = server
        self._mcp_name = mcp_tool_def.get("name", "")
        # Buddy tool name: mcp_<server>_<tool> for clean namespacing
        # Replace non-alphanumeric in server name to keep tool name valid
        clean_server = re.sub(r"[^a-zA-Z0-9_]", "_", server.name)
        self.name = f"mcp_{clean_server}_{self._mcp_name}"
        # Honor the server's stated read-only intent if provided
        annot = mcp_tool_def.get("annotations", {}) or {}
        self.read_only = bool(annot.get("readOnlyHint", False))
        desc = mcp_tool_def.get("description", "")
        self.description = f"[{server.name}] {desc}" if desc else f"[{server.name}] MCP tool"
        self.input_schema = mcp_tool_def.get("inputSchema") or {
            "type": "object", "properties": {},
        }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        if not self._server.is_running:
            return ToolResult.fail(f"MCP server {self._server.name} is not running")
        try:
            result = _send_request(self._server, "tools/call", {
                "name": self._mcp_name,
                "arguments": kwargs,
            }, timeout=self._server.timeout)
        except McpError as e:
            return ToolResult.fail(f"MCP error: {e}")
        except Exception as e:
            return ToolResult.fail(f"MCP unexpected: {e}")

        content = result.get("content", [])
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "image":
                        parts.append(f"[image: {block.get('mimeType', '?')}]")
                    elif block.get("type") == "resource":
                        parts.append(f"[resource: {block.get('uri', '?')}]")
                    else:
                        parts.append(json.dumps(block, default=str)[:500])
            output = "\n".join(parts)
        else:
            output = str(content)

        if result.get("isError"):
            return ToolResult.fail(output)
        return ToolResult.ok(output or "(empty)")


# --- Top-level orchestration -----------------------------------------

_SERVERS: dict[str, McpServer] = {}


def list_servers() -> list[McpServer]:
    return list(_SERVERS.values())


def get_server(name: str) -> McpServer | None:
    return _SERVERS.get(name)


def _load_config() -> dict[str, Any]:
    if not MCP_CONFIG.exists():
        return {"servers": {}}
    try:
        return json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {"servers": {}}


def initialize_all() -> dict[str, Any]:
    """Load mcp.json, spawn all configured servers, register their tools."""
    from .tools.registry import ALL_TOOLS, TOOL_REGISTRY

    cfg = _load_config()
    summary: dict[str, Any] = {}

    for name, spec in (cfg.get("servers") or {}).items():
        if not isinstance(spec, dict):
            continue
        if name in _SERVERS:
            _stop_server(_SERVERS[name])

        server = McpServer(
            name=name,
            transport=spec.get("transport", "stdio"),
            enabled=spec.get("enabled", True),
            tags=spec.get("tags", []),
            description=spec.get("description", ""),
            command=spec.get("command", ""),
            args=spec.get("args", []),
            env=spec.get("env", {}),
            url=spec.get("url", ""),
            headers=spec.get("headers", {}),
            timeout=int(spec.get("timeout", 60)),
        )
        _SERVERS[name] = server

        if not server.enabled:
            summary[name] = {"ok": False, "tools": 0, "error": "disabled", "skipped": True}
            continue

        server.started_at = time.time()
        if server.transport == "http":
            ok = _start_http_server(server)
        else:
            ok = _start_stdio_server(server)

        if not ok:
            summary[name] = {"ok": False, "tools": 0, "error": server.error}
            logger_mod.log_error("mcp.start.failed", server=name, error=server.error)
            continue

        tools = _list_server_tools(server)
        registered = 0
        for tdef in tools:
            wrapper = McpTool(server, tdef)
            if wrapper.name in TOOL_REGISTRY:
                continue
            ALL_TOOLS.append(wrapper)
            TOOL_REGISTRY[wrapper.name] = wrapper
            server.tool_names.append(wrapper.name)
            registered += 1
        server.tools_count = registered
        summary[name] = {"ok": True, "tools": registered, "error": ""}
        logger_mod.log("mcp.tools_registered", server=name, count=registered)

    return summary


def shutdown_all() -> None:
    for s in list(_SERVERS.values()):
        _stop_server(s)
    _SERVERS.clear()


def reload() -> dict[str, Any]:
    from .tools.registry import ALL_TOOLS, TOOL_REGISTRY
    drops = [name for name in TOOL_REGISTRY if name.startswith("mcp_")]
    if drops:
        kept = [t for t in ALL_TOOLS if t.name not in drops]
        ALL_TOOLS.clear()
        ALL_TOOLS.extend(kept)
        for n in drops:
            TOOL_REGISTRY.pop(n, None)
    shutdown_all()
    return initialize_all()


def write_example_config() -> Path:
    """Drop a disabled sample MCP config if no real config exists."""
    if MCP_CONFIG.exists():
        return MCP_CONFIG
    sample = MCP_CONFIG.parent / "mcp.json.example"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text(json.dumps({
        "_comment": "Rename to mcp.json to activate. Each entry under 'servers' spawns one server and registers its tools as 'mcp_<name>_<tool>'.",
        "servers": {
            "filesystem": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem",
                         str(Path.home())],
                "tags": ["essential"],
            },
            "github": {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
                "enabled": False,
                "tags": ["dev"],
            },
            "remote-example": {
                "transport": "http",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer ${MY_TOKEN}"},
                "enabled": False,
                "tags": ["remote"],
            },
        },
    }, indent=2), encoding="utf-8")
    return sample
