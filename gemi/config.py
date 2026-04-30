"""Agent fleet configuration — reads from agents.json with sane defaults.

Two modes:
  1. agents.json present in workspace root or ~/.gemi/  →  load fleet from JSON
  2. otherwise  →  use the built-in 3-agent example fleet

JSON schema documented in examples/agents.example.json.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECTS_ROOT = Path(os.environ.get("GEMI_PROJECTS_ROOT", str(Path.home() / "agents")))


def _port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.25) -> bool:
    """Quick TCP probe — returns True if something is listening on host:port."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


@dataclass(frozen=True)
class AgentDef:
    slug: str
    name: str
    directory: str
    port: int
    proxy_port: int
    role: str = ""
    model: str = ""
    quant: str = ""
    context: int = 16384
    kind: str = "gguf"
    can_think: bool = False
    can_image: bool = False
    can_vision: bool = False
    parallel: int = 1
    quality_tier: str = "standard"
    chat_template: str = ""

    @property
    def path(self) -> Path:
        d = Path(self.directory)
        return d if d.is_absolute() else PROJECTS_ROOT / self.directory

    @property
    def proxy_url(self) -> str:
        return f"http://127.0.0.1:{self.proxy_port}"

    @property
    def model_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def short_model(self) -> str:
        if self.model:
            return self.model.split(".gguf")[0].split("-Uncensored")[0][:40]
        return self.role

    def is_proxy_running(self) -> bool:
        if _port_open(self.proxy_port):
            return True
        pid_file = self.path / "logs" / ".pids" / "proxy.pid"
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            return False

    def is_model_running(self) -> bool:
        if _port_open(self.port):
            return True
        for name in ("llama-server", "vllm-server"):
            pid_file = self.path / "logs" / ".pids" / f"{name}.pid"
            if not pid_file.exists():
                continue
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                return True
            except (ValueError, OSError):
                continue
        return False

    def get_model_name(self) -> str:
        cfg_file = self.path / "launcher" / "llama-server.json"
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text())
                return data.get("model", self.role)
            except Exception:
                pass
        return self.model or self.role

    @property
    def needs_template_fix(self) -> bool:
        return bool(self.chat_template)

    @property
    def template_path(self) -> Path | None:
        if not self.chat_template:
            return None
        if self.chat_template == "qwen36":
            from .templates import QWEN36_TOOL_FIX
            return QWEN36_TOOL_FIX
        p = Path(self.chat_template)
        return p if p.is_file() else None

    @property
    def is_qwen36(self) -> bool:
        return "Qwen3.6" in self.model or "qwen3.6" in self.model.lower()

    @property
    def capability_tags(self) -> list[str]:
        tags = []
        if self.can_think:
            tags.append("think")
        if self.can_image:
            tags.append("image-gen")
        if self.can_vision:
            tags.append("vision")
        if self.parallel > 1:
            tags.append(f"p={self.parallel}")
        return tags


# ---- Default example fleet (used if no agents.json is found) ---------------
# Override by creating an agents.json. See examples/agents.example.json.

DEFAULT_FLEET: list[AgentDef] = [
    AgentDef(
        "local-agent-1", "Local Agent 1", "agent-1", 8001, 9001,
        role="general coder",
        model="Qwen3.6-35B-A3B-Q4_K_M.gguf",
        quant="Q4_K_M", context=16384, parallel=2, can_think=True,
        quality_tier="high", chat_template="qwen36",
    ),
    AgentDef(
        "local-agent-2", "Local Agent 2", "agent-2", 8002, 9002,
        role="precision coder",
        model="Qwen3.6-35B-A3B-Q8_K_P.gguf",
        quant="Q8_K_P", context=8192, parallel=1, can_think=True,
        quality_tier="premium", chat_template="qwen36",
    ),
    AgentDef(
        "local-agent-3", "Local Agent 3", "agent-3", 8003, 9003,
        role="fast throughput",
        model="Qwen3.6-35B-A3B-IQ3_M.gguf",
        quant="IQ3_M", context=32768, parallel=4, can_think=True,
        quality_tier="fast", chat_template="qwen36",
    ),
]


def _load_fleet_json() -> list[AgentDef] | None:
    """Try to load fleet config from agents.json. Returns None if not found."""
    candidates = [
        Path.cwd() / "agents.json",
        Path.home() / ".gemi" / "agents.json",
    ]
    for cfg_path in candidates:
        if not cfg_path.exists():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        agents = data.get("agents") or data.get("fleet") or []
        if not isinstance(agents, list):
            continue
        out: list[AgentDef] = []
        for entry in agents:
            if not isinstance(entry, dict):
                continue
            try:
                out.append(AgentDef(
                    slug=entry["slug"],
                    name=entry.get("name", entry["slug"]),
                    directory=entry.get("directory", entry["slug"]),
                    port=int(entry.get("port", 8001)),
                    proxy_port=int(entry.get("proxy_port", 9001)),
                    role=entry.get("role", ""),
                    model=entry.get("model", ""),
                    quant=entry.get("quant", ""),
                    context=int(entry.get("context", 16384)),
                    kind=entry.get("kind", "gguf"),
                    can_think=bool(entry.get("can_think", False)),
                    can_image=bool(entry.get("can_image", False)),
                    can_vision=bool(entry.get("can_vision", False)),
                    parallel=int(entry.get("parallel", 1)),
                    quality_tier=entry.get("quality_tier", "standard"),
                    chat_template=entry.get("chat_template", ""),
                ))
            except (KeyError, ValueError, TypeError):
                continue
        if out:
            return out
    return None


_loaded = _load_fleet_json()
FLEET: list[AgentDef] = _loaded if _loaded else DEFAULT_FLEET
FLEET_BY_SLUG: dict[str, AgentDef] = {a.slug: a for a in FLEET}


def get_running_agents() -> list[AgentDef]:
    return [a for a in FLEET if a.is_proxy_running()]


def get_agent(slug: str) -> AgentDef | None:
    return FLEET_BY_SLUG.get(slug)


def reload_fleet() -> list[AgentDef]:
    """Re-read agents.json. Updates FLEET and FLEET_BY_SLUG in place."""
    global FLEET, FLEET_BY_SLUG
    fresh = _load_fleet_json() or DEFAULT_FLEET
    FLEET = fresh
    FLEET_BY_SLUG = {a.slug: a for a in FLEET}
    return FLEET
