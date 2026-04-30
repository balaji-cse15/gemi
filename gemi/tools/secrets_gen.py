"""SecretsGenTool — generate passwords, API keys, and random strings."""
from __future__ import annotations

import secrets
import string
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class SecretsGenTool(Tool):
    name = "secrets_gen"
    description = (
        "Generate cryptographically secure random strings. "
        "Types: 'password' (mixed chars), 'hex' (hex string), "
        "'token' (URL-safe token), 'pin' (numeric), 'api_key' (alphanumeric)."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Type: 'password', 'hex', 'token', 'pin', 'api_key'.",
                "enum": ["password", "hex", "token", "pin", "api_key"],
            },
            "length": {
                "type": "integer",
                "description": "Length of generated string (default varies by type).",
            },
            "count": {
                "type": "integer",
                "description": "Number to generate (default 1, max 20).",
                "default": 1,
            },
        },
        "required": ["type"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        gen_type = kwargs.get("type", "")
        length = int(kwargs.get("length", 0))
        count = min(int(kwargs.get("count", 1)), 20)

        results = []
        for _ in range(count):
            if gen_type == "password":
                n = length or 20
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
                pw = "".join(secrets.choice(alphabet) for _ in range(n))
                results.append(pw)

            elif gen_type == "hex":
                n = length or 32
                results.append(secrets.token_hex(n // 2))

            elif gen_type == "token":
                n = length or 32
                results.append(secrets.token_urlsafe(n))

            elif gen_type == "pin":
                n = length or 6
                results.append("".join(secrets.choice(string.digits) for _ in range(n)))

            elif gen_type == "api_key":
                n = length or 40
                alphabet = string.ascii_letters + string.digits
                key = "".join(secrets.choice(alphabet) for _ in range(n))
                results.append(key)

            else:
                return ToolResult.fail(f"Unknown type: {gen_type}")

        return ToolResult.ok("\n".join(results))
