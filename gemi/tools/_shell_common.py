"""Shared helpers for shell-execution tools.

Provides:
  - Cross-platform bash/cmd/powershell binary discovery (Windows-aware)
  - run_shell(): unified subprocess.run wrapper with cwd/env/stdin/timeout
  - format_shell_output(): stdout+stderr formatting with truncation
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

MAX_OUTPUT = 60_000   # bytes — bigger than before, model can ask for less


def find_bash() -> str | None:
    """Locate a usable bash interpreter, preferring real bash on Windows."""
    # Direct hit first
    direct = shutil.which("bash")
    if direct and not direct.lower().endswith(".exe.lnk"):
        # On Windows, `where bash` may return something usable
        if sys.platform != "win32" or "system32" not in direct.lower():
            return direct

    if sys.platform == "win32":
        # Common Git for Windows install paths
        candidates = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Git\bin\bash.exe"),
        ]
        for c in candidates:
            if Path(c).is_file():
                return c

        # WSL fallback
        wsl = shutil.which("wsl")
        if wsl:
            return wsl  # caller may need to prepend `wsl bash -c`
    return direct


def find_powershell() -> str | None:
    """Locate PowerShell — prefer pwsh (PowerShell 7+), fall back to powershell.exe."""
    for name in ("pwsh", "powershell"):
        found = shutil.which(name)
        if found:
            return found
    if sys.platform == "win32":
        for c in [
            r"C:\Program Files\PowerShell\7\pwsh.exe",
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        ]:
            if Path(c).is_file():
                return c
    return None


def find_cmd() -> str | None:
    """Locate Windows cmd.exe. Returns None on non-Windows."""
    if sys.platform != "win32":
        return None
    return shutil.which("cmd") or r"C:\Windows\System32\cmd.exe"


def find_git() -> str | None:
    return shutil.which("git")


def run_shell(
    argv: list[str] | str,
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    timeout: int = 120,
    shell: bool = False,
) -> tuple[int, str]:
    """Run a subprocess. Returns (exit_code, combined_output_truncated)."""
    full_env = os.environ.copy()
    if env:
        full_env.update({k: str(v) for k, v in env.items()})

    try:
        proc = subprocess.run(
            argv,
            shell=shell,
            cwd=str(cwd) if cwd else None,
            input=stdin,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"[command timed out after {timeout}s]"
    except FileNotFoundError as e:
        return 127, f"[command not found: {e}]"
    except Exception as e:
        return 1, f"[execution failed: {e}]"

    out = (proc.stdout or "") + (proc.stderr or "")
    out = out.strip()
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n\n... (truncated at {MAX_OUTPUT} chars)"
    return proc.returncode, out


# Common input schema fragment shared by shell tools
SHELL_SCHEMA_PROPS = {
    "command": {
        "type": "string",
        "description": "The command to run.",
    },
    "cwd": {
        "type": "string",
        "description": "Working directory (default: workspace root).",
    },
    "env": {
        "type": "object",
        "description": "Extra env vars to set for this call only (key=value).",
    },
    "stdin": {
        "type": "string",
        "description": "String to pipe to the process's stdin.",
    },
    "timeout": {
        "type": "integer",
        "description": "Timeout in seconds (default 120, max 600).",
        "default": 120,
    },
}
