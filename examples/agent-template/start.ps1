<#
.SYNOPSIS
    Reference agent launcher — boots llama-server + Anthropic-Messages-API proxy.

.DESCRIPTION
    Drop this into <agent-dir>/launcher/start.ps1 alongside your model file.
    Gemi's main launcher (gemi.ps1) calls this with -Proxy when you pick the
    agent. Edit the constants at the top to match your agent.

.EXAMPLE
    .\start.ps1 -Proxy           Boot both llama-server and the proxy
    .\start.ps1                  Boot llama-server only
    .\start.ps1 -Stop            Stop everything (kills tracked PIDs)
    .\start.ps1 -Check           Show running status

.NOTES
    Expected layout:
      <agent-dir>/
        launcher/
          start.ps1                  (this file)
          llama-server.json          (optional config, see below)
        <model>.gguf                  (the model file)
        logs/
          .pids/                      (auto-managed PID tracking)
#>
param(
    [switch]$Proxy,
    [switch]$Stop,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

# ---- AGENT CONFIG --- edit these to match your setup ------------------

$AGENT_NAME    = "Local Agent 1"
$MODEL_FILE    = "Qwen3.6-35B-A3B-Q4_K_M.gguf"        # in this agent's root dir
$LLAMA_PORT    = 8001
$PROXY_PORT    = 9001
$CONTEXT       = 16384
$NGL           = 99                                     # GPU layers
$PARALLEL      = 2
$BATCH_SIZE    = 1024
$UBATCH_SIZE   = 512
$THREADS       = 8
$FLASH_ATTN    = $true

# Path to llama-server.exe (or just "llama-server" if on PATH)
$LLAMA_SERVER  = "llama-server"

# Chat template fix (Qwen3.6 needs this for proper tool-call JSON output).
# Path is relative to this script. Default points at Gemi's bundled fix.
$CHAT_TEMPLATE = "$PSScriptRoot\..\..\..\..\Gemi\gemi\templates\qwen36_tool_call_fix.jinja"

# Anthropic-Messages-API proxy command.
# We call free-claude-code's uvicorn server. Replace with your proxy.
$PROXY_CMD     = "uvicorn"
$PROXY_ARGS    = @(
    "free_claude_code.server:app"
    "--host", "127.0.0.1"
    "--port", "$PROXY_PORT"
)
$PROXY_ENV     = @{
    "UPSTREAM_BASE" = "http://127.0.0.1:$LLAMA_PORT/v1"
}

# ---- end of config ----------------------------------------------------

$root      = Split-Path $PSScriptRoot -Parent       # agent root (one level up)
$logDir    = Join-Path $root "logs"
$pidDir    = Join-Path $logDir ".pids"
New-Item -ItemType Directory -Force -Path $logDir, $pidDir | Out-Null

$modelPath = Join-Path $root $MODEL_FILE


function Write-Step  { param([string]$t) Write-Host "  ▸ $t" -ForegroundColor Cyan }
function Write-OK    { param([string]$t) Write-Host "  [OK] $t" -ForegroundColor Green }
function Write-Warn  { param([string]$t) Write-Host "  [WARN] $t" -ForegroundColor Yellow }
function Write-Err   { param([string]$t) Write-Host "  [FAIL] $t" -ForegroundColor Red }


function Stop-Pid {
    param([string]$Name)
    $f = Join-Path $pidDir "$Name.pid"
    if (-not (Test-Path $f)) { return }
    $procId = Get-Content $f -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($procId) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-OK "stopped $Name (pid $procId)"
        } catch {}
    }
    Remove-Item $f -Force -ErrorAction SilentlyContinue
}

function Test-Port {
    param([int]$P)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect("127.0.0.1", $P, $null, $null)
        $waited = $iar.AsyncWaitHandle.WaitOne(500, $false)
        if (-not $waited) { $tcp.Close(); return $false }
        $tcp.EndConnect($iar) | Out-Null
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}


# ---- Stop / Check modes ---------------------------------------------

if ($Stop) {
    Write-Step "Stopping $AGENT_NAME"
    Stop-Pid "llama-server"
    Stop-Pid "proxy"
    return
}

if ($Check) {
    $llama = Test-Port $LLAMA_PORT
    $proxy = Test-Port $PROXY_PORT
    Write-Host ""
    Write-Host "  $AGENT_NAME"
    Write-Host "    llama-server :$LLAMA_PORT  $(if ($llama) {'UP'} else {'OFF'})"
    Write-Host "    proxy        :$PROXY_PORT  $(if ($proxy) {'UP'} else {'OFF'})"
    Write-Host ""
    return
}


# ---- Boot llama-server -----------------------------------------------

if (-not (Test-Path $modelPath)) {
    Write-Err "Model not found: $modelPath"
    Write-Host "  Edit `$MODEL_FILE in this script or download the GGUF." -ForegroundColor DarkGray
    exit 1
}

Stop-Pid "llama-server"

Write-Step "Starting llama-server..."
$llamaArgs = @(
    "-m", $modelPath
    "--host", "127.0.0.1"
    "--port", "$LLAMA_PORT"
    "--ctx-size", "$CONTEXT"
    "-ngl", "$NGL"
    "--parallel", "$PARALLEL"
    "--batch-size", "$BATCH_SIZE"
    "--ubatch-size", "$UBATCH_SIZE"
    "--threads", "$THREADS"
)
if ($FLASH_ATTN)   { $llamaArgs += "--flash-attn" }
if ($CHAT_TEMPLATE -and (Test-Path $CHAT_TEMPLATE)) {
    $llamaArgs += "--chat-template-file"
    $llamaArgs += $CHAT_TEMPLATE
    Write-Host "    chat template: $CHAT_TEMPLATE" -ForegroundColor DarkGray
}

$llama = Start-Process -FilePath $LLAMA_SERVER -ArgumentList $llamaArgs `
    -RedirectStandardOutput (Join-Path $logDir "llama-server.log") `
    -RedirectStandardError  (Join-Path $logDir "llama-server.err") `
    -WindowStyle Hidden -PassThru
$llama.Id | Out-File -FilePath (Join-Path $pidDir "llama-server.pid") -Encoding ASCII
Write-OK "llama-server pid $($llama.Id)  port $LLAMA_PORT"


# ---- Boot proxy if requested ----------------------------------------

if ($Proxy) {
    Stop-Pid "proxy"

    # Wait briefly for llama-server to bind
    Start-Sleep -Seconds 2

    Write-Step "Starting Anthropic-Messages-API proxy..."

    # Set env vars for the proxy process
    $envBlock = [System.Collections.Generic.Dictionary[string,string]]::new()
    foreach ($k in $PROXY_ENV.Keys) { $envBlock[$k] = $PROXY_ENV[$k] }

    # Use ProcessStartInfo to inject env vars cleanly
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName  = $PROXY_CMD
    foreach ($a in $PROXY_ARGS) { $null = $psi.ArgumentList.Add($a) }
    $psi.WorkingDirectory   = $root
    $psi.UseShellExecute    = $false
    $psi.WindowStyle        = "Hidden"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    foreach ($k in $envBlock.Keys) { $psi.EnvironmentVariables[$k] = $envBlock[$k] }
    foreach ($v in [System.Environment]::GetEnvironmentVariables().Keys) {
        if (-not $psi.EnvironmentVariables.ContainsKey($v)) {
            $psi.EnvironmentVariables[$v] = [System.Environment]::GetEnvironmentVariable($v)
        }
    }
    $proxy = [System.Diagnostics.Process]::Start($psi)
    $proxy.Id | Out-File -FilePath (Join-Path $pidDir "proxy.pid") -Encoding ASCII
    Write-OK "proxy pid $($proxy.Id)  port $PROXY_PORT"
}

Write-Host ""
Write-OK "$AGENT_NAME booted. Logs: $logDir"
Write-Host "  Run [.\start.ps1 -Stop] to terminate." -ForegroundColor DarkGray
