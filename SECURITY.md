# Security

## Where credentials and API keys belong

Gemi never bundles or requires any API keys. **Every key you supply lives
on your local machine and is never committed to the repository.**

The intended layout:

```
~/.gemi/                          ← user-private, gitignored
  agents.json                     ← your fleet definition (paths, ports)
  mcp.json                        ← MCP servers (some need tokens — see below)
  permissions.json                ← per-tool allow/deny rules
  hooks.json                      ← PreToolUse/PostToolUse triggers
  sessions/                       ← saved transcripts
  logs/                           ← runtime logs

your-project/.env                 ← per-project secrets (gitignored)
```

The repository's [`.gitignore`](.gitignore) explicitly excludes:

- `agents.json`, `mcp.json`, `hooks.json`, `permissions.json`, `profiles.json`
- `.env`, `.env.*` (only `.env.example` / `.env.template` are tracked)
- `*credentials*`, `*token*.json`, `*secret*.txt`, `.netrc`, `.ssh/`, `id_rsa*`
- `*.pem`, `*.key`, `*.pfx`, `*.p12`, `*.crt`, service-account JSONs

## Optional API keys (only if you use those MCP servers)

Set these in `~/.gemi/.env` or your shell environment — they're read by the
MCP server processes Gemi spawns, not by the CLI itself:

| Variable | Used by | Free tier? |
| --- | --- | --- |
| `GITHUB_TOKEN` | `github` MCP server | ✅ Personal access tokens |
| `BRAVE_API_KEY` | `brave-search` MCP server | ✅ Free 2k/month |
| `NOTION_TOKEN` | `notion` MCP server | ✅ With personal workspace |
| `SUPABASE_ACCESS_TOKEN` | `supabase` MCP server | ✅ |
| `CLOUDFLARE_API_TOKEN` | `cloudflare` MCP server | ✅ Free tier |
| `HF_TOKEN` | `huggingface` MCP server | ✅ |

**None of these are required.** All 100+ built-in tools and the 13+ free
public-API tools (`weather`, `wiki`, `arxiv`, `hn_top`, `crypto_price`,
`pokemon`, etc.) work without any keys at all.

If a key is missing, the corresponding MCP server simply fails to start
and the rest of Gemi keeps running. There's no "gemi-cloud" to authenticate
against — every model call goes to your local `llama-server`.

## What the CLI sends over the network

By default, **nothing leaves your machine**. The agent loop talks to:

- `127.0.0.1:8001+N` — your `llama-server` instance
- `127.0.0.1:9001+N` — the Anthropic-Messages-API-compat proxy

Tools that explicitly hit the public internet (`web_fetch`, `web_search`,
`crypto_price`, `weather`, etc.) are flagged with the `[web]` capability
so you know exactly which calls leave the box. Disable any of them via
`~/.gemi/permissions.json`.

## Reporting a vulnerability

If you find a security issue, please **do not** open a public GitHub issue.
Email the repo owner directly via the contact on the GitHub profile, or
open a private security advisory at:

`https://github.com/space-kitty-o/gemi/security/advisories/new`

## Don't paste real keys into examples or PRs

`examples/.env.example` and `examples/agents.example.json` are tracked but
must contain only placeholders. Pre-commit, eyeball the diff (`git diff
--cached`) before pushing — Gemi has no automatic scrubbing yet.

GitHub's secret-scanning is enabled on this repo, but treat that as a
last-resort backstop, not your first line of defense.
