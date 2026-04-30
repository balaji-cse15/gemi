"""ForensicsTool — file analysis, hex dump, strings extraction, metadata."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

MAGIC_BYTES = {
    b'\x89PNG': 'PNG image',
    b'\xff\xd8\xff': 'JPEG image',
    b'GIF8': 'GIF image',
    b'PK\x03\x04': 'ZIP archive / DOCX / XLSX / APK / JAR',
    b'PK\x05\x06': 'ZIP archive (empty)',
    b'\x1f\x8b': 'Gzip compressed',
    b'BZ': 'Bzip2 compressed',
    b'\xfd7zXZ': 'XZ compressed',
    b'Rar!': 'RAR archive',
    b'7z\xbc\xaf': '7-Zip archive',
    b'\x7fELF': 'ELF executable (Linux)',
    b'MZ': 'PE executable (Windows EXE/DLL)',
    b'\xca\xfe\xba\xbe': 'Mach-O / Java class (big-endian)',
    b'\xfe\xed\xfa\xce': 'Mach-O 32-bit',
    b'\xfe\xed\xfa\xcf': 'Mach-O 64-bit',
    b'%PDF': 'PDF document',
    b'\xd0\xcf\x11\xe0': 'Microsoft Office (OLE2)',
    b'SQLite': 'SQLite database',
    b'\x00\x00\x01\x00': 'ICO icon',
    b'RIFF': 'RIFF (WAV/AVI/WebP)',
    b'OggS': 'Ogg container',
    b'fLaC': 'FLAC audio',
    b'ID3': 'MP3 with ID3 tag',
    b'\xff\xfb': 'MP3 audio',
    b'\x1aE\xdf\xa3': 'Matroska/WebM video',
    b'\x00\x00\x00\x1cftyp': 'MP4/M4A/MOV',
    b'<!DOCTYPE': 'HTML document',
    b'<?xml': 'XML document',
    b'{\n': 'JSON data',
    b'---': 'YAML/frontmatter',
}


class ForensicsTool(Tool):
    name = "forensics"
    description = (
        "File forensics: detect file type by magic bytes, hex dump, "
        "extract printable strings, show file metadata. "
        "Useful for CTF challenges and binary analysis."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'identify', 'hexdump', 'strings', 'metadata', 'entropy'.",
                "enum": ["identify", "hexdump", "strings", "metadata", "entropy"],
            },
            "file_path": {
                "type": "string",
                "description": "Path to file to analyze.",
            },
            "offset": {
                "type": "integer",
                "description": "Byte offset for hexdump (default 0).",
                "default": 0,
            },
            "length": {
                "type": "integer",
                "description": "Number of bytes for hexdump (default 256).",
                "default": 256,
            },
            "min_length": {
                "type": "integer",
                "description": "Minimum string length for strings extraction (default 4).",
                "default": 4,
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

        if action == "identify":
            return self._identify(fp)
        elif action == "hexdump":
            offset = int(kwargs.get("offset", 0))
            length = min(int(kwargs.get("length", 256)), 4096)
            return self._hexdump(fp, offset, length)
        elif action == "strings":
            min_len = int(kwargs.get("min_length", 4))
            return self._strings(fp, min_len)
        elif action == "metadata":
            return self._metadata(fp)
        elif action == "entropy":
            return self._entropy(fp)
        return ToolResult.fail(f"Unknown action: {action}")

    def _identify(self, fp: Path) -> ToolResult:
        try:
            data = fp.read_bytes()[:32]
        except Exception as e:
            return ToolResult.fail(f"Read error: {e}")

        matches = []
        for magic, desc in MAGIC_BYTES.items():
            if data.startswith(magic):
                matches.append(desc)

        size = fp.stat().st_size
        size_str = f"{size:,} bytes"
        if size > 1_048_576:
            size_str += f" ({size / 1_048_576:.1f} MB)"

        lines = [f"File: {fp.name}", f"Size: {size_str}"]
        if matches:
            lines.append(f"Type: {', '.join(matches)}")
        else:
            lines.append("Type: Unknown")
        lines.append(f"Magic: {data[:8].hex()}")
        return ToolResult.ok("\n".join(lines))

    def _hexdump(self, fp: Path, offset: int, length: int) -> ToolResult:
        try:
            with open(fp, "rb") as f:
                f.seek(offset)
                data = f.read(length)
        except Exception as e:
            return ToolResult.fail(f"Read error: {e}")

        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{offset + i:08x}  {hex_part:<48s}  |{ascii_part}|")
        return ToolResult.ok("\n".join(lines))

    def _strings(self, fp: Path, min_len: int) -> ToolResult:
        try:
            data = fp.read_bytes()
        except Exception as e:
            return ToolResult.fail(f"Read error: {e}")

        strings = []
        current = []
        for b in data:
            if 32 <= b < 127:
                current.append(chr(b))
            else:
                if len(current) >= min_len:
                    strings.append("".join(current))
                current = []
        if len(current) >= min_len:
            strings.append("".join(current))

        if not strings:
            return ToolResult.ok(f"No strings found (min length {min_len}).")

        display = strings[:200]
        result = "\n".join(display)
        if len(strings) > 200:
            result += f"\n... ({len(strings) - 200} more)"
        return ToolResult.ok(f"{len(strings)} strings found:\n{result}")

    def _metadata(self, fp: Path) -> ToolResult:
        import os
        stat = fp.stat()
        from datetime import datetime
        lines = [
            f"File: {fp.name}",
            f"Path: {fp}",
            f"Size: {stat.st_size:,} bytes",
            f"Created: {datetime.fromtimestamp(stat.st_ctime).isoformat()}",
            f"Modified: {datetime.fromtimestamp(stat.st_mtime).isoformat()}",
            f"Accessed: {datetime.fromtimestamp(stat.st_atime).isoformat()}",
            f"Extension: {fp.suffix}",
            f"Permissions: {oct(stat.st_mode)}",
        ]
        return ToolResult.ok("\n".join(lines))

    def _entropy(self, fp: Path) -> ToolResult:
        import math
        try:
            data = fp.read_bytes()
        except Exception as e:
            return ToolResult.fail(f"Read error: {e}")

        if not data:
            return ToolResult.ok("Empty file, entropy = 0")

        freq = [0] * 256
        for b in data:
            freq[b] += 1

        entropy = 0.0
        for f in freq:
            if f > 0:
                p = f / len(data)
                entropy -= p * math.log2(p)

        assessment = "low (text/structured)" if entropy < 5 else "medium" if entropy < 7 else "high (compressed/encrypted/random)"
        return ToolResult.ok(f"Entropy: {entropy:.4f} bits/byte (max 8.0)\nAssessment: {assessment}\nSize: {len(data):,} bytes")
