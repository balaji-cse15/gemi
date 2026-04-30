# Agent template

Reference per-agent launcher. Copy this directory into your `$GEMI_PROJECTS_ROOT`
(default `~/agents/`) and edit the values at the top of `start.ps1` to match
your model + ports.

## Layout

```
~/agents/
  agent-1/                                 ← name this whatever you want
    launcher/
      start.ps1                            ← copy from this template
      llama-server.json                    ← optional, mirrors start.ps1 constants
    Qwen3.6-35B-A3B-Q4_K_M.gguf            ← your downloaded GGUF
    logs/                                  ← auto-created
      .pids/                               ← auto-managed
```

Then point your `~/.gemi/agents.json` at it:

```json
{
  "agents": [
    {
      "slug":       "local-agent-1",
      "name":       "Local Agent 1",
      "directory":  "agent-1",
      "port":       8001,
      "proxy_port": 9001,
      "model":      "Qwen3.6-35B-A3B-Q4_K_M.gguf",
      "quant":      "Q4_K_M",
      "context":    16384,
      "parallel":   2,
      "can_think":  true,
      "quality_tier": "high",
      "role":       "general coder",
      "chat_template": "qwen36"
    }
  ]
}
```

## What `start.ps1` does

1. Spawns `llama-server` listening on `LLAMA_PORT` (default 8001) with
   `--ngl 99 --flash-attn --parallel 2 --chat-template-file ...`
2. If `-Proxy` is passed: spawns the Anthropic-Messages-API translator
   (free-claude-code by default) listening on `PROXY_PORT` (default 9001),
   pointing upstream at `127.0.0.1:LLAMA_PORT`.
3. Tracks PIDs in `logs/.pids/` so `start.ps1 -Stop` can kill them.

## Customising

Edit the `$AGENT_NAME` block at the top of `start.ps1`:

```powershell
$AGENT_NAME    = "My Coder"
$MODEL_FILE    = "qwen3-coder-30b-Q5_K_M.gguf"
$LLAMA_PORT    = 8001
$PROXY_PORT    = 9001
$CONTEXT       = 32768
$PARALLEL      = 4
```

For different proxies (LiteLLM, custom translation layer, ...), change
`$PROXY_CMD` and `$PROXY_ARGS`.

## Testing manually

```powershell
.\start.ps1            # llama-server only
.\start.ps1 -Proxy     # both
.\start.ps1 -Check     # report port status
.\start.ps1 -Stop      # kill both
```

## Hooked up to gemi

Once the agent is configured in `agents.json`, the main `gemi.ps1`
launcher will auto-call this script:

```cmd
gemi.bat 1            ← boots agent-1 + drops you in the REPL
gemi.bat -Boot 1      ← just boots, no REPL
gemi.bat -Status      ← see port status across the whole fleet
gemi.bat -StopAll     ← shut down every agent
```
