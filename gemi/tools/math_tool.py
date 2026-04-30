"""MathTool — safe mathematical expression evaluation."""
from __future__ import annotations

import ast
import math
import operator
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCTIONS = {
    "abs": abs, "round": round, "min": min, "max": max,
    "int": int, "float": float,
    "sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "ceil": math.ceil, "floor": math.floor,
    "pi": math.pi, "e": math.e, "tau": math.tau,
    "inf": math.inf, "nan": math.nan,
    "gcd": math.gcd, "factorial": math.factorial,
    "degrees": math.degrees, "radians": math.radians,
    "pow": pow, "sum": sum,
}


def _safe_eval(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")
    elif isinstance(node, ast.BinOp):
        op = SAFE_OPS.get(type(node.op))
        if not op:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and right > 1000:
            raise ValueError("Exponent too large (max 1000)")
        return op(left, right)
    elif isinstance(node, ast.UnaryOp):
        op = SAFE_OPS.get(type(node.op))
        if not op:
            raise ValueError(f"Unsupported unary: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCTIONS:
            func = SAFE_FUNCTIONS[node.func.id]
            if callable(func):
                args = [_safe_eval(a) for a in node.args]
                return func(*args)
        raise ValueError(f"Unsupported function: {ast.dump(node.func)}")
    elif isinstance(node, ast.Name):
        if node.id in SAFE_FUNCTIONS:
            val = SAFE_FUNCTIONS[node.id]
            if not callable(val):
                return val
        raise ValueError(f"Unknown name: {node.id}")
    elif isinstance(node, ast.Tuple):
        return tuple(_safe_eval(e) for e in node.elts)
    elif isinstance(node, ast.List):
        return [_safe_eval(e) for e in node.elts]
    raise ValueError(f"Unsupported node: {type(node).__name__}")


class MathTool(Tool):
    name = "math"
    description = (
        "Safely evaluate mathematical expressions. "
        "Supports +, -, *, /, //, %, **, and math functions "
        "(sqrt, log, sin, cos, abs, round, etc.)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression to evaluate (e.g. 'sqrt(144) + 2**10').",
            },
        },
        "required": ["expression"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        expr = kwargs.get("expression", "").strip()
        if not expr:
            return ToolResult.fail("No expression provided.")

        try:
            tree = ast.parse(expr, mode="eval")
            result = _safe_eval(tree)
            if isinstance(result, float) and result == int(result) and not math.isinf(result):
                display = f"{result} (= {int(result)})"
            else:
                display = str(result)
            return ToolResult.ok(display)
        except SyntaxError as e:
            return ToolResult.fail(f"Syntax error: {e}")
        except ValueError as e:
            return ToolResult.fail(f"Evaluation error: {e}")
        except ZeroDivisionError:
            return ToolResult.fail("Division by zero")
        except Exception as e:
            return ToolResult.fail(f"Error: {e}")
