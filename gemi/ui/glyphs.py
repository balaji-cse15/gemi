"""Unicode glyphs and figures for Buddy's UI.

Inspired by Claude Code's figures.ts, with Buddy-specific additions for
the multi-agent fleet, hooks, cache, and cost displays.
"""
from __future__ import annotations

import os
import sys

_IS_WINDOWS = sys.platform == "win32"
_IS_DARWIN = sys.platform == "darwin"


# --- Brand identity ---------------------------------------------------

BUDDY_GLYPH = "✻"        # primary brand glyph (teardrop asterisk)
BUDDY_GLYPH_ALT = "✶"    # alternate (six-pointed star)
BUDDY_GLYPH_SMALL = "·"  # idle dot

# Spinner frames — same animation Claude Code uses, with platform fallbacks
if _IS_WINDOWS:
    SPINNER_FRAMES_FWD = ["·", "✢", "*", "✶", "✻", "✽"]
else:
    SPINNER_FRAMES_FWD = ["·", "✢", "✳", "✶", "✻", "✽"]
SPINNER_FRAMES = SPINNER_FRAMES_FWD + list(reversed(SPINNER_FRAMES_FWD))

# Braille spinner for fast/compact use
BRAILLE_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Dot spinner for status footer
DOT_SPINNER = ["⠁", "⠂", "⠄", "⠂"]


# --- Powerline / segment glyphs --------------------------------------

POWERLINE_RIGHT = ""  #
POWERLINE_RIGHT_THIN = ""  #
POWERLINE_LEFT = ""  #
POWERLINE_LEFT_THIN = ""  #

# Fallbacks for non-Powerline fonts
SEGMENT_RIGHT = "❯"
SEGMENT_RIGHT_THIN = "›"
SEGMENT_DIVIDER = "│"
SEGMENT_DIVIDER_THIN = "┊"


# --- Box drawing ------------------------------------------------------

# Light
BOX_LIGHT = {
    "h": "─", "v": "│",
    "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
    "lt": "├", "rt": "┤", "tt": "┬", "bt": "┴", "cross": "┼",
}
# Heavy
BOX_HEAVY = {
    "h": "━", "v": "┃",
    "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛",
    "lt": "┣", "rt": "┫", "tt": "┳", "bt": "┻", "cross": "╋",
}
# Double
BOX_DOUBLE = {
    "h": "═", "v": "║",
    "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝",
    "lt": "╠", "rt": "╣", "tt": "╦", "bt": "╩", "cross": "╬",
}


# --- Status indicators ------------------------------------------------

CHECK = "✓"
CROSS = "✗"
DOT_FILLED = "●"
DOT_EMPTY = "○"
DOT_HALF = "◐"
DIAMOND_FILLED = "◆"
DIAMOND_OPEN = "◇"
SQUARE_FILLED = "■"
SQUARE_EMPTY = "□"
TRIANGLE_RIGHT = "▶"
TRIANGLE_LEFT = "◀"
TRIANGLE_UP = "▲"
TRIANGLE_DOWN = "▼"
LIGHTNING = "⚡"
SPARKLE = "✨"
HOURGLASS = "⏳"
CLOCK = "◷"
LOCK_OPEN = "🔓"
LOCK_CLOSED = "🔒"
WARNING = "⚠"
INFO = "ⓘ"
ARROW_RIGHT = "→"
ARROW_LEFT = "←"
ARROW_UP = "↑"
ARROW_DOWN = "↓"
ARROW_RIGHT_HEAVY = "▶"


# --- Effort / quality tier indicators --------------------------------

EFFORT_LOW = "○"
EFFORT_MEDIUM = "◐"
EFFORT_HIGH = "●"
EFFORT_MAX = "◉"

QUALITY_TIER_GLYPH = {
    "economy": "○",
    "fast": "◐",
    "standard": "●",
    "high": "●",
    "premium": "◉",
}


# --- Progress bars ----------------------------------------------------

BAR_FULL_BLOCK = "█"
BAR_LIGHT_BLOCK = "░"
BAR_FILLED_FRACTIONS = ["░", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]


def progress_bar(percent: float, width: int = 20, filled_char: str = "█", empty_char: str = "░") -> str:
    """Render a progress bar at the given percent (0-100)."""
    pct = max(0.0, min(100.0, percent))
    filled = int(width * pct / 100)
    return filled_char * filled + empty_char * (width - filled)


def gradient_bar(percent: float, width: int = 20) -> str:
    """Smooth gradient progress bar using fractional blocks."""
    pct = max(0.0, min(100.0, percent))
    total_eighths = int(width * pct / 100 * 8)
    full = total_eighths // 8
    partial = total_eighths % 8
    bar = BAR_FULL_BLOCK * full
    if partial > 0 and full < width:
        bar += BAR_FILLED_FRACTIONS[partial]
        full += 1
    bar += BAR_LIGHT_BLOCK * (width - full)
    return bar


# --- Capability tag glyphs -------------------------------------------

CAPABILITY_GLYPHS = {
    "think":     "🧠",
    "image-gen": "🎨",
    "vision":    "👁",
    "fast":      "⚡",
    "p":         "∥",  # parallel
}


def cap_glyph(tag: str) -> str:
    """Return a glyph for a capability tag (e.g. 'think', 'p=4')."""
    if tag.startswith("p=") or tag.startswith("p:"):
        return f"∥{tag.split('=', 1)[-1]}"
    return CAPABILITY_GLYPHS.get(tag, tag)


# --- Tool tier indicators --------------------------------------------

TIER_GLYPHS = {
    "safe":  "●",
    "write": "◐",
    "yolo":  "◉",
}

TIER_LABELS = {
    "safe":  "SAFE",
    "write": "WRITE",
    "yolo":  "YOLO",
}


# --- Fleet status indicators -----------------------------------------

STATUS_READY = "●"
STATUS_OFFLINE = "○"
STATUS_PARTIAL = "◐"
STATUS_LOADING = "◌"


def fleet_status_glyph(model_running: bool, proxy_running: bool) -> str:
    if model_running and proxy_running:
        return STATUS_READY
    if model_running or proxy_running:
        return STATUS_PARTIAL
    return STATUS_OFFLINE


# --- Mode indicators -------------------------------------------------

MODE_GLYPHS = {
    "yolo": "⚡",
    "plan": "◇",
    "auto": "↻",
    "normal": "✻",
}


# --- Width helpers ---------------------------------------------------

def visible_width(s: str) -> int:
    """Return the visible width of a string accounting for emoji/wide chars."""
    width = 0
    for ch in s:
        cp = ord(ch)
        # Wide CJK and emoji ranges (simplified)
        if 0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0x303E or \
           0x3041 <= cp <= 0x33FF or 0x3400 <= cp <= 0x4DBF or \
           0x4E00 <= cp <= 0x9FFF or 0xA000 <= cp <= 0xA4CF or \
           0xAC00 <= cp <= 0xD7A3 or 0xF900 <= cp <= 0xFAFF or \
           0xFE30 <= cp <= 0xFE4F or 0xFF00 <= cp <= 0xFF60 or \
           0xFFE0 <= cp <= 0xFFE6 or 0x1F300 <= cp <= 0x1FAFF:
            width += 2
        elif cp < 0x20 or 0x7F <= cp <= 0xA0:
            continue  # control char
        else:
            width += 1
    return width


def supports_unicode() -> bool:
    """Best-effort detection of Unicode support."""
    enc = (sys.stdout.encoding or "").lower()
    if "utf" in enc:
        return True
    if os.environ.get("GEMI_NO_UNICODE"):
        return False
    return not _IS_WINDOWS  # default: assume yes on non-Windows


def supports_truecolor() -> bool:
    """Detect 24-bit color support."""
    if os.environ.get("GEMI_NO_TRUECOLOR"):
        return False
    colorterm = os.environ.get("COLORTERM", "").lower()
    if "truecolor" in colorterm or "24bit" in colorterm:
        return True
    term = os.environ.get("TERM", "").lower()
    if "256color" in term or "256-color" in term:
        return True
    if os.environ.get("WT_SESSION"):  # Windows Terminal
        return True
    return False
