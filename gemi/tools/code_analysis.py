"""CodeAnalysisTool — static analysis using Python AST."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class CodeAnalysisTool(Tool):
    name = "code_analysis"
    description = (
        "Analyze Python source code structure using AST. "
        "Actions: 'outline' (classes, functions, imports), "
        "'imports' (list all imports), 'complexity' (function metrics), "
        "'symbols' (all defined names)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'outline', 'imports', 'complexity', 'symbols'.",
                "enum": ["outline", "imports", "complexity", "symbols"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to Python source file.",
            },
        },
        "required": ["action", "file_path"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        file_path = kwargs.get("file_path", "")

        if not file_path:
            return ToolResult.fail("No file_path provided.")

        fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
        fp = fp.resolve()

        if not fp.is_file():
            return ToolResult.fail(f"File not found: {fp}")
        if fp.suffix != ".py":
            return ToolResult.fail("Only .py files supported.")

        try:
            source = fp.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(fp))
        except SyntaxError as e:
            return ToolResult.fail(f"Syntax error: {e}")
        except Exception as e:
            return ToolResult.fail(f"Parse error: {e}")

        if action == "outline":
            return self._outline(tree, fp)
        elif action == "imports":
            return self._imports(tree)
        elif action == "complexity":
            return self._complexity(tree, source)
        elif action == "symbols":
            return self._symbols(tree)
        return ToolResult.fail(f"Unknown action: {action}")

    def _outline(self, tree: ast.Module, fp: Path) -> ToolResult:
        lines = [f"File: {fp.name}"]
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                bases = ", ".join(
                    ast.unparse(b) for b in node.bases
                ) if node.bases else ""
                lines.append(f"\n  class {node.name}({bases})  [line {node.lineno}]")
                for item in node.body:
                    if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                        args = ", ".join(a.arg for a in item.args.args)
                        prefix = "async " if isinstance(item, ast.AsyncFunctionDef) else ""
                        lines.append(f"    {prefix}def {item.name}({args})  [line {item.lineno}]")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = ", ".join(a.arg for a in node.args.args)
                prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                lines.append(f"\n  {prefix}def {node.name}({args})  [line {node.lineno}]")
        return ToolResult.ok("\n".join(lines))

    def _imports(self, tree: ast.Module) -> ToolResult:
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if alias.asname:
                        name += f" as {alias.asname}"
                    imports.append(f"  import {name}  [line {node.lineno}]")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = ", ".join(
                    a.name + (f" as {a.asname}" if a.asname else "")
                    for a in node.names
                )
                imports.append(f"  from {module} import {names}  [line {node.lineno}]")
        if not imports:
            return ToolResult.ok("No imports found.")
        return ToolResult.ok(f"{len(imports)} imports:\n" + "\n".join(imports))

    def _complexity(self, tree: ast.Module, source: str) -> ToolResult:
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                branches = 0
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                         ast.With, ast.BoolOp, ast.IfExp)):
                        branches += 1
                line_count = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "lines": line_count,
                    "branches": branches,
                    "cyclomatic": branches + 1,
                })

        if not functions:
            return ToolResult.ok("No functions found.")

        functions.sort(key=lambda f: f["cyclomatic"], reverse=True)
        lines = [f"{'Function':<35s} {'Lines':>5s} {'CC':>4s}"]
        lines.append("-" * 46)
        for f in functions:
            lines.append(f"{f['name']:<35s} {f['lines']:>5d} {f['cyclomatic']:>4d}")
        return ToolResult.ok("\n".join(lines))

    def _symbols(self, tree: ast.Module) -> ToolResult:
        symbols = {"classes": [], "functions": [], "variables": []}
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                symbols["classes"].append(f"{node.name} [line {node.lineno}]")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                symbols["functions"].append(f"{node.name} [line {node.lineno}]")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols["variables"].append(f"{target.id} [line {node.lineno}]")

        lines = []
        for kind, items in symbols.items():
            if items:
                lines.append(f"{kind.title()} ({len(items)}):")
                for item in items:
                    lines.append(f"  {item}")
        if not lines:
            return ToolResult.ok("No top-level symbols found.")
        return ToolResult.ok("\n".join(lines))
