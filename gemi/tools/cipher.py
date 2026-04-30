"""Cipher / encoding detection + decode — CTF and quick-conversion helper.

Tools:
  cipher_detect     Heuristic detection: base16/32/64/85, hex, binary, octal,
                    ROT13, Caesar (all rotations), reverse, Atbash, Morse
  cipher_decode     Apply a specific decoding scheme
  cipher_xor        XOR with key (string or hex)
  cipher_brute      Try every reasonable scheme and rank by 'looks-like-text'
  cipher_morse      Morse encode/decode
  cipher_caesar     Caesar/ROT-N for any N
"""
from __future__ import annotations

import base64
import codecs
import re
import string
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


# ---------------------------------------------------------------- helpers

PRINTABLE = set(string.printable)
COMMON_WORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "man", "new", "now", "old", "see", "two", "way", "who", "boy",
    "did", "its", "let", "put", "say", "she", "too", "use", "this", "with",
    "from", "they", "have", "that", "what", "when", "your", "about",
    "world", "hello", "test", "data", "code", "user", "admin", "root",
    "flag", "pass", "secret", "key", "token", "true", "false", "null",
}


def _has_common_words(s: str) -> int:
    if not s:
        return 0
    words = re.findall(r"[A-Za-z]+", s.lower())
    return sum(1 for w in words if w in COMMON_WORDS)


def _looks_like_text(s: str) -> float:
    """Heuristic 0-1 score: higher = more likely human text."""
    if not s:
        return 0.0
    sample = s[:5000]
    printable_ratio = sum(c in PRINTABLE for c in sample) / len(sample)
    if printable_ratio < 0.85:
        return printable_ratio * 0.5

    letters = sum(c.isalpha() or c == " " for c in sample)
    base = printable_ratio * 0.4 + (letters / len(sample)) * 0.4

    # Bonus: common English words present (massively distinguishes real
    # decoding from ROT-N noise that just shifts letters).
    words = _has_common_words(sample)
    bonus = min(0.3, words * 0.08)

    return min(1.0, base + bonus)


# ---------------------------------------------------------------- detect

class CipherDetectTool(Tool):
    name = "cipher_detect"
    read_only = True
    description = (
        "Heuristically detect what encoding/cipher a string uses. Tests "
        "base16, base32, base64, base85, hex, binary, octal, URL-encoded, "
        "ROT13, reverse, Atbash. Returns ranked candidates."
    )
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        text = (kwargs.get("text") or "").strip()
        if not text:
            return ToolResult.fail("empty text")
        candidates: list[tuple[str, str, float]] = []

        # Hex
        clean = text.replace(" ", "").replace("\n", "")
        if re.fullmatch(r"[0-9a-fA-F]+", clean) and len(clean) % 2 == 0:
            try:
                decoded = bytes.fromhex(clean).decode("utf-8", errors="replace")
                candidates.append(("hex", decoded, _looks_like_text(decoded)))
            except Exception:
                pass

        # Binary
        if re.fullmatch(r"[01\s]+", text):
            bits = text.replace(" ", "").replace("\n", "")
            if len(bits) % 8 == 0:
                try:
                    decoded = "".join(chr(int(bits[i:i+8], 2)) for i in range(0, len(bits), 8))
                    candidates.append(("binary", decoded, _looks_like_text(decoded)))
                except Exception:
                    pass

        # Octal (3-digit groups)
        if re.fullmatch(r"[0-7\s]+", text):
            grouped = text.split()
            try:
                if all(0 <= int(g, 8) < 256 for g in grouped):
                    decoded = "".join(chr(int(g, 8)) for g in grouped)
                    candidates.append(("octal", decoded, _looks_like_text(decoded)))
            except Exception:
                pass

        # Base64
        if re.fullmatch(r"[A-Za-z0-9+/=\s]+", text) and len(clean) % 4 == 0 and len(clean) >= 4:
            try:
                decoded = base64.b64decode(clean, validate=False).decode("utf-8", errors="replace")
                candidates.append(("base64", decoded, _looks_like_text(decoded)))
            except Exception:
                pass

        # URL-safe base64
        if re.fullmatch(r"[A-Za-z0-9\-_=\s]+", text):
            try:
                padded = clean + "=" * (-len(clean) % 4)
                decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
                candidates.append(("base64url", decoded, _looks_like_text(decoded)))
            except Exception:
                pass

        # Base32
        if re.fullmatch(r"[A-Z2-7=\s]+", text.upper()):
            try:
                padded = clean.upper() + "=" * (-len(clean) % 8)
                decoded = base64.b32decode(padded, casefold=True).decode("utf-8", errors="replace")
                candidates.append(("base32", decoded, _looks_like_text(decoded)))
            except Exception:
                pass

        # Base85
        try:
            decoded = base64.b85decode(clean).decode("utf-8", errors="replace")
            candidates.append(("base85", decoded, _looks_like_text(decoded)))
        except Exception:
            pass

        # ROT13 / ROT-N
        for n in range(1, 26):
            decoded = "".join(
                chr((ord(c) - 0x41 + n) % 26 + 0x41) if "A" <= c <= "Z" else
                chr((ord(c) - 0x61 + n) % 26 + 0x61) if "a" <= c <= "z" else c
                for c in text
            )
            score = _looks_like_text(decoded)
            if n == 13 or score > 0.85:
                candidates.append((f"ROT{n}", decoded, score))

        # Reversed
        rev = text[::-1]
        candidates.append(("reverse", rev, _looks_like_text(rev)))

        # Atbash
        atbash = "".join(
            chr(0x5A - (ord(c) - 0x41)) if "A" <= c <= "Z" else
            chr(0x7A - (ord(c) - 0x61)) if "a" <= c <= "z" else c
            for c in text
        )
        candidates.append(("atbash", atbash, _looks_like_text(atbash)))

        # URL encode/decode
        if "%" in text:
            try:
                from urllib.parse import unquote_plus
                decoded = unquote_plus(text)
                candidates.append(("url", decoded, _looks_like_text(decoded)))
            except Exception:
                pass

        candidates.sort(key=lambda c: -c[2])

        out = [f"# Cipher detection — input: {text[:80]}{'…' if len(text) > 80 else ''}\n"]
        out.append(f"  ranked by 'looks-like-text' score (higher = better):\n")
        for name, decoded, score in candidates[:12]:
            preview = decoded[:80].replace("\n", "\\n")
            out.append(f"  [{score:.2f}]  {name:<11}  → {preview}{'…' if len(decoded) > 80 else ''}")
        return ToolResult.ok("\n".join(out))


# ---------------------------------------------------------------- explicit decode

class CipherDecodeTool(Tool):
    name = "cipher_decode"
    read_only = True
    description = (
        "Apply a specific decoding scheme. scheme one of: base64, base64url, "
        "base32, base16, base85, hex, binary, octal, url, rot13, atbash, reverse."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "scheme": {"type": "string"},
        },
        "required": ["text", "scheme"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        text = kwargs.get("text") or ""
        scheme = (kwargs.get("scheme") or "").lower().strip()
        clean = text.replace(" ", "").replace("\n", "")
        try:
            if scheme == "base64":
                out = base64.b64decode(clean + "=" * (-len(clean) % 4), validate=False).decode("utf-8", errors="replace")
            elif scheme == "base64url":
                out = base64.urlsafe_b64decode(clean + "=" * (-len(clean) % 4)).decode("utf-8", errors="replace")
            elif scheme == "base32":
                out = base64.b32decode(clean.upper() + "=" * (-len(clean) % 8), casefold=True).decode("utf-8", errors="replace")
            elif scheme == "base16" or scheme == "hex":
                out = bytes.fromhex(clean).decode("utf-8", errors="replace")
            elif scheme == "base85":
                out = base64.b85decode(clean).decode("utf-8", errors="replace")
            elif scheme == "binary":
                bits = clean
                out = "".join(chr(int(bits[i:i+8], 2)) for i in range(0, len(bits), 8))
            elif scheme == "octal":
                groups = text.split()
                out = "".join(chr(int(g, 8)) for g in groups)
            elif scheme == "url":
                from urllib.parse import unquote_plus
                out = unquote_plus(text)
            elif scheme == "rot13":
                out = codecs.decode(text, "rot_13")
            elif scheme == "atbash":
                out = "".join(
                    chr(0x5A - (ord(c) - 0x41)) if "A" <= c <= "Z" else
                    chr(0x7A - (ord(c) - 0x61)) if "a" <= c <= "z" else c
                    for c in text
                )
            elif scheme == "reverse":
                out = text[::-1]
            else:
                return ToolResult.fail(f"unknown scheme: {scheme}")
        except Exception as e:
            return ToolResult.fail(f"decode failed: {e}")
        return ToolResult.ok(out)


# ---------------------------------------------------------------- xor

class CipherXorTool(Tool):
    name = "cipher_xor"
    read_only = True
    description = (
        "XOR a string against a key. Pass `text` (hex or plain) and `key`. "
        "Auto-detects: if text is hex, decodes first; key can be plain or 'hex:...' or 'b64:...'."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "key": {"type": "string"},
            "text_format": {"type": "string", "default": "auto", "description": "auto|plain|hex|base64"},
            "output": {"type": "string", "default": "auto", "description": "auto|plain|hex|base64"},
        },
        "required": ["text", "key"],
    }

    @staticmethod
    def _parse_input(text: str, fmt: str) -> bytes:
        if fmt == "auto":
            stripped = text.strip().replace(" ", "").replace("\n", "")
            if re.fullmatch(r"[0-9a-fA-F]+", stripped) and len(stripped) % 2 == 0 and len(stripped) >= 4:
                return bytes.fromhex(stripped)
            return text.encode()
        if fmt == "hex":
            return bytes.fromhex(text.replace(" ", ""))
        if fmt == "base64":
            return base64.b64decode(text + "=" * (-len(text) % 4))
        return text.encode()

    @staticmethod
    def _parse_key(key: str) -> bytes:
        if key.startswith("hex:"):
            return bytes.fromhex(key[4:])
        if key.startswith("b64:"):
            return base64.b64decode(key[4:])
        return key.encode()

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        text = kwargs.get("text") or ""
        key = kwargs.get("key") or ""
        in_fmt = kwargs.get("text_format", "auto")
        out_fmt = kwargs.get("output", "auto")
        if not text or not key:
            return ToolResult.fail("missing text or key")
        try:
            data = self._parse_input(text, in_fmt)
            kbytes = self._parse_key(key)
            if not kbytes:
                return ToolResult.fail("empty key")
            xored = bytes(b ^ kbytes[i % len(kbytes)] for i, b in enumerate(data))
        except Exception as e:
            return ToolResult.fail(f"XOR failed: {e}")

        if out_fmt == "auto":
            try:
                decoded = xored.decode("utf-8")
                printable = sum(c in PRINTABLE for c in decoded) / max(len(decoded), 1)
                if printable >= 0.85:
                    return ToolResult.ok(decoded)
            except UnicodeDecodeError:
                pass
            return ToolResult.ok(f"hex: {xored.hex()}")
        if out_fmt == "hex":
            return ToolResult.ok(xored.hex())
        if out_fmt == "base64":
            return ToolResult.ok(base64.b64encode(xored).decode())
        return ToolResult.ok(xored.decode("utf-8", errors="replace"))


# ---------------------------------------------------------------- caesar

class CipherCaesarTool(Tool):
    name = "cipher_caesar"
    read_only = True
    description = "Caesar/ROT-N: rotate every letter by N. Pass shift=N (1-25) or 'all' to brute-force all 25 rotations."
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "shift": {"type": "string", "default": "all"},
        },
        "required": ["text"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        text = kwargs.get("text") or ""
        shift = str(kwargs.get("shift", "all"))
        if not text:
            return ToolResult.fail("empty text")

        def rot(t: str, n: int) -> str:
            return "".join(
                chr((ord(c) - 0x41 + n) % 26 + 0x41) if "A" <= c <= "Z" else
                chr((ord(c) - 0x61 + n) % 26 + 0x61) if "a" <= c <= "z" else c
                for c in t
            )

        if shift == "all":
            out = [f"# Caesar — all 25 rotations\n"]
            for n in range(1, 26):
                rotated = rot(text, n)
                score = _looks_like_text(rotated)
                out.append(f"  [n={n:>2}, score={score:.2f}]  {rotated[:120]}")
            out.sort(key=lambda l: -float(l.split('score=')[-1].split(']')[0]) if 'score=' in l else 0)
            return ToolResult.ok("\n".join(out))
        try:
            n = int(shift) % 26
        except ValueError:
            return ToolResult.fail("shift must be integer or 'all'")
        return ToolResult.ok(rot(text, n))


# ---------------------------------------------------------------- morse

MORSE_TABLE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", "_": "..--.-",
    "\"": ".-..-.", "$": "...-..-", "@": ".--.-.",
}
MORSE_REV = {v: k for k, v in MORSE_TABLE.items()}


class CipherMorseTool(Tool):
    name = "cipher_morse"
    read_only = True
    description = "Encode or decode Morse code (use '/' between words on decode)."
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "mode": {"type": "string", "default": "decode", "description": "encode | decode"},
        },
        "required": ["text"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        text = kwargs.get("text") or ""
        mode = (kwargs.get("mode") or "decode").lower()
        if mode == "encode":
            words = []
            for w in text.upper().split():
                letters = [MORSE_TABLE.get(c, "") for c in w]
                words.append(" ".join(l for l in letters if l))
            return ToolResult.ok(" / ".join(words))
        # decode
        words = re.split(r"\s*/\s*", text.strip())
        decoded = []
        for w in words:
            decoded.append("".join(MORSE_REV.get(letter, "?") for letter in w.split()))
        return ToolResult.ok(" ".join(decoded))


CIPHER_TOOLS = [
    CipherDetectTool(),
    CipherDecodeTool(),
    CipherXorTool(),
    CipherCaesarTool(),
    CipherMorseTool(),
]
