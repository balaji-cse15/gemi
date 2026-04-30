"""HashCrackTool — identify hash types and crack common hashes."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

HASH_PATTERNS = [
    (r'^[a-f0-9]{32}$', 'MD5', 32),
    (r'^[a-f0-9]{40}$', 'SHA-1', 40),
    (r'^[a-f0-9]{64}$', 'SHA-256', 64),
    (r'^[a-f0-9]{128}$', 'SHA-512', 128),
    (r'^[a-f0-9]{56}$', 'SHA-224', 56),
    (r'^[a-f0-9]{96}$', 'SHA-384', 96),
    (r'^\$2[aby]?\$\d{1,2}\$.{53}$', 'bcrypt', 0),
    (r'^\$6\$', 'SHA-512 crypt', 0),
    (r'^\$5\$', 'SHA-256 crypt', 0),
    (r'^\$1\$', 'MD5 crypt', 0),
    (r'^[a-f0-9]{8}$', 'CRC32 / possible short hash', 8),
]

COMMON_PASSWORDS = [
    "password", "123456", "12345678", "qwerty", "abc123", "monkey", "master",
    "dragon", "111111", "baseball", "iloveyou", "trustno1", "sunshine", "princess",
    "football", "charlie", "access", "shadow", "michael", "admin", "letmein",
    "1234567", "welcome", "login", "starwars", "solo", "passw0rd", "hello",
    "root", "toor", "pass", "test", "guest", "changeme", "default", "secret",
]


class HashCrackTool(Tool):
    name = "hash_crack"
    description = (
        "Identify hash types and attempt to crack common hashes. "
        "Actions: 'identify' (detect hash algorithm), "
        "'crack' (try common passwords), 'generate' (hash a string)."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'identify', 'crack', 'generate'.",
                "enum": ["identify", "crack", "generate"],
            },
            "hash": {
                "type": "string",
                "description": "Hash string to identify or crack.",
            },
            "text": {
                "type": "string",
                "description": "Text to hash (for generate action).",
            },
            "algorithm": {
                "type": "string",
                "description": "Algorithm for generate (md5, sha1, sha256, sha512).",
                "default": "sha256",
            },
            "wordlist": {
                "type": "string",
                "description": "Path to custom wordlist file (one word per line).",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "identify":
            return self._identify(kwargs.get("hash", ""))
        elif action == "crack":
            return self._crack(kwargs.get("hash", ""), kwargs.get("wordlist", ""), workspace)
        elif action == "generate":
            return self._generate(kwargs.get("text", ""), kwargs.get("algorithm", "sha256"))
        return ToolResult.fail(f"Unknown action: {action}")

    def _identify(self, hash_str: str) -> ToolResult:
        if not hash_str:
            return ToolResult.fail("No hash provided.")
        h = hash_str.strip().lower()
        matches = []
        for pattern, name, length in HASH_PATTERNS:
            if re.match(pattern, h, re.IGNORECASE):
                matches.append(f"  {name} ({length} chars)" if length else f"  {name}")
        if not matches:
            return ToolResult.ok(f"Unknown hash format ({len(h)} chars)")
        return ToolResult.ok(f"Possible hash types:\n" + "\n".join(matches))

    def _crack(self, hash_str: str, wordlist_path: str, workspace: Path) -> ToolResult:
        if not hash_str:
            return ToolResult.fail("No hash provided.")
        h = hash_str.strip().lower()

        words = list(COMMON_PASSWORDS)
        if wordlist_path:
            fp = Path(wordlist_path) if Path(wordlist_path).is_absolute() else workspace / wordlist_path
            if fp.is_file():
                try:
                    words.extend(fp.read_text().splitlines()[:10000])
                except Exception:
                    pass

        algorithms = []
        if len(h) == 32:
            algorithms.append(("md5", hashlib.md5))
        if len(h) == 40:
            algorithms.append(("sha1", hashlib.sha1))
        if len(h) == 64:
            algorithms.append(("sha256", hashlib.sha256))
        if len(h) == 128:
            algorithms.append(("sha512", hashlib.sha512))

        if not algorithms:
            return ToolResult.fail("Cannot determine hash algorithm from length.")

        for word in words:
            word = word.strip()
            if not word:
                continue
            for algo_name, algo_func in algorithms:
                computed = algo_func(word.encode()).hexdigest()
                if computed == h:
                    return ToolResult.ok(f"CRACKED!\n  Password: {word}\n  Algorithm: {algo_name}")

        return ToolResult.ok(f"Not cracked. Tried {len(words)} words against {len(algorithms)} algorithm(s).")

    def _generate(self, text: str, algorithm: str) -> ToolResult:
        if not text:
            return ToolResult.fail("No text provided.")
        algos = {
            "md5": hashlib.md5, "sha1": hashlib.sha1,
            "sha256": hashlib.sha256, "sha512": hashlib.sha512,
        }
        func = algos.get(algorithm)
        if not func:
            return ToolResult.fail(f"Unknown algorithm: {algorithm}")
        return ToolResult.ok(f"{algorithm}: {func(text.encode()).hexdigest()}")
