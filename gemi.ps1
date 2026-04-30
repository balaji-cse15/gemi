<#
.SYNOPSIS
    Gemi -- unified Windows launcher for the local-fleet AI CLI.

.DESCRIPTION
    Reads agents.json (or ~/.gemi/agents.json, or builds-in defaults) and
    boots the chosen agent's stack via its launcher\start.ps1, then runs
    the Gemi CLI.

.EXAMPLE
    .\gemi.ps1                       # interactive picker
    .\gemi.ps1 1                     # boot agent 1
    .\gemi.ps1 -Agent local-agent-2
    .\gemi.ps1 -Profile yolo
    .\gemi.ps1 -Resume               # resume last session
    .\gemi.ps1 -Status               # fleet table
    .\gemi.ps1 -Doctor               # health check
    .\gemi.ps1 -StopAll              # shut down everything
#>
param(
    [Parameter(Position = 0)]
    [string]$Agent = "",
    [string]$Profile = "",
    [string]$Workspace = "",
    [string]$Resume = "",
    [string]$Exec = "",
    [string]$Boot = "",
    [switch]$Yolo,
    [switch]$Plan,
    [switch]$Auto,
    [switch]$Status,
    [switch]$Doctor,
    [switch]$StopAll,
    [switch]$NoBoot,
    [switch]$NoBanner,
    [switch]$Help
)

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot


# ============================================================================
# Load fleet from agents.json (or use defaults)
# ============================================================================

function Load-Fleet {
    $candidates = @(
        (Join-Path $root "agents.json"),
        (Join-Path $env:USERPROFILE ".gemi\agents.json")
    )
    foreach ($cfg in $candidates) {
        if (Test-Path $cfg) {
            try {
                $data = Get-Content $cfg -Raw | ConvertFrom-Json
                if ($data.agents) { return $data.agents }
                if ($data.fleet)  { return $data.fleet }
            } catch { }
        }
    }

    # Built-in default fleet (3 agents).
    return @(
        [PSCustomObject]@{
            slug="local-agent-1"; name="Local Agent 1"; directory="agent-1"
            port=8001; proxy_port=9001; quant="Q4_K_M"; context=16384; parallel=2
            quality_tier="high"; role="general coder"
        },
        [PSCustomObject]@{
            slug="local-agent-2"; name="Local Agent 2"; directory="agent-2"
            port=8002; proxy_port=9002; quant="Q8_K_P"; context=8192; parallel=1
            quality_tier="premium"; role="precision coder"
        },
        [PSCustomObject]@{
            slug="local-agent-3"; name="Local Agent 3"; directory="agent-3"
            port=8003; proxy_port=9003; quant="IQ3_M"; context=32768; parallel=4
            quality_tier="fast"; role="fast throughput"
        }
    )
}

$Fleet = Load-Fleet
$projectsRoot = if ($env:GEMI_PROJECTS_ROOT) { $env:GEMI_PROJECTS_ROOT } else { Join-Path $env:USERPROFILE "agents" }


function Get-AgentByQuery {
    param([string]$Query)
    if ([string]::IsNullOrWhiteSpace($Query)) { return $null }
    $q = $Query.Trim().ToLower()
    foreach ($a in $Fleet) {
        if ($a.slug.ToLower() -eq $q) { return $a }
        if ($a.name.ToLower() -eq $q) { return $a }
    }
    foreach ($a in $Fleet) {
        if ($a.slug.ToLower() -like "*$q*") { return $a }
    }
    return $null
}


# ============================================================================
# Pretty-print helpers (pure ASCII)
# ============================================================================

function W       { param([string]$t, [string]$c = "Gray") Write-Host $t -ForegroundColor $c -NoNewline }
function WL      { param([string]$t, [string]$c = "Gray") Write-Host $t -ForegroundColor $c }
function WS      { param([string]$t)  WL "" ; WL "  >> $t" "Magenta" ; WL "" }
function WOK     { param([string]$t)  WL "  [OK]   $t" "Green" }
function WERR    { param([string]$t)  WL "  [FAIL] $t" "Red" }
function WWARN   { param([string]$t)  WL "  [WARN] $t" "Yellow" }
function WSTEP   { param([string]$t)  WL "  --> $t" "Cyan" }
function WDIM    { param([string]$t)  WL "       $t" "DarkGray" }


function Show-Banner {
    if ($NoBanner) { return }
    WL ""
    WL "   ######  ######## ##     ## ####" "Magenta"
    WL "  ##    ## ##       ###   ###  ##" "Magenta"
    WL "  ##       ##       #### ####  ##" "Magenta"
    WL "  ##  ###  ######   ## ### ##  ##" "Magenta"
    WL "  ##   ##  ##       ##     ##  ##" "Magenta"
    WL "  ##    ## ##       ##     ##  ##" "Magenta"
    WL "   ######  ######## ##     ## ####" "Magenta"
    W   "    *  " "Magenta"
    WL "local-fleet AI coding assistant" "DarkGray"
    WL ""
}


# ============================================================================
# Boot detection
# ============================================================================

function Test-Port {
    param([int]$PortNum)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect("127.0.0.1", $PortNum, $null, $null)
        $waited = $iar.AsyncWaitHandle.WaitOne(500, $false)
        if (-not $waited) { $tcp.Close(); return $false }
        $tcp.EndConnect($iar) | Out-Null
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}


function Get-AgentStatus {
    param($AgentObj)
    $modelUp = Test-Port $AgentObj.port
    $proxyUp = Test-Port $AgentObj.proxy_port
    if ($modelUp -and $proxyUp) { return "READY" }
    if ($modelUp) { return "MODEL" }
    if ($proxyUp) { return "PROXY" }
    return "OFF"
}


function Start-AgentBoot {
    param($AgentObj)

    $startScript = Join-Path $projectsRoot "$($AgentObj.directory)\launcher\start.ps1"
    if (-not (Test-Path $startScript)) {
        WERR "boot script missing: $startScript"
        WDIM "Set up the agent's launcher\start.ps1 first. See README -> Adding Agents."
        return $false
    }

    WSTEP "Booting $($AgentObj.name) ($($AgentObj.slug))..."
    WDIM "llama-server :$($AgentObj.port)   proxy :$($AgentObj.proxy_port)"

    try {
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = "powershell.exe"
        $startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -Proxy"
        $startInfo.WorkingDirectory = (Split-Path $startScript -Parent)
        $startInfo.UseShellExecute = $false
        $startInfo.WindowStyle = "Hidden"
        $proc = [System.Diagnostics.Process]::Start($startInfo)
    } catch {
        WERR "couldn't run start.ps1: $_"
        return $false
    }

    WSTEP "Waiting for ports to open (up to 60s)..."
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if ((Test-Port $AgentObj.port) -and (Test-Port $AgentObj.proxy_port)) {
            WL ""
            WOK "$($AgentObj.slug) READY"
            return $true
        }
        Start-Sleep -Milliseconds 800
        Write-Host "." -NoNewline -ForegroundColor DarkGray
    }
    WL ""
    WWARN "ports didn't both come up -- check $($AgentObj.directory)\logs\"
    return $false
}


function Stop-AllAgents {
    WS "Stopping all agents"
    $stopped = 0
    foreach ($a in $Fleet) {
        $stop = Join-Path $projectsRoot "$($a.directory)\launcher\start.ps1"
        if (-not (Test-Path $stop)) { continue }
        if ((Test-Port $a.port) -or (Test-Port $a.proxy_port)) {
            WSTEP "Stopping $($a.slug)..."
            try {
                & $stop -Stop 2>&1 | Out-Null
                $stopped++
            } catch {}
        }
    }
    Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    WOK "$stopped agents told to stop"
}


function Show-FleetTable {
    $tierGlyph = @{
        "premium"="**"; "high"="++"; "standard"="++"; "fast"="+-"; "economy"="--"
    }
    WL ""
    W "  #   " "DarkGray"
    W "Slug                  "        "Cyan"
    W "Status      "                  "Gray"
    W "Quant      "                   "Yellow"
    W "Ctx       "                    "DarkGray"
    W "P    "                         "DarkGray"
    W "Tier         "                 "DarkGray"
    WL "Role" "DarkGray"
    WL "  -------------------------------------------------------------------------------------------------" "DarkGray"

    $i = 1
    foreach ($a in $Fleet) {
        $st = Get-AgentStatus $a
        $stColor = switch ($st) {
            "READY"  { "Green" }
            default  { "DarkGray" }
        }
        $stGlyph = if ($st -eq "READY") { "[ON ] " } elseif ($st -eq "OFF") { "[off] " } else { "[~~ ] " }
        $tg = $tierGlyph[$a.quality_tier]
        if (-not $tg) { $tg = ".." }
        $key = if ($i -lt 10) { "$i" } else { "0" }
        W ("  [{0}]  " -f $key) "Magenta"
        W ($a.slug.PadRight(22)) "Cyan"
        W $stGlyph $stColor
        W ($st.PadRight(6)) $stColor
        W ($a.quant.PadRight(11)) "Yellow"
        W (("{0:N0}" -f $a.context).PadLeft(7) + "   ") "DarkGray"
        W ("p" + $a.parallel + "   ") "DarkGray"
        W ($tg + " ") "Yellow"
        W ($a.quality_tier.PadRight(11)) "DarkGray"
        WL ($a.role) "DarkGray"
        $i++
    }
    WL ""
    $running = ($Fleet | Where-Object { Test-Port $_.proxy_port }).Count
    WDIM "$running of $($Fleet.Count) agents online"
    WL ""
}


function Show-Picker {
    while ($true) {
        WS "Select an agent"
        Show-FleetTable
        W "  " ; W "[s]" "Magenta" ; W "  status refresh    " "DarkGray"
        W "[d]" "Magenta" ; W "  doctor          " "DarkGray"
        W "[k]" "Magenta" ; W "  stop all         " "DarkGray"
        W "[q]" "Magenta" ; WL "  quit" "DarkGray"
        WL ""

        W "  Pick agent " "DarkGray"
        W "[1-9, 0]" "White"
        W " or type slug: " "DarkGray"
        $resp = Read-Host
        if ($resp) { $resp = $resp.Trim() }

        if ([string]::IsNullOrWhiteSpace($resp)) {
            $running = $Fleet | Where-Object { Test-Port $_.proxy_port } | Select-Object -First 1
            if ($running) { return $running }
            return $Fleet[0]
        }

        if ($resp -eq "q") { return $null }
        if ($resp -eq "s") { continue }
        if ($resp -eq "d") { return "DOCTOR" }
        if ($resp -eq "k") { Stop-AllAgents; continue }

        if ($resp -match '^\d+$') {
            $n = [int]$resp
            $idx = if ($n -ge 1) { $n - 1 } else { 9 }
            if ($idx -ge 0 -and $idx -lt $Fleet.Count) { return $Fleet[$idx] }
            WWARN "Invalid number"
            continue
        }

        $match = Get-AgentByQuery $resp
        if ($match) { return $match }
        WWARN "No agent matches '$resp'"
    }
}


function Run-Doctor {
    Show-Banner
    WS "Health check"

    try {
        $pyVer = (python --version 2>&1) -join " "
        WOK "Python: $pyVer"
    } catch { WERR "Python not on PATH"; exit 1 }

    $bv = $null
    try { $bv = (python -c "import gemi; print(gemi.__version__)" 2>$null).Trim() } catch {}
    if ($bv) { WOK "Gemi: v$bv" } else {
        WWARN "Gemi not installed -- run: pip install -e ."
    }

    try {
        $nv = (node --version 2>$null).Trim()
        $nx = (npx --version 2>$null).Trim()
        if ($nv) { WOK "Node $nv  npx $nx" } else { WWARN "Node not on PATH" }
    } catch { WWARN "Node not on PATH" }

    try {
        $uv = (uvx --version 2>$null).Trim()
        if ($uv) { WOK "uvx: $uv" } else { WWARN "uvx not found -- pip install uv" }
    } catch { WWARN "uvx not found" }

    try {
        $gv = (git --version 2>$null).Trim()
        if ($gv) { WOK "$gv" } else { WWARN "git not on PATH" }
    } catch { WWARN "git not on PATH" }

    $bashCandidates = @(
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files (x86)\Git\bin\bash.exe"
    )
    $foundBash = $bashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($foundBash) { WOK "Git Bash: $foundBash" } else { WWARN "Git Bash not found" }

    $gemiDir = Join-Path $env:USERPROFILE ".gemi"
    foreach ($sub in @("sessions", "memory", "logs", "plugins", "prompt_templates")) {
        $p = Join-Path $gemiDir $sub
        if (-not (Test-Path $p)) {
            New-Item -ItemType Directory -Path $p -Force | Out-Null
            WOK "Created $p"
        } else { WDIM "$p" }
    }

    WS "Per-agent launchers"
    foreach ($a in $Fleet) {
        $sp = Join-Path $projectsRoot "$($a.directory)\launcher\start.ps1"
        if (Test-Path $sp) { WDIM "[OK] $($a.slug.PadRight(18)) -> $sp" }
        else { WERR "[--] $($a.slug.PadRight(18)) -> $sp" }
    }

    WS "Fleet status"
    Show-FleetTable
}


# ============================================================================
# Main flow
# ============================================================================

if ($Help)    { Get-Help $PSCommandPath -Full; exit 0 }
if ($Doctor)  { Run-Doctor; exit 0 }
if ($StopAll) { Show-Banner; Stop-AllAgents; exit 0 }

if ($Boot) {
    Show-Banner
    $a = Get-AgentByQuery $Boot
    if (-not $a) { WERR "no agent matches '$Boot'"; exit 1 }
    if ((Get-AgentStatus $a) -eq "READY") {
        WOK "$($a.slug) already READY"
        exit 0
    }
    if (Start-AgentBoot $a) { exit 0 } else { exit 1 }
}

if ($Status) { Show-Banner ; Show-FleetTable ; exit 0 }


$resolvedAgent = $null
if ($Agent) {
    $resolvedAgent = Get-AgentByQuery $Agent
    if (-not $resolvedAgent) {
        Show-Banner
        WERR "no agent matches '$Agent'"
        exit 1
    }
}

Show-Banner

if (-not $resolvedAgent -and -not $Profile -and -not $Resume) {
    $picked = Show-Picker
    if ($null -eq $picked) { WL "  Goodbye." "DarkGray"; exit 0 }
    if ($picked -eq "DOCTOR") { Run-Doctor; exit 0 }
    $resolvedAgent = $picked
}


if ($resolvedAgent -and -not $NoBoot -and -not $Resume) {
    $st = Get-AgentStatus $resolvedAgent
    if ($st -ne "READY") {
        if ($st -eq "OFF") {
            Start-AgentBoot $resolvedAgent | Out-Null
        } else {
            WWARN "$($resolvedAgent.slug) status: $st (partial). Continuing..."
        }
    } else {
        WOK "$($resolvedAgent.slug) already READY"
    }
}


$args_list = @()
if ($resolvedAgent) { $args_list += "--agent"; $args_list += $resolvedAgent.slug }
if ($Workspace)     { $args_list += "--workspace"; $args_list += $Workspace }
if ($Profile)       { $args_list += "--profile"; $args_list += $Profile }
if ($Yolo)          { $args_list += "--yolo" }
if ($Plan)          { $args_list += "--plan" }
if ($Auto)          { $args_list += "--autopilot" }
if ($Resume) {
    $args_list += "--resume"
    if ($Resume -ne "True" -and $Resume -ne "true" -and $Resume -ne "$true") {
        $args_list += $Resume
    }
}
if ($Exec) { $args_list += "--exec"; $args_list += $Exec }


WL ""
WSTEP "Launching Gemi..."
WL ""

Push-Location $root
try {
    python -m gemi @args_list
    $cliExit = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($cliExit) { exit $cliExit }
