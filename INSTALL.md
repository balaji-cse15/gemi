# Install Gemi (Windows)

Step-by-step setup for a fresh Windows machine.

## 1. Install prerequisites

```cmd
:: Python (3.11+)
:: Download from https://www.python.org/downloads/  (check "Add to PATH")

:: Node.js (for npm-based MCP servers)
:: Download from https://nodejs.org/

:: Git for Windows (provides Git Bash → makes the `bash` tool work)
:: Download from https://git-scm.com/download/win

:: uv / uvx (for Python-based MCP servers)
pip install uv
```

Verify everything:

```cmd
python --version            :: 3.11+
node --version              :: 18+
npx --version
uvx --version
git --version
```

## 2. Clone Gemi

```cmd
cd %USERPROFILE%
git clone https://github.com/space-kitty-o/gemi
cd gemi
pip install -e .
```

Verify:
```cmd
python -m gemi --version
```

## 3. Build llama.cpp

Gemi expects each agent to have a working `llama-server`. Easiest path:

```cmd
cd %USERPROFILE%
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

:: GPU build (CUDA — recommended)
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j

:: Or CPU-only
cmake -B build
cmake --build build --config Release -j
```

The `llama-server.exe` binary lives at
`%USERPROFILE%\llama.cpp\build\bin\Release\llama-server.exe`.

Add that directory to your PATH, or reference it explicitly in each
agent's `start.ps1`.

## 4. Get a model

Pick a Qwen 3.6 GGUF from Hugging Face (or any other compatible model).
For example:

```
https://huggingface.co/bartowski/Qwen3-Coder-30B-A3B-Instruct-GGUF
```

Download a quant (e.g. `Q4_K_M.gguf`) and put it in your agent's
directory.

## 5. Get an Anthropic-API-compatible proxy

`llama-server`'s default OpenAI API isn't enough — Gemi uses the
Anthropic Messages API. Two options:

**Option A:** [free-claude-code](https://github.com/spectrobit/free-claude-code) — translates Anthropic ↔ OpenAI API.

```cmd
cd %USERPROFILE%
git clone https://github.com/spectrobit/free-claude-code
cd free-claude-code
pip install -e .
```

**Option B:** Use llama.cpp's experimental Anthropic-compatible mode (if available in your version).

## 6. Set up your first agent

Create the directory layout:

```
%USERPROFILE%\agents\agent-1\
  Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf      :: model
  launcher\
    start.ps1                                    :: spins llama-server + proxy
    llama-server.json                            :: llama-server config
    proxy.ps1                                    :: proxy launcher
  logs\
    .pids\                                       :: auto-managed
```

Sample `start.ps1`:

```powershell
param([switch]$Proxy, [switch]$Stop)

$root = Split-Path -Parent $PSScriptRoot
$pidDir = "$root\logs\.pids"
$logDir = "$root\logs"
New-Item -ItemType Directory -Force -Path $pidDir, $logDir | Out-Null

if ($Stop) {
    foreach ($n in @("llama-server", "proxy")) {
        $f = "$pidDir\$n.pid"
        if (Test-Path $f) {
            $p = Get-Content $f | Select-Object -First 1
            try { Stop-Process -Id $p -Force } catch {}
            Remove-Item $f -Force
        }
    }
    return
}

# Start llama-server
$llamaArgs = @(
    "-m", "$root\Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
    "--port", "8001"
    "--host", "127.0.0.1"
    "--ctx-size", "16384"
    "-ngl", "99"
    "--flash-attn"
    "--parallel", "2"
    "--chat-template-file", "$PSScriptRoot\..\..\gemi\templates\qwen36_tool_call_fix.jinja"
)
$ll = Start-Process -FilePath "llama-server" -ArgumentList $llamaArgs `
    -RedirectStandardOutput "$logDir\llama-server.log" `
    -RedirectStandardError "$logDir\llama-server.err" `
    -WindowStyle Hidden -PassThru
$ll.Id | Out-File -FilePath "$pidDir\llama-server.pid" -Encoding ASCII

if ($Proxy) {
    Start-Sleep -Seconds 3
    # Start your proxy of choice here, listening on 9001 and forwarding to 127.0.0.1:8001
    # Example with free-claude-code uvicorn:
    $proxyArgs = @(
        "free_claude_code.server:app"
        "--host", "127.0.0.1"
        "--port", "9001"
    )
    $env:UPSTREAM_BASE = "http://127.0.0.1:8001/v1"
    $proxy = Start-Process -FilePath "uvicorn" -ArgumentList $proxyArgs `
        -RedirectStandardOutput "$logDir\proxy.log" `
        -RedirectStandardError "$logDir\proxy.err" `
        -WindowStyle Hidden -PassThru
    $proxy.Id | Out-File -FilePath "$pidDir\proxy.pid" -Encoding ASCII
}
```

Adjust paths, ports, and proxy choice to match your setup.

## 7. Configure Gemi

```cmd
mkdir %USERPROFILE%\.gemi
copy examples\agents.example.json   %USERPROFILE%\.gemi\agents.json
copy examples\mcp.example.json      %USERPROFILE%\.gemi\mcp.json
copy examples\profiles.example.json %USERPROFILE%\.gemi\profiles.json
```

Edit `agents.json` to match your real setup (slug, directory, port, model
filename, context, quant).

## 8. Run

```cmd
gemi.bat -Doctor       :: full sanity check
gemi.bat               :: interactive picker
gemi.bat 1             :: boot agent 1, drop into REPL
gemi.bat -Status       :: see fleet at a glance
```

You should see the picker, the boot logs, then the REPL prompt. Type
`/help` to explore the 60+ commands.

## Troubleshooting

**"command not found: npx"** when running with MCP enabled:
- Reinstall Node.js with "Add to PATH" checked.
- Or set `enabled: false` for the MCP servers you don't need.

**"PowerShell is in NonInteractive mode"** when running through cmd:
- The launcher uses `-NonInteractive`. Run `gemi.bat` directly (not via
  another batch script that pipes input).

**"Invalid request sent to provider"**:
- Your model's context window is full. Try a smaller agent or increase
  the model's `--ctx-size`. Gemi auto-truncates tools for ≤12K-context
  agents, but the system prompt + workspace context can still bloat.

**Bash tool runs cmd.exe instead of bash**:
- Install Git for Windows. Gemi auto-discovers
  `C:\Program Files\Git\bin\bash.exe`.

**Tool calls fail silently with Qwen 3.6**:
- Set `"chat_template": "qwen36"` in your `agents.json` entry. The
  bundled template fix at `gemi/templates/qwen36_tool_call_fix.jinja`
  rewrites the broken default XML format into proper JSON.

For more, run `gemi.bat -Doctor`.
