---
description: One-time setup after installing ARIS as a Claude Code plugin — registers the Codex reviewer MCP server from the plugin directory and points ARIS helpers at it. Run once; re-run only if `claude mcp list` stops showing codex as connected.
---

# ARIS plugin setup

This plugin ships the skills. Two things live outside the plugin's reach and
have to be wired once: the `codex` MCP server every reviewer call goes through,
and the pointer that lets skills find ARIS's helper scripts. Do both now, in
this order, with Bash. Report each step's outcome plainly; do not add checks
beyond these.

The plugin is installed at:

```
${CLAUDE_PLUGIN_ROOT}
```

## 1. Codex CLI

```bash
codex --version && codex login status
```

If `codex` is missing, stop and tell the user to run
`npm install -g @openai/codex && codex login`, then `/aris:setup` again.
If it is installed but not logged in, tell the user to run `!codex login`
(the `!` prefix runs it in this session) and come back. Any codex-cli version
works — the bridge below uses `codex exec`, which every version has.

## 2. Register the `codex` MCP server (user scope)

ARIS skills call `mcp__codex__codex`, so the server must be registered under
the name `codex`. codex-cli 0.154 removed `codex mcp-server`; ARIS ships its
own stand-in, and the plugin directory contains it.

```bash
claude mcp get codex 2>/dev/null | grep -A1 Command
```

If the registered command is not already
`python3 ${CLAUDE_PLUGIN_ROOT}/mcp-servers/codex-exec/server.py`:

```bash
claude mcp remove codex -s user 2>/dev/null
claude mcp add codex -s user -- python3 "${CLAUDE_PLUGIN_ROOT}/mcp-servers/codex-exec/server.py"
```

Requires `python3` 3.9+ on PATH (macOS system Python is fine, no packages).

## 3. Point ARIS helpers at the plugin

Skills resolve helper scripts (`verify_papers.py`, `save_trace.sh`, …) through
`~/.aris/repo`. Write it only if it is missing or points at a directory that no
longer exists — an existing ARIS clone is just as good and must not be
overwritten:

```bash
mkdir -p ~/.aris
if [ ! -f ~/.aris/repo ] || [ ! -d "$(cat ~/.aris/repo)" ]; then
  printf '%s\n' "${CLAUDE_PLUGIN_ROOT}" > ~/.aris/repo
fi
cat ~/.aris/repo
```

## 4. Tell the user what to do next

- Restart Claude Code — MCP servers are loaded at startup. Then
  `claude mcp list` must show `codex: python3 …/codex-exec/server.py - ✔ Connected`.
- Plugin skills are namespaced: type `/aris:idea-discovery "…"`,
  `/aris:paper-writing "…"`, `/aris:research-implement-feature "…"`. Skills
  call each other by their short names internally; only what the user types
  carries the `aris:` prefix.
- The reviewer model comes from `~/.codex/config.toml` (ARIS assumes
  `gpt-6-astra` at `xhigh`); nothing here changes it.
- Updates: `claude plugin update aris@aris`. Setup does not need re-running
  after an update.
