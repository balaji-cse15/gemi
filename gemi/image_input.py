"""Image input — let users attach images to prompts for vision-capable agents.

Syntax inside a user prompt:
    image:path/to/image.png
    image:/abs/path/to/image.jpg

When detected:
  - For vision-capable agents: replace token with a base64-encoded image block
    in the message content, alongside the remaining text
  - For non-vision agents: replace with a stub note "[image: <name>]"

Returns the original message converted to either a string (no images) or
a structured Anthropic content list (with image blocks).
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

from .config import AgentDef

IMAGE_TOKEN = re.compile(r"image:([^\s]+)")
SUPPORTED_EXT = {".png": "image/png", ".jpg": "image/jpeg",
                 ".jpeg": "image/jpeg", ".gif": "image/gif",
                 ".webp": "image/webp"}
MAX_BYTES = 5 * 1024 * 1024  # 5MB cap


def _encode_image(path: Path) -> dict[str, Any] | str:
    """Return Anthropic image block dict or an error string."""
    if not path.is_file():
        return f"[image not found: {path}]"
    if path.stat().st_size > MAX_BYTES:
        return f"[image too large: {path.name}, max 5MB]"
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXT:
        return f"[unsupported image format: {suffix}]"
    try:
        data = path.read_bytes()
    except Exception as e:
        return f"[image read failed: {e}]"
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": SUPPORTED_EXT[suffix],
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


def expand(text: str, workspace: Path, agent: AgentDef) -> Any:
    """Expand image: tokens in text. Returns either:
      - the original string unchanged (no tokens found)
      - a list of content blocks if any tokens were expanded
    """
    matches = list(IMAGE_TOKEN.finditer(text))
    if not matches:
        return text

    is_vision = bool(getattr(agent, "can_vision", False))
    blocks: list[dict[str, Any]] = []

    cursor = 0
    text_buf = ""
    for m in matches:
        token = m.group(0)
        path_str = m.group(1)
        # Append preceding text
        text_buf += text[cursor:m.start()]
        cursor = m.end()

        path = Path(path_str)
        if not path.is_absolute():
            path = workspace / path
        path = path.resolve()

        if is_vision:
            block_or_err = _encode_image(path)
            if isinstance(block_or_err, dict):
                # Flush text buffer first
                if text_buf.strip():
                    blocks.append({"type": "text", "text": text_buf})
                    text_buf = ""
                blocks.append(block_or_err)
            else:
                # Encode error → keep as text
                text_buf += block_or_err
        else:
            text_buf += f"[image: {path.name} — current agent has no vision capability]"

    # Trailing text
    text_buf += text[cursor:]
    if text_buf.strip():
        blocks.append({"type": "text", "text": text_buf})

    if not blocks:
        return text  # no expansion happened
    if len(blocks) == 1 and blocks[0]["type"] == "text":
        return blocks[0]["text"]
    return blocks


def has_image_token(text: str) -> bool:
    return bool(IMAGE_TOKEN.search(text))
