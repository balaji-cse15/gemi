# Contributing to Gemi

Thanks for your interest. PRs welcome — but a few rules to keep things sane.

## Setup

```bash
git clone https://github.com/space-kitty-o/gemi
cd gemi
pip install -e ".[dev]"
```

## What's worth working on

In rough priority order:

1. **More free-API tools**. Add a `gemi/tools/<name>.py`, register it in
   `tools/registry.py`. Must be no-key or have a generous free tier.
2. **MCP server templates** in `examples/mcp.example.json`. Anything from
   the [official MCP servers list](https://github.com/modelcontextprotocol/servers).
3. **Linux/macOS launcher** (`gemi.sh`) — mirroring `gemi.ps1`'s
   capabilities (picker, doctor, auto-boot, profiles).
4. **Per-agent launcher templates** in `examples/agent-template/` for
   common stacks (llama.cpp, vLLM, Ollama bridges).
5. **Tests** — `tests/` is empty for now. Smoke tests for tool registry,
   provider parsing, picker resolution, etc.
6. **Bug fixes** — see GitHub issues.

## Code style

- Python 3.11+ (use `|` union types, `match` where it helps).
- Avoid heavy dependencies. The whole point is a lean, local CLI.
- Tools should be one file in `gemi/tools/`, with one Tool subclass.
- Per-call timeouts on every external operation.
- No emojis in launcher files (`.bat`, `.ps1`) — they break under non-UTF8
  Windows codepages.
- Comment the *why*, not the *what*.

## Adding a tool

```python
# gemi/tools/mytool.py
from pathlib import Path
from typing import Any
from .base import Tool, ToolResult

class MyTool(Tool):
    name = "my_tool"
    description = "What it does, in one line, model-facing."
    read_only = True            # SAFE tier
    # dangerous = True          # YOLO tier (skip both for WRITE tier)
    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "string", "description": "Description"}
        },
        "required": ["x"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        x = kwargs.get("x", "")
        if not x:
            return ToolResult.fail("missing x")
        return ToolResult.ok(f"got: {x}")
```

Then register in `gemi/tools/registry.py`:

```python
from .mytool import MyTool
# ...
ALL_TOOLS = [
    # ...,
    MyTool(),
]
```

If your tool is essential (you'd want it on small-context 8K agents),
add the name to `ESSENTIAL_TOOLS` in the same file.

## Adding a slash command

```python
# gemi/commands/registry.py
@register("mycmd", "Short description for /help.")
def cmd_mycmd(app, args: list[str]) -> None:
    app.console.print("Hello from /mycmd")
```

Optionally add an alias to `COMMAND_ALIASES` and a category in
`COMMAND_CATEGORIES`.

## Pull request process

1. Fork, branch, push.
2. PR description: what + why. One sentence each is fine.
3. Keep PRs focused. One feature, one PR.
4. If you change behavior of an existing tool/command, mention it.
5. Don't include local config (`agents.json`, secrets, your tokens, your
   model files).

## Reporting bugs

Run `gemi.bat -Doctor` first and include the output. That covers 80% of
"my setup is broken" issues.
