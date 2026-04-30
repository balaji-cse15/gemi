"""Theme system — Buddy's color palette across multiple modes.

Inspired by Claude Code's theme.ts. Provides multiple coordinated palettes:
  - dark (default)
  - light
  - dark-ansi (16-color ANSI fallback)
  - light-ansi
  - daltonized-dark / daltonized-light (color-blind friendly)

Each theme exposes a Rich Theme with semantic styles plus a structured
palette dict for programmatic gradient/animation use.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from rich.theme import Theme

CONFIG_FILE = Path.home() / ".gemi" / "config.json"

ThemeName = Literal["dark", "light", "dark-ansi", "light-ansi", "daltonized-dark", "daltonized-light"]


@dataclass
class Palette:
    """Structured color palette — used for gradients, charts, animations."""
    # Brand
    buddy: str = "rgb(177,113,247)"           # electric purple — Buddy primary
    buddy_shimmer: str = "rgb(207,153,255)"   # lighter for shimmer
    buddy_dim: str = "rgb(127,73,197)"        # darker for backgrounds

    # Semantic colors
    success: str = "rgb(78,186,101)"
    error: str = "rgb(255,107,128)"
    warning: str = "rgb(255,193,7)"
    info: str = "rgb(122,180,232)"

    # Text levels
    text: str = "rgb(255,255,255)"
    text_muted: str = "rgb(170,170,170)"
    text_subtle: str = "rgb(100,100,100)"
    text_inverse: str = "rgb(0,0,0)"

    # Modes
    yolo: str = "rgb(255,193,7)"
    yolo_shimmer: str = "rgb(255,213,87)"
    plan: str = "rgb(78,196,201)"             # teal
    plan_shimmer: str = "rgb(118,236,241)"
    auto: str = "rgb(120,200,255)"
    auto_shimmer: str = "rgb(160,220,255)"

    # Tool tiers
    tier_safe: str = "rgb(78,186,101)"        # green
    tier_write: str = "rgb(255,193,7)"        # amber
    tier_yolo: str = "rgb(255,107,128)"       # red

    # Diff
    diff_added: str = "rgb(105,219,124)"
    diff_removed: str = "rgb(255,107,128)"
    diff_added_dim: str = "rgb(57,97,72)"
    diff_removed_dim: str = "rgb(120,52,62)"

    # Fleet (8 distinct hues for sub-agents)
    agent_red: str = "rgb(220,38,38)"
    agent_blue: str = "rgb(37,99,235)"
    agent_green: str = "rgb(22,163,74)"
    agent_yellow: str = "rgb(202,138,4)"
    agent_purple: str = "rgb(147,51,234)"
    agent_orange: str = "rgb(234,88,12)"
    agent_pink: str = "rgb(219,39,119)"
    agent_cyan: str = "rgb(8,145,178)"

    # Structural
    border: str = "rgb(110,110,140)"
    border_focus: str = "rgb(177,113,247)"
    surface: str = "rgb(28,28,36)"
    surface_hover: str = "rgb(44,44,56)"
    selection: str = "rgb(60,80,140)"

    # Cost / metering
    cost_low: str = "rgb(78,186,101)"
    cost_high: str = "rgb(255,193,7)"
    cost_burn: str = "rgb(255,107,128)"

    # Rainbow (for "ultrathink" / wow moments)
    rainbow: list[str] = field(default_factory=lambda: [
        "rgb(235,95,87)", "rgb(245,139,87)", "rgb(250,195,95)",
        "rgb(145,200,130)", "rgb(130,170,220)", "rgb(155,130,200)",
        "rgb(200,130,180)",
    ])


def _dark_palette() -> Palette:
    return Palette()


def _light_palette() -> Palette:
    p = Palette()
    p.buddy = "rgb(127,73,197)"
    p.buddy_shimmer = "rgb(157,103,227)"
    p.buddy_dim = "rgb(207,173,247)"
    p.text = "rgb(0,0,0)"
    p.text_muted = "rgb(85,85,85)"
    p.text_subtle = "rgb(150,150,150)"
    p.text_inverse = "rgb(255,255,255)"
    p.success = "rgb(44,122,57)"
    p.error = "rgb(171,43,63)"
    p.warning = "rgb(150,108,30)"
    p.info = "rgb(37,99,235)"
    p.diff_added = "rgb(105,219,124)"
    p.diff_removed = "rgb(255,168,180)"
    p.diff_added_dim = "rgb(199,225,203)"
    p.diff_removed_dim = "rgb(253,210,216)"
    p.surface = "rgb(245,245,250)"
    p.surface_hover = "rgb(232,232,240)"
    p.selection = "rgb(180,213,255)"
    return p


def _dark_ansi_palette() -> Palette:
    p = Palette()
    p.buddy = "magenta"
    p.buddy_shimmer = "bright_magenta"
    p.buddy_dim = "magenta"
    p.success = "green"
    p.error = "red"
    p.warning = "yellow"
    p.info = "blue"
    p.text = "white"
    p.text_muted = "bright_black"
    p.text_subtle = "bright_black"
    p.text_inverse = "black"
    p.yolo = "yellow"
    p.plan = "cyan"
    p.auto = "bright_blue"
    p.tier_safe = "green"
    p.tier_write = "yellow"
    p.tier_yolo = "red"
    p.diff_added = "green"
    p.diff_removed = "red"
    p.diff_added_dim = "green"
    p.diff_removed_dim = "red"
    p.border = "bright_black"
    p.border_focus = "magenta"
    p.agent_red = "red"
    p.agent_blue = "blue"
    p.agent_green = "green"
    p.agent_yellow = "yellow"
    p.agent_purple = "magenta"
    p.agent_orange = "yellow"
    p.agent_pink = "bright_magenta"
    p.agent_cyan = "cyan"
    return p


def _light_ansi_palette() -> Palette:
    p = _dark_ansi_palette()
    p.text = "black"
    p.text_inverse = "white"
    p.text_muted = "bright_black"
    return p


def _daltonized_dark_palette() -> Palette:
    p = Palette()
    p.buddy = "rgb(175,135,255)"
    p.success = "rgb(51,153,255)"          # blue instead of green
    p.error = "rgb(255,102,102)"
    p.warning = "rgb(255,204,0)"
    p.diff_added = "rgb(0,68,102)"          # blue diff
    p.diff_removed = "rgb(102,0,0)"
    return p


def _daltonized_light_palette() -> Palette:
    p = _light_palette()
    p.success = "rgb(0,102,153)"
    p.warning = "rgb(255,153,0)"
    p.diff_added = "rgb(153,204,255)"
    p.diff_removed = "rgb(255,204,204)"
    return p


PALETTES: dict[str, Palette] = {
    "dark": _dark_palette(),
    "light": _light_palette(),
    "dark-ansi": _dark_ansi_palette(),
    "light-ansi": _light_ansi_palette(),
    "daltonized-dark": _daltonized_dark_palette(),
    "daltonized-light": _daltonized_light_palette(),
}


def _to_rich_theme(p: Palette, name: str) -> Theme:
    """Build a Rich Theme from a Palette (with semantic style names)."""
    return Theme({
        # Brand
        "buddy":              f"bold {p.buddy}",
        "buddy.dim":          p.buddy_dim,
        "buddy.shimmer":      p.buddy_shimmer,
        "banner":             f"bold {p.buddy}",

        # Agent
        "agent.name":         f"bold {p.info}",
        "agent.role":         f"dim {p.info}",
        "agent.running":      f"bold {p.success}",
        "agent.stopped":      f"dim {p.error}",
        "agent.partial":      p.warning,

        # Tools
        "tool.name":          f"bold {p.warning}",
        "tool.icon":          p.text_muted,
        "tool.output":        p.text_muted,
        "tool.error":         f"bold {p.error}",
        "tool.blocked":       f"bold {p.error}",
        "tool.cached":        f"dim {p.info}",
        "tool.tier.safe":     p.tier_safe,
        "tool.tier.write":    p.tier_write,
        "tool.tier.yolo":     f"bold {p.tier_yolo}",

        # User / Assistant
        "user.prompt":        f"bold {p.text}",
        "assistant":          p.text,
        "command":            f"bold {p.buddy}",
        "command.arg":        p.buddy_shimmer,

        # Cost / metering
        "cost":               f"dim {p.cost_low}",
        "cost.tokens":        p.cost_low,
        "cost.high":          p.cost_high,
        "cost.burn":          f"bold {p.cost_burn}",

        # Generic semantic
        "error":              f"bold {p.error}",
        "success":            f"bold {p.success}",
        "warning":            f"bold {p.warning}",
        "info":               p.info,
        "dim":                f"dim {p.text_muted}",
        "subtle":             p.text_subtle,
        "muted":              p.text_muted,

        # Modes
        "mode.yolo":          f"bold {p.yolo}",
        "mode.plan":          f"bold {p.plan}",
        "mode.auto":          f"bold {p.auto}",

        # Diff
        "diff.add":           f"bold {p.diff_added}",
        "diff.remove":        f"bold {p.diff_removed}",
        "diff.add.dim":       p.diff_added_dim,
        "diff.remove.dim":    p.diff_removed_dim,

        # Streaming
        "streaming":          p.text,
        "spinner":            f"bold {p.buddy}",

        # Structure
        "border":             p.border,
        "border.focus":       p.border_focus,
        "separator":          f"dim {p.border}",
        "surface":            p.surface,
        "selection":          p.selection,

        # Fleet agents (8 distinct)
        "agent.0":            p.agent_purple,
        "agent.1":            p.agent_blue,
        "agent.2":            p.agent_green,
        "agent.3":            p.agent_yellow,
        "agent.4":            p.agent_pink,
        "agent.5":            p.agent_cyan,
        "agent.6":            p.agent_orange,
        "agent.7":            p.agent_red,
    })


# Cached themes
_RICH_THEMES: dict[str, Theme] = {
    name: _to_rich_theme(p, name) for name, p in PALETTES.items()
}


def get_palette(name: str = "dark") -> Palette:
    return PALETTES.get(name, PALETTES["dark"])


def get_rich_theme(name: str = "dark") -> Theme:
    return _RICH_THEMES.get(name, _RICH_THEMES["dark"])


# --- User config persistence -----------------------------------------

def _load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg: dict[str, Any]) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def get_active_theme_name() -> str:
    """Resolve the active theme: env var > config > default."""
    env = os.environ.get("GEMI_THEME", "").lower()
    if env in PALETTES:
        return env
    cfg = _load_config()
    name = cfg.get("theme", "dark")
    return name if name in PALETTES else "dark"


def set_active_theme(name: str) -> bool:
    """Persist the chosen theme. Returns True if name is valid."""
    if name not in PALETTES:
        return False
    cfg = _load_config()
    cfg["theme"] = name
    _save_config(cfg)
    return True


def list_themes() -> list[str]:
    return list(PALETTES.keys())


# --- Color utilities -------------------------------------------------

def parse_rgb(color: str) -> tuple[int, int, int] | None:
    """Parse 'rgb(r,g,b)' string into a tuple."""
    import re
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", color)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def rgb_to_string(r: int, g: int, b: int) -> str:
    return f"rgb({r},{g},{b})"


def lerp_color(a: str, b: str, t: float) -> str:
    """Linearly interpolate between two RGB colors."""
    rgb_a = parse_rgb(a)
    rgb_b = parse_rgb(b)
    if not rgb_a or not rgb_b:
        return a
    t = max(0.0, min(1.0, t))
    return rgb_to_string(
        int(rgb_a[0] + (rgb_b[0] - rgb_a[0]) * t),
        int(rgb_a[1] + (rgb_b[1] - rgb_a[1]) * t),
        int(rgb_a[2] + (rgb_b[2] - rgb_a[2]) * t),
    )


def gradient_text(text: str, color_a: str, color_b: str) -> str:
    """Apply a linear gradient between two RGB colors across the text."""
    if not text:
        return text
    rgb_a = parse_rgb(color_a)
    rgb_b = parse_rgb(color_b)
    if not rgb_a or not rgb_b:
        return text
    n = len(text)
    out = []
    for i, ch in enumerate(text):
        t = i / max(1, n - 1)
        c = rgb_to_string(
            int(rgb_a[0] + (rgb_b[0] - rgb_a[0]) * t),
            int(rgb_a[1] + (rgb_b[1] - rgb_a[1]) * t),
            int(rgb_a[2] + (rgb_b[2] - rgb_a[2]) * t),
        )
        out.append(f"[{c}]{ch}[/]")
    return "".join(out)


def hue_to_rgb_string(hue: float, saturation: float = 0.7, lightness: float = 0.6) -> str:
    """Convert HSL hue (0-360) to rgb() string."""
    h = (hue % 360 + 360) % 360
    c = (1 - abs(2 * lightness - 1)) * saturation
    x = c * (1 - abs(((h / 60) % 2) - 1))
    m = lightness - c / 2
    r = g = b = 0.0
    if h < 60:    r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    return rgb_to_string(int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))


def rainbow_text(text: str, palette: Palette | None = None) -> str:
    """Color each character in a rainbow sweep."""
    if palette is None:
        palette = PALETTES["dark"]
    if not text:
        return text
    n = len(text)
    if n <= 1:
        return f"[{palette.buddy}]{text}[/]"
    out = []
    for i, ch in enumerate(text):
        hue = (i / n) * 360
        c = hue_to_rgb_string(hue, saturation=0.65, lightness=0.65)
        out.append(f"[{c}]{ch}[/]")
    return "".join(out)


# Backwards compatibility — old code expects GEMI_THEME constant
GEMI_THEME: Theme = get_rich_theme(get_active_theme_name())


def reload_theme() -> Theme:
    """Re-resolve the theme from config and update the global. Returns the new Theme."""
    global GEMI_THEME
    GEMI_THEME = get_rich_theme(get_active_theme_name())
    return GEMI_THEME
