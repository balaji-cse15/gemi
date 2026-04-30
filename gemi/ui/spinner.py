"""Animated spinners for streaming, loading, and status indicators.

Three spinner variants:
  - GlyphSpinner — Claude-style ✻✶✳ frames with hue rotation while streaming
  - BrailleSpinner — fast compact braille for inline indicators
  - StatusSpinner — one-shot context manager for "loading" sections
"""
from __future__ import annotations

import time
import threading
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.spinner import Spinner

from . import glyphs
from .theme import get_palette, hue_to_rgb_string


class GlyphSpinner:
    """Claude-style ✻✶✳ animated spinner with hue rotation.

    Use as a context manager:
        with GlyphSpinner(console, "Thinking..."):
            ... long work ...
    """

    def __init__(
        self,
        console: Console,
        text: str = "",
        *,
        rotate_hue: bool = True,
        message_style: str | None = None,
        frame_ms: int = 80,
    ):
        self.console = console
        self.text = text
        self.rotate_hue = rotate_hue
        self.message_style = message_style
        self.frame_ms = frame_ms
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._live: Live | None = None
        self._frame = 0
        self._start_time = 0.0

    def _render(self) -> Text:
        glyph = glyphs.SPINNER_FRAMES[self._frame % len(glyphs.SPINNER_FRAMES)]
        elapsed = time.time() - self._start_time
        if self.rotate_hue:
            hue = (elapsed * 180) % 360  # full sweep every 2s
            color = hue_to_rgb_string(hue)
        else:
            color = get_palette().buddy
        out = Text()
        out.append(f" {glyph} ", style=f"bold {color}")
        if self.text:
            out.append(self.text, style=self.message_style or "muted")
            out.append(f"  ({elapsed:.1f}s)", style="dim")
        return out

    def _loop(self):
        while not self._stop.is_set():
            self._frame += 1
            if self._live:
                try:
                    self._live.update(self._render())
                except Exception:
                    break
            self._stop.wait(self.frame_ms / 1000)

    def __enter__(self) -> "GlyphSpinner":
        self._start_time = time.time()
        self._live = Live(self._render(), console=self.console, refresh_per_second=12, transient=True)
        self._live.__enter__()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self._live:
            self._live.__exit__(*_)


@contextmanager
def status(console: Console, text: str = "Working...", style: str | None = None) -> Iterator[None]:
    """One-shot status indicator (lighter than GlyphSpinner)."""
    with GlyphSpinner(console, text, message_style=style):
        yield


def render_spinner_frame(frame_index: int, color: str | None = None) -> str:
    """Return a single spinner glyph frame as a Rich-markup string."""
    glyph = glyphs.SPINNER_FRAMES[frame_index % len(glyphs.SPINNER_FRAMES)]
    c = color or get_palette().buddy
    return f"[{c}]{glyph}[/]"


def render_braille_frame(frame_index: int, color: str | None = None) -> str:
    glyph = glyphs.BRAILLE_SPINNER[frame_index % len(glyphs.BRAILLE_SPINNER)]
    c = color or get_palette().buddy
    return f"[{c}]{glyph}[/]"
