"""CryptoTool — classical ciphers and encoding for CTF challenges."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class CryptoTool(Tool):
    name = "crypto"
    description = (
        "Classical cryptography ciphers for CTF challenges. "
        "Ciphers: 'caesar', 'vigenere', 'atbash', 'xor', 'morse', 'a1z26' (A=1,Z=26)."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'encrypt' or 'decrypt'.",
                "enum": ["encrypt", "decrypt"],
            },
            "cipher": {
                "type": "string",
                "description": "Cipher: 'caesar', 'vigenere', 'atbash', 'xor', 'morse', 'a1z26', 'caesar_bruteforce'.",
                "enum": ["caesar", "vigenere", "atbash", "xor", "morse", "a1z26", "caesar_bruteforce"],
            },
            "text": {
                "type": "string",
                "description": "Text to encrypt/decrypt.",
            },
            "key": {
                "type": "string",
                "description": "Key for cipher (shift number for caesar, keyword for vigenere, hex for xor).",
            },
        },
        "required": ["cipher", "text"],
    }

    MORSE = {
        'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
        'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
        'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
        'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
        'Y': '-.--', 'Z': '--..', '0': '-----', '1': '.----', '2': '..---',
        '3': '...--', '4': '....-', '5': '.....', '6': '-....', '7': '--...',
        '8': '---..', '9': '----.', ' ': '/', '.': '.-.-.-', ',': '--..--',
    }
    MORSE_REV = {v: k for k, v in MORSE.items()}

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "encrypt")
        cipher = kwargs.get("cipher", "")
        text = kwargs.get("text", "")
        key = kwargs.get("key", "")

        if not text:
            return ToolResult.fail("No text provided.")

        if cipher == "caesar":
            shift = int(key) if key and key.lstrip("-").isdigit() else 3
            return ToolResult.ok(self._caesar(text, shift if action == "encrypt" else -shift))

        elif cipher == "caesar_bruteforce":
            lines = [f"Shift {i:2d}: {self._caesar(text, -i)}" for i in range(26)]
            return ToolResult.ok("Caesar bruteforce:\n" + "\n".join(lines))

        elif cipher == "vigenere":
            if not key:
                return ToolResult.fail("Key required for vigenere.")
            return ToolResult.ok(self._vigenere(text, key, action == "decrypt"))

        elif cipher == "atbash":
            return ToolResult.ok(self._atbash(text))

        elif cipher == "xor":
            if not key:
                return ToolResult.fail("Key (hex) required for xor.")
            return self._xor(text, key, action)

        elif cipher == "morse":
            if action == "encrypt":
                result = " ".join(self.MORSE.get(c.upper(), c) for c in text)
                return ToolResult.ok(result)
            else:
                result = "".join(self.MORSE_REV.get(code, "?") for code in text.split(" "))
                return ToolResult.ok(result)

        elif cipher == "a1z26":
            if action == "encrypt":
                nums = [str(ord(c.upper()) - 64) if c.isalpha() else c for c in text]
                return ToolResult.ok("-".join(nums))
            else:
                parts = text.replace(",", "-").split("-")
                chars = []
                for p in parts:
                    p = p.strip()
                    if p.isdigit() and 1 <= int(p) <= 26:
                        chars.append(chr(int(p) + 64))
                    else:
                        chars.append(p)
                return ToolResult.ok("".join(chars))

        return ToolResult.fail(f"Unknown cipher: {cipher}")

    def _caesar(self, text: str, shift: int) -> str:
        result = []
        for c in text:
            if c.isalpha():
                base = ord('A') if c.isupper() else ord('a')
                result.append(chr((ord(c) - base + shift) % 26 + base))
            else:
                result.append(c)
        return "".join(result)

    def _vigenere(self, text: str, key: str, decrypt: bool) -> str:
        key = key.upper()
        result = []
        ki = 0
        for c in text:
            if c.isalpha():
                base = ord('A') if c.isupper() else ord('a')
                shift = ord(key[ki % len(key)]) - ord('A')
                if decrypt:
                    shift = -shift
                result.append(chr((ord(c) - base + shift) % 26 + base))
                ki += 1
            else:
                result.append(c)
        return "".join(result)

    def _atbash(self, text: str) -> str:
        result = []
        for c in text:
            if c.isalpha():
                base = ord('A') if c.isupper() else ord('a')
                result.append(chr(base + 25 - (ord(c) - base)))
            else:
                result.append(c)
        return "".join(result)

    def _xor(self, text: str, key_hex: str, action: str) -> ToolResult:
        try:
            key_bytes = bytes.fromhex(key_hex)
        except ValueError:
            key_bytes = key_hex.encode()
        if action == "encrypt":
            data = text.encode()
            result = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
            return ToolResult.ok(result.hex())
        else:
            try:
                data = bytes.fromhex(text)
            except ValueError:
                data = text.encode()
            result = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
            try:
                return ToolResult.ok(result.decode())
            except UnicodeDecodeError:
                return ToolResult.ok(result.hex())
