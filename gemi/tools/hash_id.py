"""Hash identifier — guess hash algorithm from format + suggest john/hashcat modes.

Tools:
  hash_identify      Guess what algorithm a hash uses (length + charset + format)
  hash_hashcat_mode  Map a hash format to its hashcat -m mode number
  hash_compare       Compare two hashes (constant-time-ish, char-by-char)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


# Length-based heuristics (lowercase hex unless noted)
HASH_BY_LENGTH = {
    8:   ["CRC32"],
    16:  ["MySQL323", "MD5 truncated"],
    32:  ["MD5", "MD4", "NTLM", "LM (truncated)", "MD2", "RIPEMD-128"],
    40:  ["SHA-1", "RIPEMD-160", "MySQL5", "MySQL5.x"],
    48:  ["Tiger-192", "Haval-192"],
    56:  ["SHA-224", "SHA3-224"],
    64:  ["SHA-256", "RIPEMD-256", "Haval-256", "Snefru-256"],
    96:  ["SHA-384", "SHA3-384"],
    128: ["SHA-512", "Whirlpool", "SHA3-512", "BLAKE2b"],
}

# Hashcat mode numbers for common hashes
HASHCAT_MODES = {
    "MD5":           "0",
    "SHA-1":         "100",
    "SHA-224":       "1300",
    "SHA-256":       "1400",
    "SHA-384":       "10800",
    "SHA-512":       "1700",
    "SHA3-224":      "17300",
    "SHA3-256":      "17400",
    "SHA3-384":      "17500",
    "SHA3-512":      "17600",
    "NTLM":          "1000",
    "LM":            "3000",
    "MD4":           "900",
    "RIPEMD-160":    "6000",
    "MySQL323":      "200",
    "MySQL5":        "300",
    "Whirlpool":     "6100",
    "bcrypt":        "3200",
    "phpass":        "400",        # MD5(WordPress)
    "PBKDF2-HMAC-SHA1":   "12000",
    "PBKDF2-HMAC-SHA256": "10900",
    "PBKDF2-HMAC-SHA512": "12100",
    "scrypt":        "8900",
    "Argon2":        "n/a (use john --format=argon2)",
    "Cisco type 5":  "500",
    "Cisco type 7":  "n/a (reversible — use online tool)",
    "Cisco type 8":  "9200",
    "Cisco type 9":  "9300",
    "Django (PBKDF2 SHA256)": "10000",
    "WPA-PMKID":     "16800",
    "WPA-EAPOL":     "22000",
    "JWT (HS256)":   "16500",
    "Keepass 2":     "13400",
    "Bitcoin/Litecoin wallet": "11300",
    "MetaMask":      "26600",
}


# Regex-based identifications — these are STRONG signals (format prefixes etc.)
PATTERN_IDS = [
    (re.compile(r"^\$2[abxy]\$\d{2}\$.{53}$"), "bcrypt", "3200", "high"),
    (re.compile(r"^\$1\$[A-Za-z0-9./]+\$[A-Za-z0-9./]{22}$"), "MD5 crypt (Linux /etc/shadow)", "500", "high"),
    (re.compile(r"^\$5\$[A-Za-z0-9./]*\$[A-Za-z0-9./]+$"), "SHA-256 crypt (Linux)", "7400", "high"),
    (re.compile(r"^\$6\$[A-Za-z0-9./]*\$[A-Za-z0-9./]+$"), "SHA-512 crypt (Linux /etc/shadow)", "1800", "high"),
    (re.compile(r"^\$P\$[A-Za-z0-9./]{31}$"), "phpass (WordPress, phpBB)", "400", "high"),
    (re.compile(r"^\$H\$[A-Za-z0-9./]{31}$"), "phpass H (Joomla, phpBB3)", "400", "high"),
    (re.compile(r"^\$apr1\$[A-Za-z0-9./]+\$[A-Za-z0-9./]{22}$"), "MD5 APR1 (htpasswd)", "1600", "high"),
    (re.compile(r"^\$argon2(id|i|d)\$"), "Argon2", "(use john)", "high"),
    (re.compile(r"^\{SSHA\}.+$"), "Salted SHA-1 (LDAP SSHA)", "111", "high"),
    (re.compile(r"^\{SHA\}.+$"), "SHA-1 (LDAP)", "101", "high"),
    (re.compile(r"^\{MD5\}.+$"), "MD5 (LDAP)", "1900", "high"),
    (re.compile(r"^\{CRYPT\}.+$"), "Crypt (LDAP, depends on inner format)", "?", "medium"),
    (re.compile(r"^pbkdf2_sha256\$\d+\$.+\$.+$"), "Django PBKDF2-SHA256", "10000", "high"),
    (re.compile(r"^sha1\$.+\$.+$"), "Django SHA-1", "124", "high"),
    (re.compile(r"^[a-fA-F0-9]{32}:[a-fA-F0-9]{32}$"), "NTLM:LM combined", "1000", "high"),
    (re.compile(r"^[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+$"), "JWT (header.payload.sig)", "16500", "high"),
    (re.compile(r"^\$y\$[a-zA-Z0-9./]+\$[a-zA-Z0-9./]+\$[a-zA-Z0-9./]+$"), "yescrypt (modern Linux shadow)", "n/a", "high"),
    (re.compile(r"^[A-Za-z0-9./]{13}$"), "DES crypt (legacy Unix)", "1500", "low"),
]


def _all_hex(s: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]+", s))


def _all_b64ish(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9+/=._-]+", s))


class HashIdentifyTool(Tool):
    name = "hash_identify"
    read_only = True
    description = (
        "Identify likely hash algorithm(s) by format. Returns ranked candidates "
        "with hashcat mode numbers. Recognises bcrypt, SHA-512 crypt, MD5 crypt, "
        "Argon2, phpass, NTLM, JWT, Django, LDAP, plain MD5/SHA-* by length, etc."
    )
    input_schema = {
        "type": "object",
        "properties": {"hash": {"type": "string"}},
        "required": ["hash"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        h = (kwargs.get("hash") or "").strip()
        if not h:
            return ToolResult.fail("empty hash")

        candidates: list[dict[str, Any]] = []

        # Pattern-based (strong signals)
        for pattern, name, mode, conf in PATTERN_IDS:
            if pattern.match(h):
                candidates.append({"name": name, "mode": mode, "confidence": conf, "reason": "format-match"})

        # Length+charset based
        if not candidates:
            length = len(h)
            if _all_hex(h) and length in HASH_BY_LENGTH:
                for name in HASH_BY_LENGTH[length]:
                    mode = HASHCAT_MODES.get(name, "?")
                    candidates.append({
                        "name": name, "mode": mode,
                        "confidence": "medium",
                        "reason": f"hex length {length}",
                    })
        # Lowest-confidence: just length
        if not candidates and h.isalnum():
            candidates.append({
                "name": "Unknown",
                "mode": "?",
                "confidence": "low",
                "reason": f"length {len(h)}, charset {'hex' if _all_hex(h) else 'mixed'}",
            })

        out = [f"# Hash identification — `{h[:60]}{'…' if len(h) > 60 else ''}`",
               f"  length: {len(h)}",
               f"  charset: {'hex-only' if _all_hex(h) else 'mixed'}", ""]
        if not candidates:
            out.append("  no match")
            return ToolResult.ok("\n".join(out))
        out.append(f"  {'Algorithm':<35} {'Hashcat':<10} Confidence  Reason")
        out.append("  " + "─" * 85)
        for c in candidates:
            out.append(f"  {c['name']:<35} {c['mode']:<10} {c['confidence']:<11} {c['reason']}")
        out.append("")
        # Suggested cracking commands for the top candidate
        if candidates[0]["mode"] not in ("?", "n/a"):
            mode = candidates[0]["mode"]
            out.append("## Suggested cracking commands")
            out.append(f"  hashcat -m {mode} -a 0 hash.txt rockyou.txt")
            out.append(f"  hashcat -m {mode} -a 3 hash.txt ?l?l?l?l?l?l?l?l")
            out.append(f"  john --format={candidates[0]['name'].lower()} hash.txt")
        return ToolResult.ok("\n".join(out))


class HashcatModeTool(Tool):
    name = "hash_hashcat_mode"
    read_only = True
    description = "Look up the hashcat -m mode number for an algorithm by name (case-insensitive substring)."
    input_schema = {
        "type": "object",
        "properties": {"algorithm": {"type": "string"}},
        "required": ["algorithm"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        q = (kwargs.get("algorithm") or "").lower().strip()
        if not q:
            return ToolResult.fail("missing algorithm")
        matches = [(name, mode) for name, mode in HASHCAT_MODES.items() if q in name.lower()]
        if not matches:
            return ToolResult.fail(f"no algorithm matches '{q}'")
        out = [f"# Hashcat modes matching '{q}'"]
        for name, mode in matches:
            out.append(f"  -m {mode:<5}  {name}")
        return ToolResult.ok("\n".join(out))


HASH_TOOLS = [HashIdentifyTool(), HashcatModeTool()]
