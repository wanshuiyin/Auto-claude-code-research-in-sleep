# codex-exec — the `codex` MCP server, over `codex exec`

codex-cli 0.154.0 removed the `codex mcp-server` entry point that ARIS
registered as the `codex` MCP server. This bridge speaks the same contract —
tools `codex` and `codex-reply`, results `{threadId, content}` — and runs each
call as a `codex exec` subprocess. Nothing in the skills changes.

## Register

```bash
cd ~/aris_repo && git pull                  # existing install: older clones do not have this directory
claude mcp remove codex -s user             # only if the old `codex mcp-server` registration exists
claude mcp add codex -s user -- python3 "$(pwd)/mcp-servers/codex-exec/server.py"
```

Use the absolute path of your ARIS clone (`$(pwd)` from inside it). Restart
Claude Code; `claude mcp list` should show `codex … ✓ Connected`. Works on every
codex-cli version that has `codex exec` (all of them), so there is no reason to
keep the old registration on 0.153 either. Skills need no change.

Installed by copying `skills/` without keeping a clone? Clone the repo anywhere
and point at its `server.py`; the file is self-contained.

Other MCP hosts (Cursor, Trae, Antigravity, Copilot CLI) use the same key with
`"command": "python3", "args": ["/absolute/path/to/aris_repo/mcp-servers/codex-exec/server.py"]`.

Requirements: `codex` on PATH and logged in; Python 3.9+ (macOS system python is fine); no packages.

## What a call becomes

| MCP argument | `codex exec` |
|---|---|
| `prompt` | stdin (no argv limit) |
| `model` | `-m MODEL` |
| `config` `{"model_reasoning_effort": "ultra"}` | `-c model_reasoning_effort="ultra"` (nested objects become dotted keys) |
| `sandbox` | `--sandbox MODE` |
| `cwd` | `--cd DIR` |
| `codex-reply` `threadId` | `codex exec resume THREAD` **plus the model, config, sandbox and cwd the thread was created with** — `resume` alone would fall back to `config.toml` defaults, and ARIS's routing contract relies on a continued thread keeping its reviewer model and effort |

Per-thread settings live in `~/.codex/state/codex-exec/threads/<threadId>.json`, one file each.

A failed turn (unknown model, auth, API error) comes back as `isError: true`
with codex's own error text, so the capability fallback in
`skills/shared-references/reviewer-routing.md` keys on the same wording as before.

While a review runs the bridge streams `codex/event` notifications and, when the
host passes a `progressToken`, a `notifications/progress` heartbeat every 15 s
(`CODEX_EXEC_PROGRESS_INTERVAL_SEC`), answers `ping`, and honours
`notifications/cancelled`. Notifications cannot override a host's hard tool
timeout — deep-audit reviews at `ultra` can run 30+ minutes.

Not offered, because `codex exec` cannot honour them: `approval-policy`,
`base-instructions`, `developer-instructions`, `compact-prompt`. No ARIS skill
passed them.

Debugging: `CODEX_EXEC_DEBUG_LOG=/path/to/log` records every request and the
exact `codex exec` command line; `CODEX_BIN` points at a specific codex binary.
