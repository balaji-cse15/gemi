"""ScreenshotTool — capture desktop screenshots."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ScreenshotTool(Tool):
    name = "screenshot"
    dangerous = True
    description = (
        "Capture a screenshot of the desktop or a specific window. "
        "Saves as PNG. Uses platform-native tools."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Path to save screenshot (default: screenshot_<timestamp>.png in workspace).",
            },
            "delay": {
                "type": "integer",
                "description": "Delay in seconds before capture (default 0).",
                "default": 0,
            },
        },
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        output = kwargs.get("output_path", "")
        delay = int(kwargs.get("delay", 0))

        if not output:
            ts = int(time.time())
            output = f"screenshot_{ts}.png"

        out_path = Path(output) if Path(output).is_absolute() else workspace / output
        out_path = out_path.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if delay > 0:
            time.sleep(min(delay, 10))

        try:
            if sys.platform == "win32":
                ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$bitmap.Save('{out_path}')
$graphics.Dispose()
$bitmap.Dispose()
"""
                result = subprocess.run(
                    ["powershell", "-Command", ps_script],
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode != 0:
                    return ToolResult.fail(f"Screenshot failed: {result.stderr}")

            elif sys.platform == "darwin":
                result = subprocess.run(
                    ["screencapture", "-x", str(out_path)],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    return ToolResult.fail(f"Screenshot failed: {result.stderr}")

            else:
                for cmd in [
                    ["gnome-screenshot", "-f", str(out_path)],
                    ["scrot", str(out_path)],
                    ["import", "-window", "root", str(out_path)],
                ]:
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            break
                    except FileNotFoundError:
                        continue
                else:
                    return ToolResult.fail("No screenshot tool found (gnome-screenshot, scrot, or ImageMagick import).")

            if out_path.is_file():
                size = out_path.stat().st_size
                size_str = f"{size / 1024:.0f}KB" if size < 1_048_576 else f"{size / 1_048_576:.1f}MB"
                return ToolResult.ok(f"Screenshot saved: {out_path} ({size_str})")
            return ToolResult.fail("Screenshot file not created.")

        except subprocess.TimeoutExpired:
            return ToolResult.fail("Screenshot capture timed out.")
        except Exception as e:
            return ToolResult.fail(f"Screenshot error: {e}")
