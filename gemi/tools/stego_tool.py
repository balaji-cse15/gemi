"""StegoTool — basic steganography for CTF challenges."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class StegoTool(Tool):
    name = "stego"
    description = (
        "Basic steganography for CTF challenges. "
        "Actions: 'hide_text' (hide text in whitespace encoding), "
        "'reveal_text' (extract hidden text), 'analyze' (check file for hidden data indicators)."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'hide_text', 'reveal_text', 'analyze'.",
                "enum": ["hide_text", "reveal_text", "analyze"],
            },
            "text": {
                "type": "string",
                "description": "Secret text to hide (for hide_text).",
            },
            "cover": {
                "type": "string",
                "description": "Cover text to hide message in (for hide_text).",
            },
            "file_path": {
                "type": "string",
                "description": "File to analyze for hidden data.",
            },
            "encoded": {
                "type": "string",
                "description": "Encoded text to decode (for reveal_text).",
            },
        },
        "required": ["action"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "hide_text":
            text = kwargs.get("text", "")
            cover = kwargs.get("cover", "")
            if not text:
                return ToolResult.fail("text required.")
            if not cover:
                return ToolResult.fail("cover text required.")
            return self._hide_whitespace(text, cover)

        elif action == "reveal_text":
            encoded = kwargs.get("encoded", "")
            if not encoded:
                return ToolResult.fail("encoded text required.")
            return self._reveal_whitespace(encoded)

        elif action == "analyze":
            file_path = kwargs.get("file_path", "")
            if not file_path:
                return ToolResult.fail("file_path required.")
            fp = Path(file_path) if Path(file_path).is_absolute() else workspace / file_path
            return self._analyze(fp.resolve())

        return ToolResult.fail(f"Unknown action: {action}")

    def _hide_whitespace(self, secret: str, cover: str) -> ToolResult:
        binary = "".join(format(ord(c), "08b") for c in secret)
        encoded = binary.replace("0", " ").replace("1", "\t")
        lines = cover.splitlines()
        if not lines:
            lines = [""]
        result_lines = []
        for i, line in enumerate(lines):
            chunk_start = i * 40
            chunk = encoded[chunk_start:chunk_start + 40]
            result_lines.append(line + chunk)

        remaining = encoded[len(lines) * 40:]
        if remaining:
            result_lines.append(remaining)

        return ToolResult.ok("\n".join(result_lines))

    def _reveal_whitespace(self, encoded: str) -> ToolResult:
        binary = ""
        for c in encoded:
            if c == " ":
                binary += "0"
            elif c == "\t":
                binary += "1"

        if len(binary) < 8:
            return ToolResult.ok("No hidden data found.")

        chars = []
        for i in range(0, len(binary) - 7, 8):
            byte = binary[i:i + 8]
            val = int(byte, 2)
            if 32 <= val < 127 or val in (10, 13):
                chars.append(chr(val))
            else:
                break

        if not chars:
            return ToolResult.ok("No readable hidden text found.")
        return ToolResult.ok(f"Hidden text: {''.join(chars)}")

    def _analyze(self, fp: Path) -> ToolResult:
        if not fp.is_file():
            return ToolResult.fail(f"File not found: {fp}")

        try:
            data = fp.read_bytes()
        except Exception as e:
            return ToolResult.fail(f"Read error: {e}")

        findings = []
        size = len(data)

        if fp.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.bmp'):
            if b'PK\x03\x04' in data[100:]:
                findings.append("ZIP archive found embedded in image (possible steganography)")
            if b'Rar!' in data[100:]:
                findings.append("RAR archive found embedded in image")
            if data.endswith(b'\x00' * 100):
                findings.append("File ends with null byte padding (possible hidden data area)")

            eof_markers = {
                '.png': b'IEND',
                '.jpg': b'\xff\xd9',
                '.jpeg': b'\xff\xd9',
                '.gif': b'\x00\x3b',
            }
            marker = eof_markers.get(fp.suffix.lower())
            if marker:
                idx = data.rfind(marker)
                if idx > 0 and idx + len(marker) + 10 < size:
                    extra = size - idx - len(marker)
                    findings.append(f"Data after EOF marker: {extra} bytes (appended data detected)")

        trailing_whitespace = 0
        try:
            text = data.decode("utf-8", errors="strict")
            for line in text.splitlines():
                if line.endswith(" ") or line.endswith("\t"):
                    trailing_whitespace += 1
        except UnicodeDecodeError:
            pass

        if trailing_whitespace > 5:
            findings.append(f"Trailing whitespace on {trailing_whitespace} lines (possible whitespace steganography)")

        if not findings:
            return ToolResult.ok(f"No obvious steganography indicators found in {fp.name} ({size:,} bytes).")

        return ToolResult.ok(f"Analysis of {fp.name} ({size:,} bytes):\n" + "\n".join(f"  [!] {f}" for f in findings))
