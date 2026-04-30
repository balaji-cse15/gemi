"""DependencyTool — inspect project dependencies and imports."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class DependencyTool(Tool):
    name = "dependency"
    description = (
        "Analyze project dependencies and import graphs. "
        "Actions: 'imports' (scan Python file for imports), "
        "'unused' (find unused imports), 'tree' (show dependency tree from requirements)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'imports', 'unused', 'tree'.",
                "enum": ["imports", "unused", "tree"],
            },
            "file_path": {
                "type": "string",
                "description": "File to analyze (for imports/unused).",
            },
            "directory": {
                "type": "string",
                "description": "Directory to scan (for tree).",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "imports":
            return self._scan_imports(workspace, kwargs.get("file_path", ""))
        elif action == "unused":
            return self._find_unused(workspace, kwargs.get("file_path", ""))
        elif action == "tree":
            return self._dep_tree(workspace, kwargs.get("directory", ""))
        return ToolResult.fail(f"Unknown action: {action}")

    def _resolve(self, workspace: Path, file_path: str) -> Path:
        p = Path(file_path)
        return p if p.is_absolute() else workspace / p

    def _scan_imports(self, workspace: Path, file_path: str) -> ToolResult:
        if not file_path:
            return ToolResult.fail("file_path required.")
        fp = self._resolve(workspace, file_path)
        if not fp.is_file():
            return ToolResult.fail(f"File not found: {fp}")
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8"))
        except SyntaxError as e:
            return ToolResult.fail(f"Parse error: {e}")

        stdlib = []
        third_party = []
        local = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._classify(alias.name, stdlib, third_party, local)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    if node.level > 0:
                        local.append(f".{node.module}")
                    else:
                        self._classify(node.module, stdlib, third_party, local)

        lines = [f"Imports in {fp.name}:"]
        if stdlib:
            lines.append(f"  stdlib ({len(stdlib)}): " + ", ".join(sorted(set(stdlib))))
        if third_party:
            lines.append(f"  third-party ({len(third_party)}): " + ", ".join(sorted(set(third_party))))
        if local:
            lines.append(f"  local ({len(local)}): " + ", ".join(sorted(set(local))))
        if not (stdlib or third_party or local):
            lines.append("  (no imports)")
        return ToolResult.ok("\n".join(lines))

    def _classify(self, module: str, stdlib: list, third_party: list, local: list) -> None:
        STDLIB = {
            "os", "sys", "re", "json", "math", "time", "datetime", "pathlib",
            "collections", "itertools", "functools", "typing", "ast", "io",
            "subprocess", "threading", "socket", "http", "urllib", "hashlib",
            "base64", "struct", "shutil", "glob", "tempfile", "logging",
            "unittest", "dataclasses", "enum", "abc", "copy", "textwrap",
            "string", "secrets", "uuid", "csv", "xml", "html", "email",
            "argparse", "configparser", "contextlib", "inspect", "importlib",
            "traceback", "warnings", "signal", "platform", "ctypes",
            "__future__", "concurrent", "asyncio", "multiprocessing",
        }
        top = module.split(".")[0]
        if top in STDLIB:
            stdlib.append(top)
        elif top.startswith("."):
            local.append(module)
        else:
            third_party.append(top)

    def _find_unused(self, workspace: Path, file_path: str) -> ToolResult:
        if not file_path:
            return ToolResult.fail("file_path required.")
        fp = self._resolve(workspace, file_path)
        if not fp.is_file():
            return ToolResult.fail(f"File not found: {fp}")

        source = fp.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return ToolResult.fail(f"Parse error: {e}")

        imported = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[-1]
                    imported[name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported[name] = f"{node.module}.{alias.name}" if node.module else alias.name

        unused = []
        for local_name, full_name in imported.items():
            pattern = rf'\b{re.escape(local_name)}\b'
            occurrences = len(re.findall(pattern, source))
            if occurrences <= 1:
                unused.append(f"  {local_name} ({full_name})")

        if not unused:
            return ToolResult.ok(f"No unused imports found in {fp.name}.")
        return ToolResult.ok(f"Possibly unused imports in {fp.name}:\n" + "\n".join(unused))

    def _dep_tree(self, workspace: Path, directory: str) -> ToolResult:
        d = self._resolve(workspace, directory) if directory else workspace
        reqs = d / "requirements.txt"
        pyproj = d / "pyproject.toml"
        pkg = d / "package.json"

        lines = []
        if reqs.is_file():
            lines.append("requirements.txt:")
            for line in reqs.read_text().splitlines()[:100]:
                line = line.strip()
                if line and not line.startswith("#"):
                    lines.append(f"  {line}")

        if pyproj.is_file():
            content = pyproj.read_text()
            in_deps = False
            lines.append("pyproject.toml dependencies:")
            for line in content.splitlines():
                if "dependencies" in line and "=" in line:
                    in_deps = True
                    continue
                if in_deps:
                    if line.strip() == "]":
                        in_deps = False
                        continue
                    dep = line.strip().strip('",')
                    if dep:
                        lines.append(f"  {dep}")

        if pkg.is_file():
            import json
            try:
                data = json.loads(pkg.read_text())
                deps = data.get("dependencies", {})
                dev_deps = data.get("devDependencies", {})
                if deps:
                    lines.append(f"package.json dependencies ({len(deps)}):")
                    for n, v in sorted(deps.items())[:50]:
                        lines.append(f"  {n}: {v}")
                if dev_deps:
                    lines.append(f"package.json devDependencies ({len(dev_deps)}):")
                    for n, v in sorted(dev_deps.items())[:50]:
                        lines.append(f"  {n}: {v}")
            except Exception:
                pass

        if not lines:
            return ToolResult.ok("No dependency files found.")
        return ToolResult.ok("\n".join(lines))
