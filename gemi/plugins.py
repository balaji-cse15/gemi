"""Plugin system — auto-discover and load custom Tool subclasses from
~/.gemi/plugins/.

A plugin is just a `.py` file that defines one or more Tool subclasses.
On startup, we scan the plugin directory, import each file as a module,
collect all Tool subclasses, and register them with the tool registry.

Plugins inherit the same SAFE/WRITE/YOLO permission model as built-in
tools. Buggy plugins are isolated — exceptions during load are caught
and reported, not propagated.

Example plugin (~/.gemi/plugins/my_tool.py):

    from gemi.tools.base import Tool, ToolResult
    from pathlib import Path

    class MyTool(Tool):
        name = "my_tool"
        description = "My custom tool"
        read_only = True
        input_schema = {"type": "object", "properties": {
            "input": {"type": "string"}
        }, "required": ["input"]}

        def execute(self, workspace: Path, **kwargs) -> ToolResult:
            return ToolResult.ok(f"Got: {kwargs.get('input', '')}")
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .tools.base import Tool

PLUGINS_DIR = Path.home() / ".gemi" / "plugins"


@dataclass
class PluginInfo:
    name: str
    path: str
    tools: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def loaded(self) -> bool:
        return not self.error


_LOADED: list[PluginInfo] = []


def _ensure_dir() -> None:
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


def _import_file(path: Path) -> tuple[Any | None, str]:
    """Import a Python file as an isolated module. Returns (module, error)."""
    module_name = f"gemi_plugin_{path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None, f"could not create module spec for {path.name}"
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod, ""
    except Exception:
        return None, traceback.format_exc(limit=4)


def _extract_tools(module: Any) -> list[Tool]:
    """Find all Tool subclasses defined in the module and instantiate them."""
    tools: list[Tool] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if obj is Tool:
            continue
        if not issubclass(obj, Tool):
            continue
        # Only instantiate classes defined in THIS module (skip imports)
        if obj.__module__ != module.__name__:
            continue
        try:
            instance = obj()
        except Exception:
            continue
        if not getattr(instance, "name", ""):
            continue
        tools.append(instance)
    return tools


def discover_and_load() -> list[PluginInfo]:
    """Scan plugin dir, load each plugin, register tools. Returns infos."""
    from .tools.registry import ALL_TOOLS, TOOL_REGISTRY
    from . import logger as logger_mod

    _ensure_dir()
    _LOADED.clear()

    plugin_files = sorted(PLUGINS_DIR.glob("*.py"))
    if not plugin_files:
        return _LOADED

    for path in plugin_files:
        if path.name.startswith("_"):
            continue
        info = PluginInfo(name=path.stem, path=str(path))
        module, err = _import_file(path)
        if err or module is None:
            info.error = err.splitlines()[-1] if err else "unknown import error"
            _LOADED.append(info)
            logger_mod.log_error("plugin.load.failed", plugin=info.name, error=info.error)
            continue
        tools = _extract_tools(module)
        for t in tools:
            if t.name in TOOL_REGISTRY:
                info.error = f"tool name conflict: {t.name} already registered"
                logger_mod.log_warn("plugin.skip", plugin=info.name, reason=info.error)
                continue
            ALL_TOOLS.append(t)
            TOOL_REGISTRY[t.name] = t
            info.tools.append(t.name)
        _LOADED.append(info)
        logger_mod.log("plugin.loaded", plugin=info.name, tools=info.tools)

    return _LOADED


def list_loaded() -> list[PluginInfo]:
    return list(_LOADED)


def reload() -> list[PluginInfo]:
    """Reload all plugins. Drops previously-loaded plugin tools first."""
    from .tools.registry import ALL_TOOLS, TOOL_REGISTRY

    # Remove existing plugin tools by name
    plugin_tool_names: set[str] = set()
    for p in _LOADED:
        plugin_tool_names.update(p.tools)

    if plugin_tool_names:
        # Mutate ALL_TOOLS in place (it's referenced elsewhere)
        kept = [t for t in ALL_TOOLS if t.name not in plugin_tool_names]
        ALL_TOOLS.clear()
        ALL_TOOLS.extend(kept)
        for name in plugin_tool_names:
            TOOL_REGISTRY.pop(name, None)

    # Drop module entries so re-import is fresh
    to_drop = [k for k in sys.modules if k.startswith("gemi_plugin_")]
    for k in to_drop:
        sys.modules.pop(k, None)

    return discover_and_load()


def write_example_plugin() -> Path:
    """Drop a sample plugin to ~/.gemi/plugins/example.py if missing."""
    _ensure_dir()
    sample = PLUGINS_DIR / "example.py.disabled"
    if sample.exists():
        return sample
    sample.write_text('''"""Example Buddy plugin. Rename to .py to activate."""
from pathlib import Path
from gemi.tools.base import Tool, ToolResult


class GreetTool(Tool):
    name = "greet"
    description = "Greets the user with a custom message."
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name to greet."}
        },
        "required": ["name"],
    }

    def execute(self, workspace: Path, **kwargs) -> ToolResult:
        name = kwargs.get("name", "stranger")
        return ToolResult.ok(f"Hello, {name}! (from a custom plugin)")
''', encoding="utf-8")
    return sample
