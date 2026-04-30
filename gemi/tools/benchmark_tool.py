"""BenchmarkTool — time code execution and compare approaches."""
from __future__ import annotations

import ast
import time
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class BenchmarkTool(Tool):
    name = "benchmark"
    description = (
        "Benchmark Python code execution time. "
        "Actions: 'time' (run code N times and report stats), "
        "'compare' (time two code snippets and show which is faster)."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'time' or 'compare'.",
                "enum": ["time", "compare"],
            },
            "code": {
                "type": "string",
                "description": "Python code to benchmark (for 'time').",
            },
            "code_a": {
                "type": "string",
                "description": "First code snippet (for 'compare').",
            },
            "code_b": {
                "type": "string",
                "description": "Second code snippet (for 'compare').",
            },
            "iterations": {
                "type": "integer",
                "description": "Number of iterations (default 1000).",
                "default": 1000,
            },
            "setup": {
                "type": "string",
                "description": "Setup code to run once before benchmarking.",
            },
        },
        "required": ["action"],
    }

    def _safe_check(self, code: str) -> str | None:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"Syntax error: {e}"
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                return "Imports not allowed in benchmark code."
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("exec", "eval", "compile", "__import__", "open"):
                        return f"Unsafe call: {node.func.id}"
        return None

    def _run_timed(self, code: str, iterations: int, setup: str = "") -> dict:
        globs: dict[str, Any] = {}
        if setup:
            exec(compile(setup, "<setup>", "exec"), globs)  # noqa: S102
        compiled = compile(code, "<bench>", "exec")
        times = []
        for _ in range(iterations):
            start = time.perf_counter_ns()
            exec(compiled, globs)  # noqa: S102
            times.append(time.perf_counter_ns() - start)
        avg = sum(times) / len(times)
        mn = min(times)
        mx = max(times)
        med = sorted(times)[len(times) // 2]
        return {"avg_ns": avg, "min_ns": mn, "max_ns": mx, "median_ns": med, "total_ns": sum(times)}

    def _fmt_ns(self, ns: float) -> str:
        if ns < 1_000:
            return f"{ns:.0f}ns"
        elif ns < 1_000_000:
            return f"{ns / 1_000:.2f}µs"
        elif ns < 1_000_000_000:
            return f"{ns / 1_000_000:.2f}ms"
        return f"{ns / 1_000_000_000:.3f}s"

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")
        iterations = min(int(kwargs.get("iterations", 1000)), 100_000)
        setup = kwargs.get("setup", "")

        if setup:
            err = self._safe_check(setup)
            if err:
                return ToolResult.fail(f"Setup: {err}")

        if action == "time":
            code = kwargs.get("code", "")
            if not code:
                return ToolResult.fail("code required.")
            err = self._safe_check(code)
            if err:
                return ToolResult.fail(err)
            try:
                stats = self._run_timed(code, iterations, setup)
            except Exception as e:
                return ToolResult.fail(f"Runtime error: {e}")
            lines = [
                f"Benchmark: {iterations:,} iterations",
                f"  Average: {self._fmt_ns(stats['avg_ns'])}",
                f"  Median:  {self._fmt_ns(stats['median_ns'])}",
                f"  Min:     {self._fmt_ns(stats['min_ns'])}",
                f"  Max:     {self._fmt_ns(stats['max_ns'])}",
                f"  Total:   {self._fmt_ns(stats['total_ns'])}",
            ]
            return ToolResult.ok("\n".join(lines))

        elif action == "compare":
            code_a = kwargs.get("code_a", "")
            code_b = kwargs.get("code_b", "")
            if not code_a or not code_b:
                return ToolResult.fail("code_a and code_b required.")
            for label, code in [("A", code_a), ("B", code_b)]:
                err = self._safe_check(code)
                if err:
                    return ToolResult.fail(f"Code {label}: {err}")
            try:
                stats_a = self._run_timed(code_a, iterations, setup)
                stats_b = self._run_timed(code_b, iterations, setup)
            except Exception as e:
                return ToolResult.fail(f"Runtime error: {e}")
            ratio = stats_a["avg_ns"] / stats_b["avg_ns"] if stats_b["avg_ns"] else float("inf")
            winner = "B" if ratio > 1 else "A"
            factor = ratio if ratio > 1 else 1 / ratio if ratio else 0
            lines = [
                f"Comparison: {iterations:,} iterations",
                f"  A avg: {self._fmt_ns(stats_a['avg_ns'])}  |  B avg: {self._fmt_ns(stats_b['avg_ns'])}",
                f"  A med: {self._fmt_ns(stats_a['median_ns'])}  |  B med: {self._fmt_ns(stats_b['median_ns'])}",
                f"  Winner: {winner} ({factor:.2f}x faster)",
            ]
            return ToolResult.ok("\n".join(lines))

        return ToolResult.fail(f"Unknown action: {action}")
