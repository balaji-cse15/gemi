# Gemi Architecture

> Technical reference for the local-fleet AI CLI. Companion to README.md.

## High level

```
                    +-------------------+
                    |   User Terminal   |
                    | (Rich + prompt-   |
                    |  toolkit REPL)    |
                    +--------+----------+
                             v
                    +-------------------+
                    |    GemiApp        |
                    |   (gemi/app.py)   |
                    | - REPL loop       |
                    | - Slash commands  |
                    | - Mode management |
                    | - Streaming UI    |
                    +--------+----------+
                             v
                    +-------------------+
                    |   QueryEngine     |
                    | (query_engine.py) |
                    | - Tool loop       |
                    | - Permission gate |
                    | - Smart compaction|
                    | - Snapshots/rewind|
                    | - Stats tracking  |
                    +--------+----------+
                             |
   +-------+-----+-----+-----+----+----+----+--------+
   v       v     v     v          v    v    v        v
+----+ +----+ +----+ +-----+ +------+ +---+ +---+ +--------+
|Hooks||Cache||Cost||Perms| |Ctx   | |Aut| |Pl-||Orches  |
|     ||LRU ||kWh ||rules| |loader| |opi||ugi||tration |
+----+ +----+ +----+ +-----+ +------+ +---+ +---+ +--------+
                             |
              +-------------+-------------+
              v                           v
     +------------------+       +------------------+
     |   Tool System    |       |    Provider      |
     | 100+ tools       |       | (provider.py)    |
     | 3-tier perms     |       | SSE streaming    |
     | Smart filtering  |       | Connection pool  |
     +------------------+       +--------+---------+
                                         |
                          +--------------+--------------+
                          v                             v
               +------------------+         +------------------+
               | Anthropic-API    |         | llama-server     |
               | proxies          |         | (GGUF runtime)   |
               | ports 9001-901N  |         | ports 8001-800N  |
               +------------------+         +------------------+
                          |                             |
                          +--------------+--------------+
                                         |
                                         v
                                +------------------+
                                | Local GPU (CUDA) |
                                | GGUF models      |
                                +------------------+
```

## Request flow (single turn)

1. User types in the REPL.
2. `GemiApp` passes input to `QueryEngine.query()`.
3. Engine appends to `messages`, runs context compaction if >75% of agent
   context window.
4. Engine calls `Provider._stream_round()` — `httpx.Client.stream()`
   POSTs to `/v1/messages` on the proxy.
5. Proxy translates Anthropic format → OpenAI format, forwards to
   `llama-server`.
6. `llama-server` runs inference, returns SSE stream.
7. Provider parses SSE events; for each `content_block_delta` of type
   `text_delta`, calls `on_text_chunk()` for live streaming.
8. After stream end, the assembled response is checked for `tool_use`
   blocks. For each one:
   - **PreToolUse hook** can block.
   - **Permission tier check** (SAFE / WRITE / YOLO) + custom rules.
   - **Cache lookup** (SAFE reads only).
   - **execute_tool()** with retry-with-backoff.
   - **PostToolUse hook** can mutate output.
   - Tool results are appended; loop repeats up to 25 rounds.
9. Final response is returned as `TurnResult` and rendered to the REPL.

## Smart context compaction

When estimated tokens > 75% of context window:

1. Keep first 2 messages (initial context).
2. Keep last 4 messages (current task context).
3. Summarize the dropped middle into a compressed user/assistant pair.
4. If still over budget, truncate from the inside.

## Smart tool filtering

For agents with `context <= 12288`, only the curated `ESSENTIAL_TOOLS`
set is sent (~13 tools, ~2K tokens). Larger-context agents see the
full set (~70 native + however many MCP tools are loaded).

## Permission tiers

```
Tool call arrives
  ↓
Custom DENY rule matched?  → block
  ↓
Bypass mode (YOLO)?        → allow
  ↓
read_only=True?            → allow
  ↓
dangerous=True (YOLO)?     → block (suggest /yolo)
  ↓
Custom ALLOW rule matched? → allow
  ↓
Matches DANGEROUS_PATTERNS? → block (e.g. write to .env)
  ↓
allow
```

## Subsystems

### Hooks (`gemi/hooks.py`)

Six lifecycle events: `PreToolUse`, `PostToolUse`, `UserPromptSubmit`,
`Stop`, `SessionStart`, `AgentSwitch`. Each hook is a shell command or
Python callback. Loaded from `~/.gemi/hooks.json`.

### Cache (`gemi/cache.py`)

LRU cache (default 256 entries, 600s TTL) for SAFE read-only tools.
Auto-invalidates on writes. Tool name is part of the cache key —
`read_file("foo.py")` and `read_file("bar.py")` are separate entries.

### Cost (`gemi/cost.py`)

Per-turn kWh estimate based on quant tier multiplier × elapsed time ×
GPU/system watts. Persisted to `~/.gemi/costs.json` with daily,
by-agent, and lifetime totals.

### Permissions (`gemi/permissions.py`)

Allow/deny rules layered over the base tier system. Default deny rules
ship built-in (rm -rf /, fork bombs, .ssh/id_rsa, .aws/credentials).

### MCP (`gemi/mcp.py`)

Spawns MCP servers (stdio or HTTP transport), runs the JSON-RPC
`initialize` handshake, calls `tools/list`, registers each MCP tool
as `mcp_<server>_<toolname>`. Supports `${ENV_VAR}` substitution in
config.

### Plugins (`gemi/plugins.py`)

Auto-imports `.py` files in `~/.gemi/plugins/`, finds Tool subclasses,
registers them. Crash-isolated.

### Autopilot v2 (`gemi/autopilot_v2.py`)

Subgoal tracking, step budgets (rounds, tools, wall-clock), stall
detection (same tool 4× in a row), recovery prompts (5 errors in a
row). Live progress panel via Rich Live.

### Sub-agents (`gemi/tools/task.py`)

`task` tool spawns a fresh QueryEngine for one delegated task. Bounded
recursion depth (default 2). Multi-agent delegation lives in
`gemi/orchestration.py` (`delegate`, `vote`, `race`).

## Streaming architecture

1. `QueryEngine._stream_round()` opens `httpx.Client.stream()`.
2. SSE events parsed by `Provider._collect_sse_to_response()`.
3. `content_block_delta` with `text_delta` → `on_text_chunk()` callback
   writes directly to stdout (bypasses Rich buffering).
4. After stream end, the assembled response object has the same shape
   as a non-streamed Anthropic Messages API response.

## Connection pooling

`QueryEngine` keeps a persistent `httpx.Client` per agent with
keep-alive enabled and a 300s timeout. On `set_agent()`, the old
client is closed and a fresh one is created with the new
`base_url`.

## File system layout

```
gemi/                              # Source (this repo)
  gemi/                            # Python package
    __init__.py
    __main__.py                    # CLI entry: argparse, --exec, --status, --yolo
    app.py                         # GemiApp: REPL, slash commands, modes
    config.py                      # AgentDef + JSON-loaded fleet
    provider.py                    # SSE parsing, request building, Qwen 3.6 fallback
    query_engine.py                # Tool loop, permission gate, compaction
    session.py                     # Session persistence
    hooks.py
    cache.py
    cost.py
    permissions.py
    mcp.py
    plugins.py
    profiles.py
    autopilot_v2.py
    orchestration.py
    workspace_context.py
    image_input.py
    completion.py
    background.py
    prompts.py
    logger.py
    retry.py
    approval.py
    templates/
      qwen36_tool_call_fix.jinja   # Patched chat template
    tools/                         # 100+ tools, one per file
    ui/                            # banner, render, theme, prompt, picker, glyphs
    commands/                      # slash command registry + handlers
    skills/                        # MD-based skill loader
    memory/                        # MD-based memory store
  examples/                        # Config templates
    agents.example.json
    mcp.example.json
    profiles.example.json
    hooks.example.json
    permissions.example.json
    .env.example
  gemi.ps1                         # Unified Windows launcher
  gemi.bat                         # Windows shim
  pyproject.toml
  README.md
  ARCHITECTURE.md                  # This file
  INSTALL.md
  CONTRIBUTING.md
  LICENSE

~/.gemi/                           # User runtime data (.gitignore'd)
  agents.json                      # Your fleet config
  mcp.json                         # MCP server registry
  profiles.json                    # Saved profiles
  hooks.json
  permissions.json
  config.json                      # Theme, retry policy, approval flow
  costs.json                       # Auto-generated
  sessions/                        # Saved conversations
  memory/                          # MD memory store
  logs/                            # Daily JSONL event logs
  plugins/                         # User Tool subclasses
  prompt_templates/                # Reusable prompts

~/agents/                          # Default location (override via $GEMI_PROJECTS_ROOT)
  agent-1/
    Qwen3-Coder-...gguf
    launcher/
      start.ps1                    # Boots llama-server + proxy
      llama-server.json
      proxy.ps1
    logs/
      .pids/                       # PID tracking
```

## Anthropic Messages API protocol

All Gemi ↔ proxy traffic uses the Anthropic Messages API format. The
proxy translates to/from llama-server's OpenAI-compatible API.

**Request** (POST `http://127.0.0.1:{proxy_port}/v1/messages`):
```json
{
  "model": "claude-3-5-sonnet-latest",
  "max_tokens": 1024,
  "messages": [{"role": "user", "content": "..."}],
  "system": "You are a coding assistant.",
  "tools": [{"name": "read_file", "description": "...", "input_schema": {...}}],
  "temperature": 0.2,
  "stream": true
}
```

**SSE events** (assembled into the standard response object):
- `message_start` — id, model, input token count
- `content_block_start` — new text or tool_use block
- `content_block_delta` — incremental text (`text_delta`),
  tool args (`input_json_delta`), or thinking (`thinking_delta`)
- `content_block_stop` — block complete, JSON tool args assembled
- `message_delta` — stop_reason, output tokens
- `[DONE]` — sentinel

## Qwen 3.6 tool-call fix

Qwen 3.6 emits a broken proprietary XML for tool calls:

```xml
<tool_call><function=bash><parameter=command>ls -la</tool_call>
```

Missing closing tags, wrong format. Two-layer fix:

1. **Server-side**: `gemi/templates/qwen36_tool_call_fix.jinja` is passed
   to `llama-server --chat-template-file`. The template instructs the
   model to emit JSON inside `<tool_call>` tags:
   ```xml
   <tool_call>{"name": "bash", "arguments": {"command": "ls -la"}}</tool_call>
   ```

2. **Client-side fallback**: `Provider._parse_qwen36_broken_tool_calls()`
   scans response text for `<tool_call>` patterns and synthesizes
   `tool_use` blocks if the model regressed to the broken format.

## Error handling

| Trigger | Detection | Action |
|---|---|---|
| Context overflow | HTTP 413 / "too large" | suggest `/compact` or `/clear` |
| Timeout | 300s with no response | suggest retry or `/agent` switch |
| Connection refused | proxy unreachable | print boot command for `gemi.ps1 -Boot <slug>` |
| Server overload | HTTP 529/503/502 | auto-retry up to 2× with exponential backoff |
| Permission denied | YOLO tool in normal mode | error message suggests `/yolo` |
| Pattern match | WRITE tool with risky args | error message suggests `/yolo` |
| Transient tool error | network/timeout/rate-limit | retry-with-backoff (configurable) |
