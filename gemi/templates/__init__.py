"""Chat templates for local model compatibility fixes."""
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent

QWEN36_TOOL_FIX = TEMPLATES_DIR / "qwen36_tool_call_fix.jinja"
