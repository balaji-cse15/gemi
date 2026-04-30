"""JwtTool — decode and inspect JWT tokens (no external deps)."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class JwtTool(Tool):
    name = "jwt"
    description = (
        "Decode and inspect JWT (JSON Web Token) tokens. "
        "Shows header, payload, and signature info. No verification — decode only."
    )
    read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "token": {
                "type": "string",
                "description": "JWT token string to decode.",
            },
        },
        "required": ["token"],
    }

    def _b64_decode(self, s: str) -> bytes:
        padding = 4 - len(s) % 4
        if padding != 4:
            s += "=" * padding
        return base64.urlsafe_b64decode(s)

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        token = kwargs.get("token", "").strip()
        if not token:
            return ToolResult.fail("No token provided.")

        parts = token.split(".")
        if len(parts) != 3:
            return ToolResult.fail(f"Invalid JWT: expected 3 parts, got {len(parts)}.")

        try:
            header = json.loads(self._b64_decode(parts[0]))
        except Exception as e:
            return ToolResult.fail(f"Failed to decode header: {e}")

        try:
            payload = json.loads(self._b64_decode(parts[1]))
        except Exception as e:
            return ToolResult.fail(f"Failed to decode payload: {e}")

        lines = ["=== JWT Header ==="]
        lines.append(json.dumps(header, indent=2))
        lines.append("\n=== JWT Payload ===")
        lines.append(json.dumps(payload, indent=2))

        if "exp" in payload:
            from datetime import datetime, timezone
            try:
                exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
                lines.append(f"\nExpires: {exp.isoformat()}")
                if exp < datetime.now(timezone.utc):
                    lines.append("Status: EXPIRED")
                else:
                    lines.append("Status: VALID (not expired)")
            except Exception:
                pass

        if "iat" in payload:
            from datetime import datetime, timezone
            try:
                iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
                lines.append(f"Issued: {iat.isoformat()}")
            except Exception:
                pass

        sig_len = len(parts[2])
        lines.append(f"\nSignature: {parts[2][:20]}... ({sig_len} chars)")
        lines.append(f"Algorithm: {header.get('alg', 'unknown')}")

        return ToolResult.ok("\n".join(lines))
