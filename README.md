# Gemi

> A Claude-Code-style CLI that drives a fleet of **local LLM agents**.
> Multi-agent delegation, MCP support, plugins, sub-agent tasks, autopilot,
> 100+ built-in tools (file, shell, web, security, free public APIs),
> hooks, caching, energy/cost tracking.

```
   ######  ######## ##     ## ####
  ##    ## ##       ###   ###  ##
  ##       ##       #### ####  ##
  ##  ###  ######   ## ### ##  ##
  ##   ##  ##       ##     ##  ##
  ##    ## ##       ##     ##  ##
   ######  ######## ##     ## ####
    *  local-fleet AI coding assistant
```

```
> what's the weather in Tokyo and the top hacker news story right now
✻  fetching both in parallel...

  -- weather --
  Tokyo, Japan: 18°C, partly cloudy, wind 12 km/h
  -- hn top --
  1. [1247↑ 532c] Show HN: ... by ...
```

---

## What it is

Gemi is a terminal CLI for talking to local LLMs running on your own hardware.
It connects to one or more **`llama-server`** instances (typically on ports
8001-801N) through Anthropic-Messages-API-compatible proxies (e.g.
[`free-claude-code`](https://github.com/spectrobit/free-claude-code)) on ports 9001-901N.

Where Claude Code talks to the Anthropic API, Gemi talks to *your* fleet.

### Highlights

- **Multi-agent fleet**: configure as many agents as you have GPU for, switch
  with `Ctrl+M` or `/<n>` (1-9, 0). Each agent has its own llama-server +
  proxy + slug + role.
- **Built-in tool library — 100+ tools**: file ops, shell (bash/cmd/PowerShell),
  git, web fetch, web search, hashing, JSON/YAML/TOML, image input,
  Hacker News, weather, currency, Wikipedia, NASA APOD, IP geolocation,
  cryptocurrency prices, Pokemon, Stack Exchange, and more — all
  free, no keys.
- **Cybersecurity / CTF suite**: 24 offensive tools — exploit payload
  library (SQLi/XSS/SSRF/XXE/SSTI/JWT/etc.), recon (subdomain enum, DNS,
  ASN, fingerprinting, port scan), cipher detection + decode, hash
  identifier, OWASP web security probes, GraphQL/REST API testers.
- **MCP client**: stdio + HTTP/SSE transports, env-var substitution,
  ~30 servers pre-configured (filesystem, fetch, memory, sequential
  thinking, time, context7, GitHub, Notion, Supabase, etc.). Tools from
  every connected server show up automatically as `mcp_<server>_<tool>`.
- **Autopilot v2**: subgoal tracking, step budgets, stall detection,
  recovery prompts, live progress panel.
- **Plugin system**: drop a `.py` file in `~/.gemi/plugins/`, the Tool
  classes you define get auto-registered.
- **Sub-agent tasks**: agents can spawn isolated sub-agents with their own
  tool loops via the `task` tool (max recursion depth 2).
- **Profiles**: saved bundles of `agent + mode + theme + workspace` —
  switch contexts with `gemi -Profile pentest` or `/profile yolo`.
- **Hooks**: `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, etc.
  configured via JSON.
- **Cache + retry + approval**: LRU cache for safe reads, retry-with-backoff
  for transient errors, optional interactive `y/n/a/d` approval flow for
  risky tool calls.
- **Energy/cost tracking**: per-turn kWh + USD estimate based on quant
  tier and inference time, persisted to `~/.gemi/costs.json`.

---

## Quick start

### 1. Prerequisites

- **Windows 10/11** (this shell is Windows-first; Linux/macOS support is
  experimental).
- **Python 3.11+**
- **Node.js + npx** (for npm-based MCP servers — filesystem, memory,
  sequential-thinking, etc.)
- **uv / uvx** (for Python-based MCP servers — fetch, time, git, sqlite).
  Install with `pip install uv`.
- **Git Bash** (lets the `bash` tool actually use bash on Windows).
- **A built `llama.cpp`** with `llama-server` on your PATH or somewhere
  callable from a launcher script.
- **At least one GGUF model** downloaded (e.g. from Hugging Face).

### 2. Install Gemi

```cmd
git clone https://github.com/space-kitty-o/gemi
cd gemi
pip install -e .
```

### 3. Bootstrap your config

```cmd
mkdir %USERPROFILE%\.gemi
copy examples\mcp.example.json     %USERPROFILE%\.gemi\mcp.json
copy examples\profiles.example.json %USERPROFILE%\.gemi\profiles.json
copy examples\agents.example.json  %USERPROFILE%\.gemi\agents.json
```

Now edit `%USERPROFILE%\.gemi\agents.json` to match your actual local
agent setup (paths, ports, model files). See **Adding Agents** below.

### 4. Start an agent

For each agent, you need a directory containing `launcher\start.ps1`
that boots `llama-server` + a proxy. The `gemi.ps1` launcher will call
that script for you. See **Agent Launcher Layout** below for the format.

### 5. Run

```cmd
gemi.bat
```

You'll see the picker. Pick an agent, drop into the REPL.

---

## Usage

```cmd
gemi.bat                      :: interactive picker
gemi.bat 1                    :: boot agent 1, drop into REPL
gemi.bat -Agent local-agent-2 :: same, by full slug
gemi.bat -Profile yolo        :: apply a saved profile
gemi.bat -Resume              :: resume the most recent session
gemi.bat -Status              :: fleet status table
gemi.bat -Doctor              :: full health check
gemi.bat -Boot 1              :: boot agent 1 only (no REPL)
gemi.bat -StopAll             :: shut down every running agent
```

In the REPL:

```
> /help                       List all commands (60+ across 12 categories)
> /agent                      Open the agent picker
> /3                          Quick-switch to agent 3
> Ctrl+M                      Open the agent picker mid-prompt
> Ctrl+Y                      Toggle YOLO mode
> Ctrl+L                      Clear screen
> !ls -la                     Run a shell one-liner directly (no agent turn)
> /sh git status              Same, slash form
> /run                        Detect & list project task runners
> /run test                   Auto-dispatch the 'test' task
> /cat file.py                Syntax-highlighted preview
> /spend                      kWh + USD breakdown
> /mcp                        List MCP servers
> /tools                      Browse the 100+ available tools
> /vote what is 2+2           Run a prompt across all running agents
> /task fix the failing test  Spawn a sub-agent task
> /yolo                       Toggle dangerous tools
> /quit                       Exit
```

---

## Adding agents

Edit `~/.gemi/agents.json`:

```json
{
  "agents": [
    {
      "slug": "local-agent-1",
      "name": "My Coder",
      "directory": "agent-1",
      "port": 8001,
      "proxy_port": 9001,
      "model": "Qwen3.6-35B-A3B-Q4_K_M.gguf",
      "quant": "Q4_K_M",
      "context": 16384,
      "parallel": 2,
      "can_think": true,
      "quality_tier": "high",
      "role": "general coder",
      "chat_template": "qwen36"
    }
  ]
}
```

**`directory`** is interpreted relative to `$env:GEMI_PROJECTS_ROOT`
(default `~/agents/`). So the example above expects a layout like:

```
%USERPROFILE%\agents\agent-1\
  launcher\
    start.ps1                 # boots llama-server + proxy
    llama-server.json         # llama-server config
    proxy.ps1                 # proxy launcher (free-claude-code or similar)
  Qwen3.6-35B-A3B-Q4_K_M.gguf # the model file
  logs\                       # auto-created
```

### Per-agent `start.ps1` contract

The launcher (`gemi.ps1`) invokes each agent's `start.ps1 -Proxy`. Your
`start.ps1` is responsible for spinning up:
- `llama-server` listening on `port` (e.g. 8001)
- An Anthropic-Messages-API-compatible proxy listening on `proxy_port`
  (e.g. 9001)

Both should be running detached/in-background. The launcher will then
poll TCP for both ports and continue once ready. A reference `start.ps1`
is included in the GitHub repo under `examples/agent-template/`.

### `chat_template: "qwen36"`

If you're running a Qwen 3.6 model, set this. It tells `llama-server` to
use Gemi's bundled tool-call template fix at
`gemi/templates/qwen36_tool_call_fix.jinja`. The fix converts Qwen's
broken default XML tool-call format into proper JSON. Without it, tool
calls will silently fail or get stuck in retry loops.

The launcher reads `chat_template_file` from each agent's
`llama-server.json` and passes it to llama-server via
`--chat-template-file`.

---

## Configuration files

All under `~/.gemi/`:

| File | Purpose |
|---|---|
| `agents.json` | Your fleet — slug, ports, model, paths. **Required**. |
| `mcp.json` | MCP server registry — which servers to spawn at startup. |
| `profiles.json` | Saved `agent+mode+theme+workspace` bundles. |
| `hooks.json` | Pre/post tool-call callbacks. |
| `permissions.json` | Allow/deny rules layered over the SAFE/WRITE/YOLO tier system. |
| `config.json` | Global config: theme, retry policy, approval flow. |
| `costs.json` | (Auto-generated) energy/cost log. |
| `sessions/` | (Auto-generated) saved conversation JSONs. |
| `memory/` | (Auto-generated) MD-based memory store with frontmatter. |
| `logs/` | (Auto-generated) JSONL event log per day. |
| `plugins/` | Drop your custom Tool subclasses here. |
| `prompt_templates/` | Reusable prompt templates with `{var}` substitution. |

Examples for each are in `examples/`.

---

## Permission tiers

Every tool has one of three tiers:

- **SAFE** (read-only) — always allowed. Examples: `read_file`, `grep`,
  `tree`, `web_fetch`, `wiki`, `weather`, `cipher_detect`.
- **WRITE** (mutating) — allowed but pattern-checked. Examples:
  `write_file`, `edit_file`, `python_run`. The `DANGEROUS_PATTERNS`
  table blocks risky args (e.g. writes to `.env`, `.aws/credentials`).
- **YOLO** (dangerous) — blocked unless YOLO mode is on. Examples:
  `bash`, `cmd`, `powershell`, `git`, `exploits`, `recon_*`, `websec_*`.
  Designed for legitimate use cases: pentesting under authorization,
  CTF / hackathon competitions, full-shell development. Toggle with
  `--yolo`, `/yolo`, or `Ctrl+Y`.

---

## Architecture

```
+-------------------+        +-------------------+
|   User Terminal   |        | gemi.ps1 / .bat   |
| (Rich + prompt-   |        | (boots agents,    |
|  toolkit REPL)    |        |  starts CLI)      |
+--------+----------+        +---------+---------+
         v                              v
+--------+----------------------------+ |
|              Gemi CLI               |<+
|         (gemi/__main__.py)          |
+----+----------------+---------------+
     |                |
     v                v
+----+----+    +-----+--------+
|  Tool   |    |  Provider    |
| Registry|    |  (httpx SSE) |
| 100+    |    |              |
+----+----+    +-----+--------+
     |               |
     |               v
     |   +-----------+----------+
     |   | local-llm proxies    |
     |   | (free-claude-code)   |
     |   | ports 9001-901N      |
     |   +-----------+----------+
     |               |
     v               v
+----+---------+ +----+----------+
|  MCP servers | | llama-server  |
|  (stdio/HTTP)| | ports 8001-N  |
+--------------+ +---------------+
                       |
                       v
                +------+------+
                | local GPU   |
                | GGUF models |
                +-------------+
```

See `ARCHITECTURE.md` for the deep dive (request flow, streaming,
context compaction, cost tracking, hooks pipeline).

---

## Tool inventory

The full list (100+ tools) lives in `gemi/tools/`. Highlights:

**Core (always present):**
- File: `read_file`, `write_file`, `edit_file`, `multi_edit`, `glob`, `grep`, `tree`, `diff`
- Shell (YOLO): `bash`, `cmd`, `powershell`, `shell`, `git`, `task_runner`
- Reasoning: `think`, `agent_call`, `agent_vote`, `task`
- Web: `web_fetch`, `web_search`, `http_request`, `download`
- Data: `json_parse`, `yaml_parse`, `toml_parse`, `xml_parse`, `csv_parse`, `regex`, `hash`, `base64`

**Free public APIs (13):**
- `hn_top`, `hn_item` (Hacker News)
- `weather` (Open-Meteo, geocodes place names)
- `currency` (Frankfurter ECB rates)
- `wiki` (Wikipedia summaries)
- `arxiv_search` (academic papers)
- `reddit` (public subreddit JSON)
- `nasa_apod` (astronomy picture of the day)
- `country` (REST Countries)
- `ip_lookup` (geolocation)
- `crypto_price` (CoinGecko)
- `pokemon`, `stackexchange`

**Cybersecurity / CTF (24):**
- `exploits` — 200+ payloads across 15 categories (SQLi, XSS, SSRF, XXE, SSTI, LDAP, NoSQL, cmd injection, path traversal, prototype pollution, JWT, CORS, HTTP smuggling, open-redirect)
- `recon_subdomains`, `recon_dns`, `recon_asn`, `recon_fingerprint`,
  `recon_robots`, `recon_ports`, `recon_whois`
- `cipher_detect`, `cipher_decode`, `cipher_xor`, `cipher_caesar`, `cipher_morse`
- `hash_identify`, `hash_hashcat_mode`
- `websec_headers`, `websec_methods`, `websec_cors`, `websec_xss_smoke`, `websec_sqli_smoke`
- `api_introspect_graphql`, `api_openapi_discover`, `api_rate_limit_probe`, `api_auth_bypass`

**Platform integrations (via MCP):** filesystem, GitHub, Notion, Supabase, Cloudflare, Vercel, Linear, Slack, Gmail, Google Drive/Calendar, AWS, Docker, Postgres, SQLite, Playwright, Chrome DevTools, and 15+ more.

---

## Contributing

PRs welcome. Areas that benefit from help:

- More free-API tools (REST Countries, exchange rates, NOAA, etc.)
- Additional MCP server templates in `examples/mcp.example.json`
- Linux/macOS launcher (`gemi.sh`)
- Tests (`tests/` is empty for now)
- More agent-launcher templates (`examples/agent-template/`)

See `CONTRIBUTING.md` for the workflow.

---

## License

Apache 2.0 — see `LICENSE`.
